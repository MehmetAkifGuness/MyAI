import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

from boru.models import ChatMessage
from boru.tools import (
    LLMSmartEditProposalPreparer,
    RuleBasedSmartEditRequestParser,
    SafeEditWorkspace,
)


class SequenceChatModel:
    def __init__(
        self,
        responses: Sequence[str],
    ):
        self._responses = list(
            responses
        )

        self.calls: list[
            list[ChatMessage]
        ] = []

    def generate(
        self,
        messages: Sequence[
            ChatMessage
        ],
    ) -> str:
        self.calls.append(
            list(messages)
        )

        if not self._responses:
            raise AssertionError(
                "Beklenmeyen ek model çağrısı."
            )

        return self._responses.pop(
            0
        )


class MutatingAfterFirstFailureModel:
    def __init__(
        self,
        target: Path,
    ):
        self._target = target
        self.calls = 0

    def generate(
        self,
        messages: Sequence[
            ChatMessage
        ],
    ) -> str:
        del messages

        self.calls += 1

        if self.calls == 1:
            self._target.write_text(
                'model = "external"\n',
                encoding="utf-8",
            )

            return (
                "JSON veremiyorum."
            )

        raise AssertionError(
            "Kaynak değiştiyse ikinci "
            "model çağrısı yapılmamalı."
        )


