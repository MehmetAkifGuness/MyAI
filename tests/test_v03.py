import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

from boru.assistant import (
    AssistantService,
)
from boru.conversation import (
    ConversationHistory,
)
from boru.models import (
    ChatMessage,
)
from boru.profile import (
    JsonUserProfileRepository,
    ProfileContextProvider,
    ProfileObserver,
    RuleBasedProfileExtractor,
    UserProfileService,
)
from boru.prompts import (
    SystemPromptFactory,
)


class RecordingChatModel:
    def __init__(
        self,
        responses: list[str],
    ):
        self._responses = iter(
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

        return next(
            self._responses
        )


class ProfileTests(
    unittest.TestCase
):
    @staticmethod
    def _create_service(
        path: Path,
    ) -> UserProfileService:
        return UserProfileService(
            repository=(
                JsonUserProfileRepository(
                    path
                )
            ),
            extractor=(
                RuleBasedProfileExtractor()
            ),
        )

    def test_name_persists_across_service_restart(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "profile.json"
            )

            service = (
                self._create_service(
                    path
                )
            )

            service.observe(
                (
                    "Benim adım "
                    "Mehmet Akif."
                )
            )

            restarted_service = (
                self._create_service(
                    path
                )
            )

            self.assertIn(
                "Mehmet Akif",
                restarted_service
                .build_context(),
            )

    def test_favorite_color_persists(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "profile.json"
            )

            service = (
                self._create_service(
                    path
                )
            )

            service.observe(
                (
                    "Benim favori "
                    "rengim mavi."
                )
            )

            context = (
                service.build_context()
            )

            self.assertIn(
                "favorite_color",
                context,
            )

            self.assertIn(
                "mavi",
                context,
            )

    def test_transient_statement_is_not_persisted(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "profile.json"
            )

            service = (
                self._create_service(
                    path
                )
            )

            updates = service.observe(
                (
                    "Bugün Python "
                    "çalışıyorum."
                )
            )

            self.assertEqual(
                updates,
                [],
            )

            self.assertFalse(
                path.exists()
            )

    def test_profile_questions_do_not_overwrite_values(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "profile.json"
            )

            service = (
                self._create_service(
                    path
                )
            )

            service.observe(
                "Benim adım Mehmet."
            )

            service.observe(
                "Benim adım neydi?"
            )

            service.observe(
                (
                    "Favori rengim "
                    "neydi?"
                )
            )

            context = (
                service.build_context()
            )

            self.assertIn(
                "Mehmet",
                context,
            )

            self.assertNotIn(
                "neydi",
                context.casefold(),
            )

    def test_assistant_injects_saved_profile_context(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "profile.json"
            )

            profile_service = (
                self._create_service(
                    path
                )
            )

            profile_service.observe(
                (
                    "Benim favori "
                    "rengim mavi."
                )
            )

            model = RecordingChatModel(
                [
                    (
                        "Favori rengin "
                        "mavi."
                    )
                ]
            )

            assistant = (
                AssistantService(
                    chat_model=model,
                    conversation_history=(
                        ConversationHistory()
                    ),
                    prompt_factory=(
                        SystemPromptFactory(
                            "Börü"
                        )
                    ),
                    message_observers=[
                        ProfileObserver(
                            profile_service
                        )
                    ],
                    context_providers=[
                        ProfileContextProvider(
                            profile_service
                        )
                    ],
                )
            )

            assistant.reply(
                (
                    "Favori rengim "
                    "neydi?"
                )
            )

            system_messages = [
                message.content
                for message
                in model.calls[0]
                if (
                    message.role
                    == "system"
                )
            ]

            self.assertTrue(
                any(
                    "mavi" in message
                    for message
                    in system_messages
                )
            )


if __name__ == "__main__":
    unittest.main()