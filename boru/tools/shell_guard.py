import re


class ShellEnvironmentAssignmentGuard:
    """Prevents shell assignments from falling through to conversational generation."""

    _ASSIGNMENT = re.compile(
        r"^\s*(?:\$env:[A-Za-z_][A-Za-z0-9_]*\s*=|"
        r"(?:export|set)\s+[A-Za-z_][A-Za-z0-9_]*\s*=).+$",
        re.IGNORECASE | re.DOTALL,
    )

    @property
    def has_pending(self) -> bool:
        return False

    def resolve(self, message: str) -> str | None:
        if not self._ASSIGNMENT.fullmatch(message):
            return None
        return (
            "ORTAM DEĞİŞKENİ AYARLANMADI\n"
            "Shell ortam değişkenleri Börü sohbetinden değiştirilemez. "
            "Komutu PowerShell/terminal penceresinde çalıştırıp Börü'yü yeniden başlatın."
        )
