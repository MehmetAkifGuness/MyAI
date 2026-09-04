import tempfile
import unittest
from pathlib import Path

from boru.tools import (
    ControlledWriteCoordinator,
    LLMProjectFileSelector,
    ProjectEditRequest,
    ProjectFileSelection,
    RiskBasedToolPolicy,
    RuleBasedWriteIntentDetector,
    RuleBasedWriteRequestParser,
    SafeWriteWorkspace,
    ToolExecutor,
    ToolRegistry,
    ToolRisk,
    WriteFileTool,
)
from boru.tools.project_selection import (
    RuleFirstProjectFileSelector,
)


class RaisingSelector:
    def __init__(self):
        self.calls = 0

    def select_files(
        self,
        *,
        request,
        available_paths,
    ):
        del request, available_paths
        self.calls += 1
        raise AssertionError(
            "Fallback selector çağrılmamalıydı."
        )


class RecordingSelector:
    def __init__(
        self,
        selection: ProjectFileSelection,
    ):
        self.selection = selection
        self.calls = 0

    def select_files(
        self,
        *,
        request,
        available_paths,
    ) -> ProjectFileSelection:
        del request, available_paths
        self.calls += 1
        return self.selection


class NeverCalledChatModel:
    def __init__(self):
        self.calls = 0

    def generate(self, messages):
        del messages
        self.calls += 1
        raise AssertionError(
            "LLM çağrılmamalıydı."
        )


class PendingApprovalAndProjectSelectionHotfixTests(
    unittest.TestCase
):
    def test_two_explicit_paths_bypass_fallback_selector(
        self,
    ) -> None:
        fallback = RaisingSelector()

        selector = RuleFirstProjectFileSelector(
            fallback=fallback,
            max_files=4,
            deterministic_min_paths=2,
        )

        request = ProjectEditRequest(
            instruction=(
                "project_config_test.py içindeki FEATURE ayarını true yap "
                "ve project_service_test.py dosyasındaki FEATURE kontrolünü "
                "buna uyumlu hale getir"
            )
        )

        selection = selector.select_files(
            request=request,
            available_paths=(
                "other.py",
                "project_config_test.py",
                "project_service_test.py",
                "tests/test_other.py",
            ),
        )

        self.assertEqual(
            selection.paths,
            (
                "project_config_test.py",
                "project_service_test.py",
            ),
        )
        self.assertEqual(
            fallback.calls,
            0,
        )

    def test_two_explicit_paths_bypass_llm_selector_entirely(
        self,
    ) -> None:
        model = NeverCalledChatModel()

        selector = RuleFirstProjectFileSelector(
            fallback=LLMProjectFileSelector(
                chat_model=model,
                max_files=4,
                max_attempts=2,
            ),
            max_files=4,
            deterministic_min_paths=2,
        )

        selection = selector.select_files(
            request=ProjectEditRequest(
                instruction=(
                    "a.py içindeki ayarı değiştir ve b.py dosyasını güncelle"
                )
            ),
            available_paths=(
                "a.py",
                "b.py",
                "c.py",
            ),
        )

        self.assertEqual(
            selection.paths,
            (
                "a.py",
                "b.py",
            ),
        )
        self.assertEqual(
            model.calls,
            0,
        )

    def test_single_explicit_path_can_delegate_for_project_discovery(
        self,
    ) -> None:
        fallback = RecordingSelector(
            ProjectFileSelection(
                paths=(
                    "config.py",
                    "service.py",
                )
            )
        )

        selector = RuleFirstProjectFileSelector(
            fallback=fallback,
            max_files=4,
            deterministic_min_paths=2,
        )

        selection = selector.select_files(
            request=ProjectEditRequest(
                instruction=(
                    "config.py içindeki ayarı değiştir ve bunu kullanan servisi güncelle"
                )
            ),
            available_paths=(
                "config.py",
                "service.py",
            ),
        )

        self.assertEqual(
            fallback.calls,
            1,
        )
        self.assertEqual(
            selection.paths,
            (
                "config.py",
                "service.py",
            ),
        )

    def test_fallback_must_keep_single_explicit_path(
        self,
    ) -> None:
        fallback = RecordingSelector(
            ProjectFileSelection(
                paths=(
                    "service.py",
                )
            )
        )

        selector = RuleFirstProjectFileSelector(
            fallback=fallback,
            max_files=4,
            deterministic_min_paths=2,
        )

        with self.assertRaisesRegex(
            ValueError,
            "açıkça belirtilen",
        ):
            selector.select_files(
                request=ProjectEditRequest(
                    instruction=(
                        "config.py içindeki ayarı değiştir ve ilgili servisi güncelle"
                    )
                ),
                available_paths=(
                    "config.py",
                    "service.py",
                ),
            )

    def test_more_than_max_explicit_paths_is_fail_closed(
        self,
    ) -> None:
        selector = RuleFirstProjectFileSelector(
            fallback=RaisingSelector(),
            max_files=4,
            deterministic_min_paths=2,
        )

        with self.assertRaisesRegex(
            ValueError,
            "sınırını aşıyor",
        ):
            selector.select_files(
                request=ProjectEditRequest(
                    instruction=(
                        "a.py b.py c.py d.py e.py dosyalarını güncelle"
                    )
                ),
                available_paths=(
                    "a.py",
                    "b.py",
                    "c.py",
                    "d.py",
                    "e.py",
                ),
            )

    def test_typo_during_pending_create_does_not_execute_or_fall_through(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            coordinator = self._build_create_coordinator(
                root
            )

            staged = coordinator.resolve(
                "dosya oluştur: project_service_test.py\n"
                "İçerik:\n"
                "hello"
            )

            self.assertIn(
                "henüz uygulanmadı",
                staged or "",
            )

            typo_response = coordinator.resolve(
                "onayşa"
            )

            self.assertEqual(
                typo_response,
                (
                    "Zaten onay bekleyen bir dosya değişikliği var. "
                    "Önce 'onayla' veya 'iptal' demelisin."
                ),
            )
            self.assertFalse(
                (root / "project_service_test.py").exists()
            )

            approved = coordinator.resolve(
                "onayla"
            )

            self.assertEqual(
                approved,
                "Dosya oluşturuldu: project_service_test.py",
            )
            self.assertEqual(
                (root / "project_service_test.py").read_text(
                    encoding="utf-8"
                ),
                "hello",
            )

    def test_any_unknown_message_is_locked_while_pending(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            coordinator = self._build_create_coordinator(
                Path(directory)
            )

            coordinator.resolve(
                "dosya oluştur: a.txt\n"
                "İçerik:\n"
                "x"
            )

            response = coordinator.resolve(
                "merhaba"
            )

            self.assertIn(
                "onay bekleyen",
                response or "",
            )

    @staticmethod
    def _build_create_coordinator(
        root: Path,
    ) -> ControlledWriteCoordinator:
        registry = ToolRegistry(
            [
                WriteFileTool(
                    SafeWriteWorkspace(
                        root
                    )
                )
            ]
        )

        executor = ToolExecutor(
            registry=registry,
            policy=RiskBasedToolPolicy(
                allowed_risks=(
                    ToolRisk.WRITE,
                )
            ),
        )

        return ControlledWriteCoordinator(
            parser=RuleBasedWriteRequestParser(),
            intent_detector=(
                RuleBasedWriteIntentDetector()
            ),
            executor=executor,
        )


if __name__ == "__main__":
    unittest.main()