import tempfile
import unittest
from pathlib import Path

from boru.reflection.context_provider import ReflectionContextProvider
from boru.reflection.engine import SelfReflectionEngine
from boru.reflection.models import ReflectionRecord, ReflectionVerdict
from boru.reflection.repository import JsonReflectionRepository


class SelfReflectionLoopTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_path = Path(self.temp_dir.name) / "reflections.json"
        self.repo = JsonReflectionRepository(self.storage_path, max_records=5)
        self.engine = SelfReflectionEngine(self.repo)
        self.context_provider = ReflectionContextProvider(self.engine, max_lessons=3)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_record_success_and_read_back(self):
        record = self.engine.record_success(
            task="hata onarımı",
            paths=["boru/models.py"],
            summary="None kontrolü başarıyla eklendi",
        )
        self.assertEqual(record.verdict, ReflectionVerdict.PASS)
        self.assertEqual(record.target_paths, ("boru/models.py",))

        records = self.repo.read_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].task, "hata onarımı")
        self.assertEqual(records[0].verdict, ReflectionVerdict.PASS)

    def test_record_failure_and_rollback(self):
        fail_rec = self.engine.record_failure(
            task="refactoring",
            paths=["boru/config.py"],
            error_or_report="SyntaxError: invalid syntax",
        )
        self.assertEqual(fail_rec.verdict, ReflectionVerdict.FAIL)
        self.assertIn("DİKKAT", fail_rec.lesson)

        rollback_rec = self.engine.record_rollback(
            paths=["boru/config.py"],
            reason="kullanıcı onaylamadı",
        )
        self.assertEqual(rollback_rec.verdict, ReflectionVerdict.ROLLBACK)
        self.assertIn("UYARI", rollback_rec.lesson)

        records = self.repo.read_records()
        self.assertEqual(len(records), 2)

    def test_query_by_paths(self):
        self.engine.record_success("görev 1", ["a.py", "b.py"], "a ve b onarıldı")
        self.engine.record_failure("görev 2", ["c.py"], "c patladı")
        self.engine.record_success("görev 3", ["b.py"], "b optimize edildi")

        b_records = self.repo.query_by_paths(("b.py",))
        self.assertEqual(len(b_records), 2)
        # En güncel kayıt ilk sırada olmalı
        self.assertEqual(b_records[0].task, "görev 3")
        self.assertEqual(b_records[1].task, "görev 1")

    def test_context_provider_injects_matching_lessons(self):
        self.engine.record_failure("test task", ["main.py"], "fonksiyon bulunamadı")
        context = self.context_provider.build_context("main.py üzerinde çalış")

        self.assertIn("[Öz-İyileştirme Hafızası", context)
        self.assertIn("[FAIL]", context)
        self.assertIn("fonksiyon bulunamadı", context)

    def test_context_provider_empty_when_no_records(self):
        context = self.context_provider.build_context("dosya.py düzenle")
        self.assertEqual(context, "")

    def test_max_records_trimming(self):
        for i in range(10):
            self.engine.record_success(f"task {i}", [f"file_{i}.py"])

        records = self.repo.read_records()
        self.assertEqual(len(records), 5)  # max_records=5
        self.assertEqual(records[-1].task, "task 9")


if __name__ == "__main__":
    unittest.main()
