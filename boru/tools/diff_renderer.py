import difflib


class UnifiedDiffRenderer:
    """Unified diff çıktısını terminal newline durumundan bağımsız okunabilir üretir."""

    _CURRENT_NO_NEWLINE_MARKER = (
        "\\ No newline at end of current file"
    )

    _PROPOSED_NO_NEWLINE_MARKER = (
        "\\ No newline at end of proposed file"
    )

    def render(
        self,
        *,
        original: str,
        updated: str,
        fromfile: str,
        tofile: str,
    ) -> str:
        lines = list(
            difflib.unified_diff(
                original.splitlines(),
                updated.splitlines(),
                fromfile=fromfile,
                tofile=tofile,
                lineterm="",
            )
        )

        if not lines:
            return ""

        if (
            original
            and not self._has_terminal_newline(
                original
            )
        ):
            lines.append(
                self._CURRENT_NO_NEWLINE_MARKER
            )

        if (
            updated
            and not self._has_terminal_newline(
                updated
            )
        ):
            lines.append(
                self._PROPOSED_NO_NEWLINE_MARKER
            )

        return "\n".join(lines) + "\n"

    @staticmethod
    def _has_terminal_newline(
        value: str,
    ) -> bool:
        return value.endswith(
            ("\n", "\r")
        )