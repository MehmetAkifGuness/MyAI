import re

from boru.autonomy.models import AutonomyAction
from boru.autonomy.parser import RuleBasedAutonomyCommandParser


class AutonomousDevelopmentCoordinator:
    """Supervise planning, approval, verification and recovery through safe delegates."""

    def __init__(self, task_coordinator, *, evaluator=None, feature_level=0):
        self._tasks = task_coordinator
        self._evaluator = evaluator
        self._parser = RuleBasedAutonomyCommandParser(feature_level)

    @property
    def has_pending(self):
        return self._tasks.has_pending

    def resolve(self, message):
        command = self._parser.parse(message)
        if command is None:
            if self._parser.is_intent(message):
                if self._is_cancel(message):
                    return self._pause(cancel_label=True)
                return self._parser.usage()
            return self._tasks.resolve(message)
        handlers = {
            AutonomyAction.DEVELOP: lambda: self._start(command.value),
            AutonomyAction.PLAN: lambda: self._plan(command.value),
            AutonomyAction.START: self._start_plan,
            AutonomyAction.CONTINUE: self._continue,
            AutonomyAction.STATUS: lambda: self._render("DURUM", self._tasks.resolve("görev durumu")),
            AutonomyAction.PAUSE: self._pause,
            AutonomyAction.RETRY: lambda: self._retry(command.value),
            AutonomyAction.VERIFY: lambda: self._verify(command.value),
            AutonomyAction.SUMMARY: self._summary,
            AutonomyAction.ARCHIVE: self._archive,
            AutonomyAction.LIMITS: self._limits,
            AutonomyAction.HELP: lambda: self._parser.usage(),
        }
        return handlers[command.action]()

    def _start(self, objective):
        if not objective:
            return self._parser.usage()
        if len(objective) > 4000:
            return "OTONOM GELİŞTİRME\nDurum: REDDEDİLDİ\nHedef en fazla 4000 karakter olabilir."
        if self._tasks.has_pending:
            return "OTONOM GELİŞTİRME\nDurum: ONAY BEKLİYOR\nÖnce etkin akışı tamamlayın veya iptal edin."
        planned = self._plan(objective, wrapped=False)
        if not planned or "GÖREV PLANI HAZIRLANDI" not in planned:
            return self._render("PLANLANAMADI", planned)
        started = self._tasks.resolve("planı çalıştır")
        status = self._execution_status(started)
        return self._render(status, planned + "\n\n" + (started or ""))

    def _plan(self, objective, *, wrapped=True):
        if not objective:
            return self._parser.usage()
        if len(objective) > 4000:
            return self._render("REDDEDİLDİ", "Hedef en fazla 4000 karakter olabilir.")
        if self._tasks.has_pending:
            return self._render("ONAY BEKLİYOR", "Önce etkin akışı tamamlayın veya duraklatın.")
        response = self._tasks.resolve("görev planla: " + objective)
        if not wrapped:
            return response
        status = "PLAN HAZIR" if response and "GÖREV PLANI HAZIRLANDI" in response else "PLANLANAMADI"
        return self._render(status, response)

    def _start_plan(self):
        if self._tasks.has_pending:
            return self._render("ONAY BEKLİYOR", "Etkin öneri zaten onay bekliyor.")
        response = self._tasks.resolve("planı çalıştır")
        status = self._execution_status(response)
        return self._render(status, response)

    def _continue(self):
        response = self._tasks.resolve("planı devam ettir")
        status = self._execution_status(response)
        return self._render(status, response)

    def _pause(self, cancel_label=False):
        if not self._tasks.has_pending:
            label = "ETKİN ONAY YOK" if cancel_label else "DURAKLATILACAK AKIŞ YOK"
            return f"OTONOM GELİŞTİRME\nDurum: {label}"
        response = self._tasks.resolve("iptal")
        return self._render("İPTAL" if cancel_label else "DURAKLATILDI", response)

    def _retry(self, task_id):
        normalized = task_id.strip().upper()
        if re.fullmatch(r"TASK-[1-9]\d*", normalized) is None:
            return self._render("REDDEDİLDİ", "Task kimliği TASK-N biçiminde olmalıdır.")
        if self._tasks.has_pending:
            return self._render("ONAY BEKLİYOR", "Önce etkin akışı tamamlayın veya duraklatın.")
        response = self._tasks.resolve("task yeniden dene: " + normalized)
        status = self._execution_status(response)
        return self._render(status, response)

    def _verify(self, value):
        if self._evaluator is None:
            return self._render("DOĞRULANAMADI", "Kanıt değerlendiricisi etkin değil.")
        try:
            paths = self._verification_paths(value)
            response = self._evaluator.validate_paths(paths)
        except (OSError, RuntimeError, ValueError) as error:
            return self._render("DOĞRULANAMADI", str(error))
        status = "GEÇTİ" if "Durum: GEÇTİ" in response else "İNCELEME GEREKLİ"
        return self._render(status, response)

    def _summary(self):
        status = self._tasks.resolve("görev durumu")
        journal = self._tasks.resolve("görev günlüğü")
        return self._render("ÖZET", (status or "") + "\n\n" + (journal or ""))

    def _archive(self):
        if self._tasks.has_pending:
            return self._render("ONAY BEKLİYOR", "Etkin öneri varken plan arşivlenemez.")
        response = self._tasks.resolve("planı arşivle")
        status = "ARŞİVLENDİ" if response and "arşivlendi" in response.casefold() else "ARŞİVLENEMEDİ"
        return self._render(status, response)

    @staticmethod
    def _limits():
        return (
            "OTONOM GELİŞTİRME SINIRLARI\n"
            "- Hedef: en fazla 4000 karakter\n"
            "- Plan: en fazla 12 task\n"
            "- Yeniden deneme: task başına 3\n"
            "- Plan geçerliliği: 7 gün\n"
            "- Kaynak değişikliği: her task için açık onay\n"
            "- Doğrulama: en fazla 12 Python dosyası; Docker ağı kapalı"
        )

    @staticmethod
    def _verification_paths(value):
        paths = tuple(dict.fromkeys(
            item.strip().replace("\\", "/")
            for item in re.split(r"\s*,\s*|\s+ve\s+", value, flags=re.IGNORECASE)
            if item.strip()
        ))
        if not 1 <= len(paths) <= 12:
            raise ValueError("Doğrulama 1-12 dosya gerektirir.")
        safe = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.py")
        if any(safe.fullmatch(path) is None or ".." in path.split("/") for path in paths):
            raise ValueError("Doğrulama yalnızca proje içindeki göreli Python yollarını kabul eder.")
        return paths

    @staticmethod
    def _is_cancel(message):
        folded = " ".join(message.strip().casefold().split()).rstrip(".!?")
        return folded in {"otonom iptal", "otonom iptal et"}

    def _execution_status(self, response):
        if self._tasks.has_pending:
            return "ONAY BEKLİYOR"
        if response and "Durum: TAMAMLANDI" in response:
            return "TAMAMLANDI"
        return "DURDU"

    @staticmethod
    def _render(status, detail):
        return f"OTONOM GELİŞTİRME\nDurum: {status}\n\n{detail or 'Yanıt yok.'}"
