from boru.database_tools.models import DatabaseAction, DatabaseResult


class DatabaseReadCoordinator:
    def __init__(self, parser, service):
        self._parser = parser
        self._service = service

    @property
    def has_pending(self) -> bool:
        return False

    def resolve(self, user_message: str) -> str | None:
        try:
            request = self._parser.parse(user_message)
            if request is None:
                return self._usage() if self._parser.is_database_intent(user_message) else None
            if request.action is DatabaseAction.TABLES:
                result = self._service.list_tables(request.database_path)
            elif request.action is DatabaseAction.SCHEMA:
                result = self._service.schema(request.database_path)
            elif request.action is DatabaseAction.DESCRIBE:
                result = self._service.describe(request.database_path, request.value)
            else:
                result = self._service.query(request.database_path, request.value)
        except (RuntimeError, ValueError) as error:
            return f"Veritabanı isteği reddedildi: {error}"
        return self._render(request.action, request.database_path, result)

    @staticmethod
    def _render(action, database_path: str, result: DatabaseResult) -> str:
        lines = [
            "VERİTABANI RAPORU",
            f"İşlem: {action.value}",
            f"Dosya: {database_path}",
            f"Satır: {len(result.rows)}",
            "",
        ]
        if result.columns:
            lines.append(" | ".join(result.columns))
        lines.extend(" | ".join(row) for row in result.rows)
        if not result.rows:
            lines.append("(sonuç yok)")
        if result.truncated:
            lines.append("Not: Sonuç satır sınırında kesildi.")
        return "\n".join(lines)

    @staticmethod
    def _usage() -> str:
        return (
            "Desteklenen biçimler: 'veritabanı tabloları: DOSYA', "
            "'veritabanı şema: DOSYA', 'veritabanı tablo açıkla: DOSYA | TABLO' ve "
            "'veritabanı sorgula: DOSYA | SELECT ...'."
        )
