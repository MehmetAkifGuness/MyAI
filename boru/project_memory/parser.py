import re

from boru.project_memory.models import ProjectMemoryAction, ProjectMemoryRequest


class RuleBasedProjectMemoryParser:
    _SHOW_PATTERN = re.compile(
        r"^(?:proje\s+(?:bilgisi|bilgileri|hafızası)(?:nı)?(?:\s+göster)?|"
        r"proje\s+hafızasını\s+göster)$",
        re.IGNORECASE,
    )
    _SAVE_PATTERN = re.compile(
        r"^(?:proje\s+bilgisi\s+kaydet|proje\s+hafızasına\s+kaydet|"
        r"proje\s+hafızası\s+ekle)\s*:\s*(.+)$",
        re.IGNORECASE | re.DOTALL,
    )
    _DELETE_PATTERN = re.compile(
        r"^(?:proje\s+bilgisi\s+sil|proje\s+hafızasından\s+sil)\s*:\s*(.+)$",
        re.IGNORECASE | re.DOTALL,
    )

    def parse(self, user_message: str) -> ProjectMemoryRequest | None:
        text = " ".join(user_message.strip().split())
        if not text:
            return None

        if self._SHOW_PATTERN.fullmatch(text):
            return ProjectMemoryRequest(ProjectMemoryAction.SHOW)

        delete_match = self._DELETE_PATTERN.fullmatch(text)
        if delete_match:
            return ProjectMemoryRequest(
                ProjectMemoryAction.DELETE,
                key=delete_match.group(1).strip(),
            )

        save_match = self._SAVE_PATTERN.fullmatch(text)
        if not save_match:
            return None

        payload = save_match.group(1).strip()
        if re.search(
            r"\bproje\s+(?:bilgisi|bilgileri|hafızası|hafızasına|hafızasından)\b",
            payload,
            re.IGNORECASE,
        ):
            return ProjectMemoryRequest(ProjectMemoryAction.SAVE)
        separator = "=" if "=" in payload else ":" if ":" in payload else ""
        if not separator:
            return ProjectMemoryRequest(ProjectMemoryAction.SAVE)

        key, value = payload.split(separator, 1)
        return ProjectMemoryRequest(
            ProjectMemoryAction.SAVE,
            key=key.strip(),
            value=value.strip(),
        )