class SmartEditRepairRetryTests(
    unittest.TestCase
):
    def test_invalid_first_output_is_repaired_on_second_attempt(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            target = (
                root
                / "smart_edit_test.txt"
            )

            target.write_text(
                'model = "old"\n',
                encoding="utf-8",
            )

            model = (
                SequenceChatModel(
                    [
                        (
                            "Model değerini "
                            "new yapmalısın."
                        ),
                        (
                            '{"old_text":"model = \\"old\\"",'
                            '"new_text":"model = \\"new\\"",'
                            '"reason":"değeri güncelle"}'
                        ),
                    ]
                )
            )

            request = (
                RuleBasedSmartEditRequestParser()
                .parse(
                    "smart_edit_test.txt'deki "
                    "model değerini new yap"
                )
            )

            proposal = (
                LLMSmartEditProposalPreparer(
                    chat_model=model,
                    workspace=(
                        SafeEditWorkspace(
                            root
                        )
                    ),
                )
                .prepare_smart_edit(
                    request  # type: ignore[arg-type]
                )
            )

            self.assertEqual(
                len(model.calls),
                2,
            )

            self.assertIn(
                'model = "new"',
                proposal.updated_content,
            )

            self.assertEqual(
                target.read_text(
                    encoding="utf-8"
                ),
                'model = "old"\n',
            )

    def test_grounding_failure_is_repaired_on_second_attempt(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            target = (
                root
                / "a.txt"
            )

            target.write_text(
                "real\n",
                encoding="utf-8",
            )

            model = (
                SequenceChatModel(
                    [
                        (
                            '{"old_text":"fake",'
                            '"new_text":"new"}'
                        ),
                        (
                            '{"old_text":"real",'
                            '"new_text":"new"}'
                        ),
                    ]
                )
            )

            request = (
                RuleBasedSmartEditRequestParser()
                .parse(
                    "a.txt'deki real "
                    "değerini new yap"
                )
            )

            proposal = (
                LLMSmartEditProposalPreparer(
                    chat_model=model,
                    workspace=(
                        SafeEditWorkspace(
                            root
                        )
                    ),
                )
                .prepare_smart_edit(
                    request  # type: ignore[arg-type]
                )
            )

            self.assertEqual(
                len(model.calls),
                2,
            )

            expected_newline = (
                "\r\n"
                if "\r\n" in target.read_text(
                    encoding="utf-8",
                    newline="",
                )
                else "\n"
            )

            self.assertEqual(
                proposal.updated_content,
                f"new{expected_newline}",
            )

    def test_two_invalid_outputs_fail_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            (
                root
                / "a.txt"
            ).write_text(
                "old\n",
                encoding="utf-8",
            )

            model = (
                SequenceChatModel(
                    [
                        "not json",
                        "still not json",
                    ]
                )
            )

            request = (
                RuleBasedSmartEditRequestParser()
                .parse(
                    "a.txt'deki old "
                    "değerini new yap"
                )
            )

            with self.assertRaisesRegex(
                ValueError,
                "geçerli ve grounded",
            ):
                LLMSmartEditProposalPreparer(
                    chat_model=model,
                    workspace=(
                        SafeEditWorkspace(
                            root
                        )
                    ),
                ).prepare_smart_edit(
                    request  # type: ignore[arg-type]
                )

            self.assertEqual(
                len(model.calls),
                2,
            )

            self.assertEqual(
                (
                    root
                    / "a.txt"
                ).read_text(
                    encoding="utf-8"
                ),
                "old\n",
            )

    def test_max_attempts_one_disables_retry(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            (
                root
                / "a.txt"
            ).write_text(
                "old\n",
                encoding="utf-8",
            )

            model = (
                SequenceChatModel(
                    [
                        "not json"
                    ]
                )
            )

            request = (
                RuleBasedSmartEditRequestParser()
                .parse(
                    "a.txt'deki old "
                    "değerini new yap"
                )
            )

            with self.assertRaises(
                ValueError
            ):
                LLMSmartEditProposalPreparer(
                    chat_model=model,
                    workspace=(
                        SafeEditWorkspace(
                            root
                        )
                    ),
                    max_attempts=1,
                ).prepare_smart_edit(
                    request  # type: ignore[arg-type]
                )

            self.assertEqual(
                len(model.calls),
                1,
            )

    def test_invalid_max_attempts_is_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                ValueError,
                "max_attempts",
            ):
                LLMSmartEditProposalPreparer(
                    chat_model=(
                        SequenceChatModel(
                            []
                        )
                    ),
                    workspace=(
                        SafeEditWorkspace(
                            directory
                        )
                    ),
                    max_attempts=0,
                )

    def test_sensitive_file_is_still_blocked_before_any_model_call(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            (
                root
                / ".env"
            ).write_text(
                "SECRET=x\n",
                encoding="utf-8",
            )

            model = (
                SequenceChatModel(
                    []
                )
            )

            request = (
                RuleBasedSmartEditRequestParser()
                .parse(
                    ".env'deki SECRET "
                    "değerini y yap"
                )
            )

            with self.assertRaisesRegex(
                ValueError,
                "Hassas",
            ):
                LLMSmartEditProposalPreparer(
                    chat_model=model,
                    workspace=(
                        SafeEditWorkspace(
                            root
                        )
                    ),
                ).prepare_smart_edit(
                    request  # type: ignore[arg-type]
                )

            self.assertEqual(
                model.calls,
                [],
            )

    def test_source_change_after_failed_first_attempt_stops_retry(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            target = (
                root
                / "a.txt"
            )

            target.write_text(
                'model = "old"\n',
                encoding="utf-8",
            )

            model = (
                MutatingAfterFirstFailureModel(
                    target
                )
            )

            request = (
                RuleBasedSmartEditRequestParser()
                .parse(
                    "a.txt'deki model "
                    "değerini new yap"
                )
            )

            with self.assertRaisesRegex(
                ValueError,
                "yeniden denenmeden önce değişmiş",
            ):
                LLMSmartEditProposalPreparer(
                    chat_model=model,
                    workspace=(
                        SafeEditWorkspace(
                            root
                        )
                    ),
                ).prepare_smart_edit(
                    request  # type: ignore[arg-type]
                )

            self.assertEqual(
                model.calls,
                1,
            )

            self.assertEqual(
                target.read_text(
                    encoding="utf-8"
                ),
                'model = "external"\n',
            )

    def test_repair_prompt_is_explicitly_json_only(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            (
                root
                / "a.txt"
            ).write_text(
                "old\n",
                encoding="utf-8",
            )

            model = (
                SequenceChatModel(
                    [
                        "not json",
                        (
                            '{"old_text":"old",'
                            '"new_text":"new",'
                            '"reason":"x"}'
                        ),
                    ]
                )
            )

            request = (
                RuleBasedSmartEditRequestParser()
                .parse(
                    "a.txt'deki old "
                    "değerini new yap"
                )
            )

            LLMSmartEditProposalPreparer(
                chat_model=model,
                workspace=(
                    SafeEditWorkspace(
                        root
                    )
                ),
            ).prepare_smart_edit(
                request  # type: ignore[arg-type]
            )

            repair_prompt = (
                model.calls[
                    1
                ][
                    1
                ].content
            )

            self.assertIn(
                "GEÇERLİ JSON",
                repair_prompt,
            )

            self.assertIn(
                "JSON dışında hiçbir karakter üretme",
                repair_prompt,
            )

            self.assertIn(
                "<BORU_INVALID_EDIT_OUTPUT>",
                repair_prompt,
            )


if __name__ == "__main__":
    unittest.main()