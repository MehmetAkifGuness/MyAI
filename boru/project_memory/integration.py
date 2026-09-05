import re

from boru.project_memory.contracts import ProjectMemoryServicePort
from boru.project_memory.models import ProjectMemoryAction, ProjectMemoryRequest
from boru.project_memory.parser import RuleBasedProjectMemoryParser


class ProjectMemoryContextProvider:
    def __init__(self, service: ProjectMemoryServicePort):
        self._service = service

    def build_context(self, user_message: str) -> str:
        del user_message
        return self._service.build_context()


class ProjectMemoryCoordinator:
    _PROJECT_QUESTION_PATTERN = re.compile(
        r"\b(?:bu\s+proje(?:de|nin|ye)?|projem(?:de|in|e)?)\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        service: ProjectMemoryServicePort,
        parser: RuleBasedProjectMemoryParser,
    ):
        self._service = service
        self._parser = parser

    def resolve(self, user_message: str) -> str | None:
        lines = tuple(
            line.strip()
            for line in user_message.splitlines()
            if line.strip()
        )
        if len(lines) > 1:
            return self._resolve_batch(lines)

        request = self._parser.parse(user_message)
        if request is None:
            return self._resolve_project_question(user_message)

        return self._resolve_request(request)

    def _resolve_batch(self, lines: tuple[str, ...]) -> str | None:
        requests = tuple(self._parser.parse(line) for line in lines)
        if requests[0] is None:
            return None
        if any(request is None for request in requests):
            return (
                "Proje hafızası komutlarıyla normal sohbet isteği aynı mesajda "
                "birleştirilemez. Komutları ve sorunuzu ayrı mesajlar olarak gönderin."
            )

        return "\n\n".join(
            self._resolve_request(request)
            for request in requests
            if request is not None
        )

    def _resolve_request(self, request: ProjectMemoryRequest) -> str:

        try:
            if request.action is ProjectMemoryAction.SHOW:
                return self._render_entries()
            if request.action is ProjectMemoryAction.DELETE:
                return self._delete(request.key)
            return self._save(request.key, request.value)
        except ValueError as error:
            return f"Proje hafızası işlemi reddedildi: {error}"

    def _render_entries(self) -> str:
        entries = self._service.list_entries()
        if not entries:
            return "PROJE HAFIZASI\nHenüz kayıtlı proje bilgisi yok."

        lines = ["PROJE HAFIZASI", f"Kayıt: {len(entries)}", ""]
        lines.extend(f"- {key}: {value}" for key, value in entries)
        return "\n".join(lines)

    def _save(self, key: str, value: str) -> str:
        if not key or not value:
            return (
                "Proje bilgisi kaydedilemedi. Beklenen biçim: "
                "proje bilgisi kaydet: anahtar = değer"
            )

        result = self._service.save_entry(key, value)
        labels = {
            "created": "kaydedildi",
            "updated": "güncellendi",
            "unchanged": "zaten aynı değerde",
        }
        normalized_key = " ".join(key.strip().split()).casefold()
        return f"Proje bilgisi {labels[result]}: {normalized_key} = {value.strip()}"

    def _delete(self, key: str) -> str:
        if not key:
            return "Silinecek proje bilgisi anahtarı belirtilmedi."
        normalized_key = " ".join(key.strip().split()).casefold()
        if not self._service.delete_entry(key):
            return f"Proje bilgisinde '{normalized_key}' anahtarı bulunamadı."
        return f"Proje bilgisi silindi: {normalized_key}"

    def _resolve_project_question(self, user_message: str) -> str | None:
        if "?" not in user_message or not self._PROJECT_QUESTION_PATTERN.search(
            user_message
        ):
            return None

        entries = self._service.list_entries()
        if not entries:
            return "Proje hafızasında henüz kayıtlı bilgi yok."

        normalized_message = " ".join(user_message.casefold().split())
        matched = tuple(
            (key, value)
            for key, value in entries
            if key in normalized_message
        )
        selected = matched or entries
        lines = "\n".join(f"- {key}: {value}" for key, value in selected)
        return f"Proje hafızasına göre:\n{lines}"
