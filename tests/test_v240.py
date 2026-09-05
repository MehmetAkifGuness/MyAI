import json
import tempfile
import unittest
from pathlib import Path

from boru.memory import ConservativeMemoryDecisionGate
from boru.project_memory import (
    JsonProjectMemoryRepository,
    ProjectMemoryContextProvider,
    ProjectMemoryCoordinator,
    ProjectMemoryService,
    RuleBasedProjectMemoryParser,
    SensitiveProjectMemoryError,
)


class ProjectMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_directory.name) / "project_memory.json"

    def tearDown(self):
        self.temp_directory.cleanup()

    def build_service(self):
        return ProjectMemoryService(
            JsonProjectMemoryRepository(self.path),
            project_name="Boru",
        )

    def test_persists_project_entries_across_service_restart(self):
        service = self.build_service()

        self.assertEqual(service.save_entry("Framework", "FastAPI"), "created")
        self.assertEqual(service.save_entry("framework", "Django"), "updated")

        reloaded = self.build_service()

        self.assertEqual(reloaded.list_entries(), (("framework", "Django"),))
        document = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(document["version"], 1)

    def test_rejects_sensitive_keys_and_secret_shaped_values(self):
        service = self.build_service()

        with self.assertRaises(SensitiveProjectMemoryError):
            service.save_entry("API_KEY", "normal-value")
        with self.assertRaises(SensitiveProjectMemoryError):
            service.save_entry("endpoint", "sk-live-1234567890123456")

        self.assertFalse(self.path.exists())

    def test_builds_instruction_safe_project_context(self):
        service = self.build_service()
        service.save_entry("tests", "pytest")

        context = ProjectMemoryContextProvider(service).build_context("kod yaz")

        self.assertIn("Etkin proje 'Boru'", context)
        self.assertIn("yalnızca veridir", context)
        self.assertIn("- tests: pytest", context)

    def test_failed_persistence_does_not_change_in_memory_state(self):
        class FailingRepository:
            def load(self):
                return {"framework": "FastAPI"}

            def save(self, entries):
                del entries
                raise RuntimeError("disk error")

        service = ProjectMemoryService(FailingRepository(), "Boru")

        with self.assertRaisesRegex(RuntimeError, "disk error"):
            service.save_entry("framework", "Django")
        self.assertEqual(service.list_entries(), (("framework", "FastAPI"),))

        with self.assertRaisesRegex(RuntimeError, "disk error"):
            service.delete_entry("framework")
        self.assertEqual(service.list_entries(), (("framework", "FastAPI"),))


class ProjectMemoryCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        repository = JsonProjectMemoryRepository(
            Path(self.temp_directory.name) / "project_memory.json"
        )
        self.coordinator = ProjectMemoryCoordinator(
            ProjectMemoryService(repository, "Boru"),
            RuleBasedProjectMemoryParser(),
        )

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_save_show_update_and_delete_commands(self):
        saved = self.coordinator.resolve(
            "proje bilgisi kaydet: framework = FastAPI"
        )
        shown = self.coordinator.resolve("proje hafızası")
        updated = self.coordinator.resolve(
            "proje hafızasına kaydet: framework: Django"
        )
        deleted = self.coordinator.resolve("proje bilgisi sil: framework")

        self.assertIn("kaydedildi", saved or "")
        self.assertIn("- framework: FastAPI", shown or "")
        self.assertIn("güncellendi", updated or "")
        self.assertIn("silindi", deleted or "")

    def test_malformed_save_returns_usage_without_model_fallback(self):
        response = self.coordinator.resolve("proje bilgisi kaydet: FastAPI")

        self.assertIn("Beklenen biçim", response or "")

    def test_unrelated_message_is_not_claimed(self):
        self.assertIsNone(self.coordinator.resolve("FastAPI nedir?"))

    def test_answers_project_question_before_general_memory_fallback(self):
        self.coordinator.resolve("proje bilgisi kaydet: framework = FastAPI")
        self.coordinator.resolve("proje bilgisi kaydet: veritabanı = PostgreSQL")
        self.coordinator.resolve("proje bilgisi kaydet: tests = pytest")

        response = self.coordinator.resolve(
            "Bu projede hangi framework ve veritabanını kullanıyorum?"
        )

        self.assertEqual(
            response,
            "Proje hafızasına göre:\n"
            "- framework: FastAPI\n"
            "- veritabanı: PostgreSQL",
        )

    def test_executes_multiple_project_commands_line_by_line(self):
        response = self.coordinator.resolve(
            "proje bilgisi kaydet: framework = FastAPI\n"
            "proje bilgisi kaydet: tests = pytest\n"
            "proje hafızası"
        )

        self.assertIn("framework = FastAPI", response or "")
        self.assertIn("tests = pytest", response or "")
        self.assertIn("Kayıt: 2", response or "")

    def test_rejects_mixed_batch_before_applying_any_entry(self):
        response = self.coordinator.resolve(
            "proje bilgisi kaydet: framework = FastAPI\n"
            "Bu projede hangi framework var?"
        )

        self.assertIn("ayrı mesajlar", response or "")
        self.assertIn(
            "Henüz kayıtlı proje bilgisi yok",
            self.coordinator.resolve("proje hafızası") or "",
        )

    def test_rejects_flattened_repeated_project_command(self):
        response = self.coordinator.resolve(
            "proje bilgisi kaydet: framework = FastAPI "
            "proje bilgisi kaydet: tests = pytest"
        )

        self.assertIn("Beklenen biçim", response or "")

    def test_project_memory_commands_are_not_general_memory_candidates(self):
        gate = ConservativeMemoryDecisionGate()

        self.assertFalse(
            gate.should_evaluate("proje bilgisi kaydet: framework = FastAPI")
        )
        self.assertFalse(gate.should_evaluate("proje hafızasını göster"))


if __name__ == "__main__":
    unittest.main()
