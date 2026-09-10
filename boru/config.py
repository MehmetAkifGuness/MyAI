import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AppSettings:
    model_name: str = "llama3.1"
    assistant_name: str = "Börü"
    history_turns: int = 50
    context_turns: int = 10
    context_max_characters: int = 12_000
    profile_path: str = "data/user_profile.json"
    memory_path: str = "data/long_term_memory.json"
    project_memory_path: str = "data/project_memory.json"
    knowledge_path: str = "data/knowledge_index.json"
    task_checkpoint_path: str = "data/task_checkpoint.json"
    api_allowed_hosts: tuple[str, ...] = ()
    memory_context_limit: int = 5
    memory_auto_capture: bool = True
    memory_semantic_enabled: bool = True
    memory_embedding_model: str = "qwen3-embedding:0.6b"
    memory_semantic_min_similarity: float = 0.55
    memory_subject_identity_min_similarity: float = 0.84
    fallback_model_name: str = ""
    chat_model_name: str = ""

    @classmethod
    def from_env(cls) -> "AppSettings":
        defaults = cls()

        model_name = os.getenv(
            "BORU_MODEL",
            defaults.model_name,
        ).strip()

        fallback_model_name = os.getenv(
            "BORU_FALLBACK_MODEL",
            defaults.fallback_model_name,
        ).strip()

        assistant_name = os.getenv(
            "BORU_ASSISTANT_NAME",
            defaults.assistant_name,
        ).strip()

        profile_path = os.getenv(
            "BORU_PROFILE_PATH",
            defaults.profile_path,
        ).strip()

        memory_path = os.getenv(
            "BORU_MEMORY_PATH",
            defaults.memory_path,
        ).strip()

        project_memory_path = os.getenv(
            "BORU_PROJECT_MEMORY_PATH",
            defaults.project_memory_path,
        ).strip()

        knowledge_path = os.getenv(
            "BORU_KNOWLEDGE_PATH",
            defaults.knowledge_path,
        ).strip()

        task_checkpoint_path = os.getenv(
            "BORU_TASK_CHECKPOINT_PATH",
            defaults.task_checkpoint_path,
        ).strip()

        api_allowed_hosts = tuple(
            host.strip()
            for host in os.getenv("BORU_API_ALLOWED_HOSTS", "").split(",")
            if host.strip()
        )

        memory_embedding_model = os.getenv(
            "BORU_MEMORY_EMBEDDING_MODEL",
            defaults.memory_embedding_model,
        ).strip()

        history_turns = cls._read_positive_integer(
            "BORU_HISTORY_TURNS",
            defaults.history_turns,
        )

        context_turns = cls._read_positive_integer(
            "BORU_CONTEXT_TURNS",
            defaults.context_turns,
        )

        context_max_characters = cls._read_positive_integer(
            "BORU_CONTEXT_MAX_CHARACTERS",
            defaults.context_max_characters,
        )

        memory_context_limit = cls._read_positive_integer(
            "BORU_MEMORY_CONTEXT_LIMIT",
            defaults.memory_context_limit,
        )

        memory_auto_capture = cls._read_boolean(
            "BORU_MEMORY_AUTO_CAPTURE",
            defaults.memory_auto_capture,
        )

        memory_semantic_enabled = cls._read_boolean(
            "BORU_MEMORY_SEMANTIC_ENABLED",
            defaults.memory_semantic_enabled,
        )

        memory_semantic_min_similarity = cls._read_unit_float(
            "BORU_MEMORY_SEMANTIC_MIN_SIMILARITY",
            defaults.memory_semantic_min_similarity,
        )

        memory_subject_identity_min_similarity = (
            cls._read_unit_float(
                "BORU_MEMORY_SUBJECT_IDENTITY_MIN_SIMILARITY",
                defaults.memory_subject_identity_min_similarity,
            )
        )

        if not model_name:
            raise ValueError(
                "BORU_MODEL boş olamaz."
            )

        if not assistant_name:
            raise ValueError(
                "BORU_ASSISTANT_NAME boş olamaz."
            )

        if not profile_path:
            raise ValueError(
                "BORU_PROFILE_PATH boş olamaz."
            )

        if not memory_path:
            raise ValueError(
                "BORU_MEMORY_PATH boş olamaz."
            )

        if not project_memory_path:
            raise ValueError(
                "BORU_PROJECT_MEMORY_PATH boş olamaz."
            )

        if not knowledge_path:
            raise ValueError(
                "BORU_KNOWLEDGE_PATH boş olamaz."
            )

        if not task_checkpoint_path:
            raise ValueError(
                "BORU_TASK_CHECKPOINT_PATH boş olamaz."
            )

        if (
            memory_semantic_enabled
            and not memory_embedding_model
        ):
            raise ValueError(
                (
                    "BORU_MEMORY_EMBEDDING_MODEL "
                    "boş olamaz."
                )
            )

        if context_turns > history_turns:
            raise ValueError(
                (
                    "BORU_CONTEXT_TURNS, "
                    "BORU_HISTORY_TURNS değerinden "
                    "büyük olamaz."
                )
            )

        return cls(
            model_name=model_name,
            chat_model_name=os.getenv('BORU_CHAT_MODEL', '').strip(),
            fallback_model_name=fallback_model_name,
            assistant_name=assistant_name,
            history_turns=history_turns,
            context_turns=context_turns,
            context_max_characters=(
                context_max_characters
            ),
            profile_path=profile_path,
            memory_path=memory_path,
            project_memory_path=project_memory_path,
            knowledge_path=knowledge_path,
            task_checkpoint_path=task_checkpoint_path,
            api_allowed_hosts=api_allowed_hosts,
            memory_context_limit=(
                memory_context_limit
            ),
            memory_auto_capture=(
                memory_auto_capture
            ),
            memory_semantic_enabled=(
                memory_semantic_enabled
            ),
            memory_embedding_model=(
                memory_embedding_model
            ),
            memory_semantic_min_similarity=(
                memory_semantic_min_similarity
            ),
            memory_subject_identity_min_similarity=(
                memory_subject_identity_min_similarity
            ),
        )

    @staticmethod
    def _read_positive_integer(
        variable_name: str,
        default_value: int,
    ) -> int:
        raw_value = os.getenv(
            variable_name,
            str(default_value),
        )

        try:
            value = int(
                raw_value
            )

        except ValueError as error:
            raise ValueError(
                f"{variable_name} tam sayı olmalıdır."
            ) from error

        if value < 1:
            raise ValueError(
                f"{variable_name} en az 1 olmalıdır."
            )

        return value

    @staticmethod
    def _read_boolean(
        variable_name: str,
        default_value: bool,
    ) -> bool:
        raw_value = os.getenv(
            variable_name,
            (
                "true"
                if default_value
                else "false"
            ),
        ).strip().casefold()

        if raw_value in {
            "1",
            "true",
            "yes",
            "on",
        }:
            return True

        if raw_value in {
            "0",
            "false",
            "no",
            "off",
        }:
            return False

        raise ValueError(
            (
                f"{variable_name} true/false, "
                "1/0, yes/no veya on/off "
                "olmalıdır."
            )
        )

    @staticmethod
    def _read_unit_float(
        variable_name: str,
        default_value: float,
    ) -> float:
        raw_value = os.getenv(
            variable_name,
            str(default_value),
        )

        try:
            value = float(
                raw_value
            )

        except ValueError as error:
            raise ValueError(
                f"{variable_name} sayı olmalıdır."
            ) from error

        if not 0.0 <= value <= 1.0:
            raise ValueError(
                (
                    f"{variable_name} 0.0 ile "
                    "1.0 arasında olmalıdır."
                )
            )

        return value
