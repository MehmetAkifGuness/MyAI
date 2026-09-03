from dataclasses import dataclass, field
from typing import Any, Literal


ProfileCategory = Literal[
    "identity",
    "preference",
    "fact",
]


@dataclass(frozen=True, slots=True)
class ProfileUpdate:
    category: ProfileCategory
    key: str
    value: str


@dataclass(slots=True)
class UserProfile:
    name: str | None = None

    preferences: dict[str, str] = field(
        default_factory=dict
    )

    facts: dict[str, str] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "preferences": dict(
                self.preferences
            ),
            "facts": dict(
                self.facts
            ),
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> "UserProfile":
        name = data.get("name")

        if name is not None:
            name = str(name).strip() or None

        preferences = cls._clean_mapping(
            data.get(
                "preferences",
                {},
            )
        )

        facts = cls._clean_mapping(
            data.get(
                "facts",
                {},
            )
        )

        return cls(
            name=name,
            preferences=preferences,
            facts=facts,
        )

    @staticmethod
    def _clean_mapping(
        value: Any,
    ) -> dict[str, str]:
        if not isinstance(
            value,
            dict,
        ):
            return {}

        cleaned: dict[str, str] = {}

        for key, item in value.items():
            key_text = str(
                key
            ).strip()

            value_text = str(
                item
            ).strip()

            if (
                key_text
                and value_text
            ):
                cleaned[
                    key_text
                ] = value_text

        return cleaned