import re

from boru.tools.edit_contracts import (
    SmartEditProposalPreparer,
    SmartEditWorkspace,
)
from boru.tools.edit_models import (
    EditProposal,
    EditRequest,
    SmartEditRequest,
)


class SmartEditNotApplicable(RuntimeError):
    """Deterministik smart-edit katmanının bu isteği güvenle çözemediğini belirtir."""


class RequestedStateAlreadySatisfied(ValueError):
    """The requested deterministic assignment already matches the source."""


class RuleBasedAssignmentEditProposalPreparer:
    """Basit `name değerini value yap` isteklerini LLM kullanmadan hazırlar."""

    _INSTRUCTION_PATTERN = re.compile(
        r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_.-]*)\s+"
        r"değerini\s+(?P<value>.+?)\s+"
        r"(?:yap|olarak\s+değiştir|olarak\s+güncelle|"
        r"değiştir|güncelle|ayarla)\s*$",
        re.IGNORECASE | re.DOTALL,
    )
    _FILE_SCOPE_QUALIFIER = re.compile(
        r"^(?:yalnızca|sadece)\s+bu\s+dosyada\s+",
        re.IGNORECASE,
    )
    _TRAILING_FILE_SCOPE = re.compile(
        r"\s*[;,]?\s*(?:yalnızca|sadece)\s+bu\s+dosya(?:yı|da)\s+kapsa\s*$",
        re.IGNORECASE,
    )

    def __init__(
        self,
        *,
        workspace: SmartEditWorkspace,
    ):
        self._workspace = workspace

    def prepare_smart_edit(
        self,
        request: SmartEditRequest,
    ) -> EditProposal:
        instruction = self._TRAILING_FILE_SCOPE.sub("", request.instruction).strip()
        instruction_match = (
            self._INSTRUCTION_PATTERN.fullmatch(
                instruction
            )
        )

        if instruction_match is None:
            raise SmartEditNotApplicable(
                "İstek basit assignment düzenleme biçiminde değil."
            )

        name = instruction_match.group(
            "name"
        ).strip()

        requested_value = (
            instruction_match.group(
                "value"
            ).strip()
        )
        requested_value = self._FILE_SCOPE_QUALIFIER.sub(
            "",
            requested_value,
            count=1,
        ).strip()

        source = self._workspace.read_edit_source(
            request.path
        )

        assignment_pattern = (
            self._build_assignment_pattern(
                name
            )
        )

        matches = list(
            assignment_pattern.finditer(
                source.content
            )
        )

        if not matches:
            raise SmartEditNotApplicable(
                "Hedef assignment kaynakta bulunamadı."
            )

        if len(matches) > 1:
            raise ValueError(
                "Hedef assignment dosyada birden fazla kez bulundu; "
                "belirsiz düzenleme reddedildi."
            )

        match = matches[0]

        old_text = match.group(0)

        new_rhs = self._format_requested_value(
            existing_rhs=match.group(
                "rhs"
            ),
            requested_value=requested_value,
        )

        new_text = (
            f"{match.group('prefix')}"
            f"{new_rhs}"
            f"{match.group('suffix')}"
            f"{match.group('eol')}"
        )

        if old_text == new_text:
            raise RequestedStateAlreadySatisfied(
                "İstenen değer dosyada zaten mevcut; uygulanacak değişiklik yok."
            )

        return (
            self._workspace
            .prepare_exact_replacement(
                EditRequest(
                    path=request.path,
                    old_text=old_text,
                    new_text=new_text,
                ),
                expected_sha256=(
                    source.sha256
                ),
            )
        )

    @staticmethod
    def _build_assignment_pattern(
        name: str,
    ) -> re.Pattern[str]:
        return re.compile(
            rf"^(?P<prefix>[ \t]*{re.escape(name)}[ \t]*=[ \t]*)"
            r"(?P<rhs>"
            r'"(?:\\.|[^"\\])*"'
            r"|\'(?:\\.|[^\'\\])*\'"
            r"|[^#\r\n]*?"
            r")"
            r"(?P<suffix>[ \t]*(?:#[^\r\n]*)?)"
            r"(?P<eol>\r?\n|$)",
            re.MULTILINE,
        )

    @staticmethod
    def _format_requested_value(
        *,
        existing_rhs: str,
        requested_value: str,
    ) -> str:
        existing = existing_rhs.strip()
        requested = requested_value.strip()

        if not requested:
            raise ValueError(
                "Yeni assignment değeri boş olamaz."
            )

        if (
            len(requested) >= 2
            and requested[0] in {
                '"',
                "'",
            }
            and requested[-1]
            == requested[0]
        ):
            return requested

        if (
            len(existing) >= 2
            and existing[0] in {
                '"',
                "'",
            }
            and existing[-1]
            == existing[0]
        ):
            quote = existing[0]

            escaped = (
                requested
                .replace(
                    "\\",
                    "\\\\",
                )
                .replace(
                    quote,
                    f"\\{quote}",
                )
            )

            return (
                f"{quote}"
                f"{escaped}"
                f"{quote}"
            )

        return requested


class FallbackSmartEditProposalPreparer:
    """Deterministik preparer uygulanamazsa mevcut grounded smart-edit preparer'a düşer."""

    def __init__(
        self,
        *,
        primary: SmartEditProposalPreparer,
        fallback: SmartEditProposalPreparer,
    ):
        self._primary = primary
        self._fallback = fallback

    def prepare_smart_edit(
        self,
        request: SmartEditRequest,
    ) -> EditProposal:
        try:
            return (
                self._primary
                .prepare_smart_edit(
                    request
                )
            )
        except SmartEditNotApplicable:
            return (
                self._fallback
                .prepare_smart_edit(
                    request
                )
            )
