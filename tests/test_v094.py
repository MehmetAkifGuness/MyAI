import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from boru.memory.models import MemoryRecord
from boru.memory.repository import JsonMemoryRepository
from boru.profile.models import UserProfile
from boru.profile.repository import JsonUserProfileRepository


class RepositoryRobustnessTests(
    unittest.TestCase
):
    @staticmethod
    def _memory_record(
        memory_id: str = "memory-1",
        content: str = "Calculator API projem pytest kullanıyor.",
        value: str = "pytest",
    ) -> MemoryRecord:
        return MemoryRecord(
            memory_id=memory_id,
            content=content,
            created_at="2026-09-04T00:00:00+00:00",
            updated_at="2026-09-04T00:00:00+00:00",
            subject="Calculator API",
            relation="test_framework",
            value=value,
        )

    def test_memory_repository_reads_utf8_bom_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            record = self._memory_record()

            path.write_text(
                json.dumps(
                    [record.to_dict()],
                    ensure_ascii=False,
                ),
                encoding="utf-8-sig",
            )

            loaded = JsonMemoryRepository(
                path
            ).load_all()

            self.assertEqual(
                loaded,
                [record],
            )

    def test_profile_repository_reads_utf8_bom_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"

            path.write_text(
                json.dumps(
                    {
                        "name": "Deneme",
                        "preferences": {
                            "favorite_color": "mavi",
                        },
                        "facts": {},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8-sig",
            )

            profile = (
                JsonUserProfileRepository(
                    path
                ).load()
            )

            self.assertEqual(
                profile.name,
                "Deneme",
            )

            self.assertEqual(
                profile.preferences[
                    "favorite_color"
                ],
                "mavi",
            )

    def test_memory_repository_writes_bomless_utf8(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"

            JsonMemoryRepository(
                path
            ).save_all(
                [self._memory_record()]
            )

            content = path.read_bytes()

            self.assertFalse(
                content.startswith(
                    b"\xef\xbb\xbf"
                )
            )

            decoded = content.decode(
                "utf-8"
            )

            self.assertIn(
                "Calculator API",
                decoded,
            )

    def test_profile_repository_writes_bomless_utf8(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"

            repository = (
                JsonUserProfileRepository(
                    path
                )
            )

            repository.save(
                UserProfile(
                    name="Deneme",
                    preferences={
                        "favorite_color": "mavi",
                    },
                )
            )

            content = path.read_bytes()

            self.assertFalse(
                content.startswith(
                    b"\xef\xbb\xbf"
                )
            )

            self.assertIn(
                "Deneme",
                content.decode("utf-8"),
            )

    def test_memory_repository_reports_invalid_json(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"

            path.write_text(
                "[invalid-json",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "Uzun süreli hafıza okunamadı",
            ):
                JsonMemoryRepository(
                    path
                ).load_all()

    def test_profile_repository_reports_invalid_json(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"

            path.write_text(
                "{invalid-json",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "Kullanıcı profili okunamadı",
            ):
                JsonUserProfileRepository(
                    path
                ).load()

    def test_failed_memory_replace_preserves_original_and_cleans_temp(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            repository = JsonMemoryRepository(
                path
            )

            original = self._memory_record()

            repository.save_all(
                [original]
            )

            original_bytes = (
                path.read_bytes()
            )

            updated = self._memory_record(
                memory_id="memory-2",
                content=(
                    "Calculator API projem "
                    "unittest kullanıyor."
                ),
                value="unittest",
            )

            with patch(
                "boru.persistence.json_file.os.replace",
                side_effect=OSError(
                    "replace failed"
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "Uzun süreli hafıza yazılamadı",
                ):
                    repository.save_all(
                        [updated]
                    )

            self.assertEqual(
                path.read_bytes(),
                original_bytes,
            )

            self.assertEqual(
                list(
                    Path(directory).glob(
                        ".memory.json.*.tmp"
                    )
                ),
                [],
            )

    def test_missing_files_keep_existing_repository_defaults(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            memories = JsonMemoryRepository(
                root / "missing-memory.json"
            ).load_all()

            profile = (
                JsonUserProfileRepository(
                    root / "missing-profile.json"
                ).load()
            )

            self.assertEqual(
                memories,
                [],
            )

            self.assertEqual(
                profile,
                UserProfile(),
            )


if __name__ == "__main__":
    unittest.main()