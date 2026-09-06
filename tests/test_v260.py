import json
import sqlite3
import tempfile
import unittest
from email.message import Message
from pathlib import Path

from boru.api_tools import (
    ApiMethod,
    ApiRequest,
    ApiResponse,
    BoundedHttpApiClient,
    ControlledApiCoordinator,
    RuleBasedApiRequestParser,
    SafeApiPolicy,
)
from boru.database_tools import (
    DatabaseReadCoordinator,
    ReadOnlySqliteService,
    RuleBasedDatabaseRequestParser,
)
from boru.memory import ConservativeMemoryDecisionGate
from boru.tools import ExclusiveOperationCoordinator


def public_resolver(host, port, type):
    del host, port, type
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


class ApiPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = SafeApiPolicy(("api.example.com",), resolver=public_resolver)

    def test_accepts_allowed_https_host_and_canonicalizes_json(self):
        request = self.policy.validate(
            ApiRequest(ApiMethod.POST, "https://api.example.com/items", '{ "x": 1 }')
        )

        self.assertEqual(request.body, '{"x":1}')

    def test_rejects_http_credentials_ports_and_unlisted_hosts(self):
        values = (
            "http://api.example.com/items",
            "https://user:pass@api.example.com/items",
            "https://api.example.com:8443/items",
            "https://other.example.com/items",
        )

        for url in values:
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.policy.validate(ApiRequest(ApiMethod.GET, url))

    def test_rejects_private_or_mixed_dns_answers(self):
        def private_resolver(host, port, type):
            del host, port, type
            return [
                (2, 1, 6, "", ("93.184.216.34", 443)),
                (2, 1, 6, "", ("127.0.0.1", 443)),
            ]

        policy = SafeApiPolicy(("api.example.com",), resolver=private_resolver)

        with self.assertRaisesRegex(ValueError, "Özel"):
            policy.validate(ApiRequest(ApiMethod.GET, "https://api.example.com"))

    def test_rejects_invalid_or_scalar_json_body(self):
        for body in ("not-json", '"text"', ""):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.policy.validate(
                    ApiRequest(ApiMethod.POST, "https://api.example.com", body)
                )

    def test_rejects_sensitive_data_in_nested_json_body(self):
        bodies = (
            '{"password":"value"}',
            '{"user":{"access_token":"value"}}',
            '{"note":"sk-live-1234567890123456"}',
        )

        for body in bodies:
            with self.subTest(body=body), self.assertRaisesRegex(ValueError, "hassas"):
                self.policy.validate(
                    ApiRequest(ApiMethod.POST, "https://api.example.com", body)
                )


class FakeApiClient:
    def __init__(self):
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return ApiResponse(200, "application/json", json.dumps({"ok": True}))


class HttpApiClientTests(unittest.TestCase):
    def test_sends_fixed_headers_and_bounds_response(self):
        class Response:
            status = 200

            def __init__(self):
                self.headers = Message()
                self.headers["Content-Type"] = "application/json; charset=utf-8"

            def read(self, size):
                return b'{"value":"long"}'[:size]

            def __enter__(self):
                return self

            def __exit__(self, *args):
                del args

        class Opener:
            def __init__(self):
                self.request = None

            def open(self, request, timeout):
                self.request = request
                self.timeout = timeout
                return Response()

        opener = Opener()
        client = BoundedHttpApiClient(
            timeout_seconds=3,
            max_response_bytes=8,
            opener=opener,
        )

        response = client.execute(
            ApiRequest(ApiMethod.POST, "https://api.example.com", '{"x":1}')
        )

        self.assertTrue(response.truncated)
        self.assertEqual(response.body, '{"value"')
        self.assertEqual(opener.request.method, "POST")
        self.assertEqual(opener.request.data, b'{"x":1}')
        self.assertEqual(opener.request.get_header("Accept"), "application/json, text/plain;q=0.9")
        self.assertEqual(opener.timeout, 3)

    def test_rejects_non_text_response(self):
        class Response:
            status = 200

            def __init__(self):
                self.headers = Message()
                self.headers["Content-Type"] = "application/octet-stream"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                del args

        class Opener:
            def open(self, request, timeout):
                del request, timeout
                return Response()

        client = BoundedHttpApiClient(opener=Opener())

        with self.assertRaisesRegex(RuntimeError, "içerik türü"):
            client.execute(ApiRequest(ApiMethod.GET, "https://api.example.com"))

    def test_rejects_redirect_response(self):
        class Response:
            status = 302
            headers = Message()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                del args

        class Opener:
            def open(self, request, timeout):
                del request, timeout
                return Response()

        client = BoundedHttpApiClient(opener=Opener())

        with self.assertRaisesRegex(RuntimeError, "yönlendirmeleri"):
            client.execute(ApiRequest(ApiMethod.GET, "https://api.example.com"))


class ApiCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeApiClient()
        self.coordinator = ControlledApiCoordinator(
            RuleBasedApiRequestParser(),
            SafeApiPolicy(("api.example.com",), resolver=public_resolver),
            self.client,
        )

    def test_get_runs_without_approval(self):
        response = self.coordinator.resolve("api get: https://api.example.com/items")

        self.assertIn("HTTP durum: 200", response or "")
        self.assertEqual(self.client.requests[0].method, ApiMethod.GET)

    def test_post_requires_exact_approval(self):
        prepared = self.coordinator.resolve(
            'api post: https://api.example.com/items | {"name":"Börü"}'
        )
        waiting = self.coordinator.resolve("onayla")
        completed = self.coordinator.resolve("api isteğini onayla")

        self.assertIn("gönderilmedi", prepared or "")
        self.assertIn("Onay bekleyen", waiting or "")
        self.assertIn("HTTP durum: 200", completed or "")
        self.assertEqual(len(self.client.requests), 1)

    def test_pending_request_can_be_cancelled(self):
        self.coordinator.resolve("api delete: https://api.example.com/items/1")

        self.assertEqual(self.coordinator.resolve("iptal"), "API isteği iptal edildi.")
        self.assertEqual(self.client.requests, [])

    def test_empty_allowlist_blocks_network_before_client(self):
        coordinator = ControlledApiCoordinator(
            RuleBasedApiRequestParser(),
            SafeApiPolicy((), resolver=public_resolver),
            self.client,
        )

        response = coordinator.resolve("api get: https://api.example.com/items")

        self.assertIn("izin listesinde değil", response or "")
        self.assertEqual(self.client.requests, [])


class DatabaseToolTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        self.database_path = self.root / "sample.db"
        connection = sqlite3.connect(self.database_path)
        connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        connection.executemany(
            "INSERT INTO users(name) VALUES (?)",
            (("Ada",), ("Linus",)),
        )
        connection.commit()
        connection.close()
        self.service = ReadOnlySqliteService(self.root)
        self.coordinator = DatabaseReadCoordinator(
            RuleBasedDatabaseRequestParser(), self.service
        )

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_lists_schema_describes_and_selects(self):
        tables = self.coordinator.resolve("veritabanı tabloları: sample.db")
        schema = self.coordinator.resolve("veritabanı şema: sample.db")
        description = self.coordinator.resolve(
            "veritabanı tablo açıkla: sample.db | users"
        )
        query = self.coordinator.resolve(
            "veritabanı sorgula: sample.db | SELECT id, name FROM users ORDER BY id"
        )

        self.assertIn("users | table", tables or "")
        self.assertIn("CREATE TABLE users", schema or "")
        self.assertIn("name | TEXT", description or "")
        self.assertIn("1 | Ada", query or "")
        self.assertIn("2 | Linus", query or "")

    def test_rejects_write_pragma_attach_and_multiple_statements(self):
        queries = (
            "DELETE FROM users",
            "PRAGMA table_info(users)",
            "ATTACH DATABASE 'other.db' AS other",
            "SELECT * FROM users; DELETE FROM users",
            "WITH x AS (SELECT 1) DELETE FROM users",
        )

        for sql in queries:
            with self.subTest(sql=sql):
                response = self.coordinator.resolve(
                    f"veritabanı sorgula: sample.db | {sql}"
                )
                self.assertIn("reddedildi", response or "")

        connection = sqlite3.connect(self.database_path)
        count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        connection.close()
        self.assertEqual(count, 2)

    def test_rejects_outside_or_non_sqlite_file(self):
        (self.root / "notes.txt").write_text("not a database", encoding="utf-8")

        outside = self.coordinator.resolve("veritabanı tabloları: ../outside.db")
        wrong_type = self.coordinator.resolve("veritabanı tabloları: notes.txt")

        self.assertIn("reddedildi", outside or "")
        self.assertIn("reddedildi", wrong_type or "")

    def test_row_limit_is_reported(self):
        service = ReadOnlySqliteService(self.root, max_rows=1)
        result = service.query("sample.db", "SELECT name FROM users ORDER BY id")

        self.assertEqual(len(result.rows), 1)
        self.assertTrue(result.truncated)

    def test_corrupt_sqlite_file_returns_controlled_error(self):
        (self.root / "corrupt.db").write_text("not sqlite", encoding="utf-8")

        response = self.coordinator.resolve("veritabanı tabloları: corrupt.db")

        self.assertIn("reddedildi", response or "")


class ExternalToolIntegrationTests(unittest.TestCase):
    def test_api_approval_is_recognized_as_orphan_control_command(self):
        class Resolver:
            has_pending = False

            def resolve(self, message):
                del message
                return None

        coordinator = ExclusiveOperationCoordinator((Resolver(),))

        self.assertIn(
            "etkin bir işlem yok",
            coordinator.resolve("api isteğini onayla") or "",
        )

    def test_external_tool_commands_are_not_memory_candidates(self):
        gate = ConservativeMemoryDecisionGate()

        self.assertFalse(gate.should_evaluate("api get: https://api.example.com"))
        self.assertFalse(
            gate.should_evaluate("veritabanı sorgula: sample.db | SELECT * FROM users")
        )


if __name__ == "__main__":
    unittest.main()
