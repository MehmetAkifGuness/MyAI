import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main_v170
from boru.code_index import SafeCodeIndex
from boru.improvement import (
    NaturalLanguageImprovementCoordinator,
    SafeChangeScopeResolver,
)
from boru.release import build_release


class FakeImprovementWorkflow:
    def __init__(self, approval_results=()):
        self.pending = False
        self.calls = []
        self.approval_results = list(approval_results)

    @property
    def has_pending(self):
        return self.pending

    def resolve(self, message):
        self.calls.append(message)
        normalized = " ".join(message.casefold().split())
        if normalized.startswith("iyileştir:"):
            self.pending = True
            return "İYİLEŞTİRME ÖNERİSİ\nOnay: iyileştirmeyi onayla"
        if self.pending and normalized == "iyileştirmeyi onayla":
            self.pending = False
            if self.approval_results:
                return self.approval_results.pop(0)
            return "Coding Agent değişikliği uygulandı: 1 dosya"
        if self.pending and normalized in {"iptal", "vazgeç"}:
            self.pending = False
            return "İyileştirme iptal edildi."
        if self.pending:
            return "İyileştirme onay bekliyor."
        return None


class SafeChangeScopeResolverTests(unittest.TestCase):
    def test_resolves_explicit_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
            resolver = SafeChangeScopeResolver(root, SafeCodeIndex(root))

            scope = resolver.resolve("sample.py dosyasındaki VALUE değerini 2 yap")

            self.assertEqual(scope.paths, ("sample.py",))
            self.assertIn("açık dosya kapsamı", scope.evidence[0])

    def test_resolves_unique_class_symbol_without_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "service.py").write_text(
                "class UniqueService:\n    pass\n",
                encoding="utf-8",
            )
            resolver = SafeChangeScopeResolver(root, SafeCodeIndex(root))

            scope = resolver.resolve("UniqueService sınıfına açıklama ekle")

            self.assertEqual(scope.paths, ("service.py",))
            self.assertIn("UniqueService", scope.evidence[0])

    def test_rejects_missing_explicit_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resolver = SafeChangeScopeResolver(root, SafeCodeIndex(root))

            with self.assertRaisesRegex(ValueError, "manifestinde bulunamadı"):
                resolver.resolve("missing.py içindeki VALUE değerini değiştir")


class NaturalLanguageImprovementCoordinatorTests(unittest.TestCase):
    def _coordinator(self, root, workflow, **kwargs):
        return NaturalLanguageImprovementCoordinator(
            workflow,
            SafeChangeScopeResolver(root, SafeCodeIndex(root)),
            **kwargs,
        )

    def test_routes_natural_request_to_approved_improvement_flow(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
            workflow = FakeImprovementWorkflow()
            coordinator = self._coordinator(root, workflow)

            report = coordinator.resolve("sample.py içindeki VALUE değerini 2 yap")

            self.assertIn("DOĞAL DİL AJAN AKIŞI", report)
            self.assertIn("Güvenli kapsam: sample.py", report)
            self.assertTrue(coordinator.has_pending)
            self.assertEqual(
                workflow.calls[0],
                "iyileştir: sample.py | sample.py içindeki VALUE değerini 2 yap",
            )
            self.assertIn("onay bekliyor", coordinator.resolve("onayla").casefold())
            result = coordinator.resolve("iyileştirmeyi onayla")
            self.assertIn("uygulandı", result)
            self.assertFalse(coordinator.has_pending)

    def test_does_not_capture_read_only_question(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "runtime.py").write_text(
                "class ReadOnlyToolAgent:\n    pass\n",
                encoding="utf-8",
            )
            coordinator = self._coordinator(root, FakeImprovementWorkflow())

            self.assertIsNone(
                coordinator.resolve("ReadOnlyToolAgent kanıtsız finali nasıl engelliyor?")
            )

    def test_failed_candidate_prepares_one_new_approved_proposal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
            workflow = FakeImprovementWorkflow(
                ["Coding Agent değişikliği uygulanamadı: geçici değerlendirme testi başarısız."]
            )
            coordinator = self._coordinator(root, workflow, max_retries=1)
            coordinator.resolve("sample.py içindeki VALUE değerini düzelt")

            report = coordinator.resolve("iyileştirmeyi onayla")

            self.assertIn("YENİDEN ÖNERİ", report)
            self.assertIn("kaynak dosyalara uygulanmadı", report)
            self.assertTrue(coordinator.has_pending)
            self.assertEqual(sum(call.startswith("iyileştir:") for call in workflow.calls), 2)


class ReleaseV130Tests(unittest.TestCase):
    def test_natural_change_requires_controlled_improvement(self):
        with self.assertRaisesRegex(ValueError, "kontrollü iyileştirme"):
            main_v170.build_application(natural_change_enabled=True)

    def test_v130_release_enables_natural_change_flow(self):
        with patch.object(main_v170, "build_application", return_value="app") as builder:
            self.assertEqual(build_release("V1.3"), "app")
            flags = builder.call_args.kwargs
            self.assertEqual(flags["application_version"], "V1.3")
            self.assertTrue(flags["improvement_enabled"])
            self.assertTrue(flags["general_agent_enabled"])
            self.assertTrue(flags["deep_code_index_enabled"])
            self.assertTrue(flags["natural_change_enabled"])


if __name__ == "__main__":
    unittest.main()
