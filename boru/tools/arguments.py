from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class ToolArgumentType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"


@dataclass(frozen=True, slots=True)
class ToolArgumentSpec:
    name: str
    value_type: ToolArgumentType
    required: bool = True
    strip: bool = False
    allow_empty: bool = True
    max_length: int | None = None
    has_default: bool = False
    default: object | None = None

    def __post_init__(self) -> None:
        cleaned_name = self.name.strip()
        if not cleaned_name:
            raise ValueError(
                "Tool argüman adı boş olamaz."
            )

        if self.required and self.has_default:
            raise ValueError(
                "Zorunlu tool argümanı varsayılan değer içeremez."
            )

        if (
            self.max_length is not None
            and self.max_length < 1
        ):
            raise ValueError(
                "max_length en az 1 olmalıdır."
            )

        object.__setattr__(
            self,
            "name",
            cleaned_name,
        )


@dataclass(frozen=True, slots=True)
class ToolArgumentSchema:
    arguments: tuple[
        ToolArgumentSpec,
        ...
    ] = ()
    allow_unknown: bool = False

    def __post_init__(self) -> None:
        names = [
            argument.name
            for argument in self.arguments
        ]

        if len(names) != len(set(names)):
            raise ValueError(
                "Tool argüman şemasında aynı isim iki kez kullanılamaz."
            )

    @property
    def by_name(
        self,
    ) -> Mapping[
        str,
        ToolArgumentSpec,
    ]:
        return MappingProxyType(
            {
                argument.name: argument
                for argument in self.arguments
            }
        )


class ToolArgumentValidationError(
    ValueError
):
    pass


class ToolArgumentValidator:
    """ToolCall argümanlarını şemaya göre doğrular ve normalize eder."""

    def validate(
        self,
        schema: ToolArgumentSchema,
        arguments: Mapping[
            str,
            object,
        ],
    ) -> dict[str, object]:
        specs = schema.by_name
        provided = dict(arguments)

        if not schema.allow_unknown:
            unknown = sorted(
                set(provided)
                - set(specs)
            )

            if unknown:
                joined = ", ".join(
                    unknown
                )

                raise ToolArgumentValidationError(
                    f"Beklenmeyen tool argümanı: {joined}."
                )

        normalized: dict[
            str,
            object,
        ] = {}

        for name, spec in specs.items():
            if name not in provided:
                if spec.required:
                    raise ToolArgumentValidationError(
                        f"Zorunlu tool argümanı eksik: {name}."
                    )

                if spec.has_default:
                    normalized[name] = (
                        self._normalize_value(
                            spec,
                            spec.default,
                        )
                    )

                continue

            normalized[name] = (
                self._normalize_value(
                    spec,
                    provided[name],
                )
            )

        if schema.allow_unknown:
            for (
                name,
                value,
            ) in provided.items():
                if name not in normalized:
                    normalized[name] = value

        return normalized

    def _normalize_value(
        self,
        spec: ToolArgumentSpec,
        value: object,
    ) -> object:
        if (
            spec.value_type
            is ToolArgumentType.STRING
        ):
            if not isinstance(
                value,
                str,
            ):
                raise ToolArgumentValidationError(
                    f"'{spec.name}' metin olmalıdır."
                )

            normalized = (
                value.strip()
                if spec.strip
                else value
            )

            if (
                not spec.allow_empty
                and not normalized
            ):
                raise ToolArgumentValidationError(
                    f"'{spec.name}' boş olamaz."
                )

            if (
                spec.max_length
                is not None
                and len(normalized)
                > spec.max_length
            ):
                raise ToolArgumentValidationError(
                    f"'{spec.name}' en fazla "
                    f"{spec.max_length} karakter olabilir."
                )

            return normalized

        if (
            spec.value_type
            is ToolArgumentType.INTEGER
        ):
            if (
                isinstance(value, bool)
                or not isinstance(
                    value,
                    int,
                )
            ):
                raise ToolArgumentValidationError(
                    f"'{spec.name}' tam sayı olmalıdır."
                )

            return value

        if (
            spec.value_type
            is ToolArgumentType.NUMBER
        ):
            if (
                isinstance(value, bool)
                or not isinstance(
                    value,
                    (int, float),
                )
            ):
                raise ToolArgumentValidationError(
                    f"'{spec.name}' sayı olmalıdır."
                )

            return value

        if (
            spec.value_type
            is ToolArgumentType.BOOLEAN
        ):
            if not isinstance(
                value,
                bool,
            ):
                raise ToolArgumentValidationError(
                    f"'{spec.name}' boolean olmalıdır."
                )

            return value

        raise ToolArgumentValidationError(
            "Desteklenmeyen tool argüman tipi: "
            f"{spec.value_type}."
        )