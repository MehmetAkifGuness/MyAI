class AutonomousDevelopmentCoordinator:
    """Turn one development objective into the existing verified task loop."""

    _USAGE = (
        "Biçimler: 'otonom geliştir: hedef', 'otonom devam et', "
        "'otonom durum' veya 'otonom iptal'."
    )

    def __init__(self, task_coordinator):
        self._tasks = task_coordinator

    @property
    def has_pending(self):
        return self._tasks.has_pending

    def resolve(self, message):
        normalized = " ".join(message.strip().casefold().split())
        if normalized.startswith("otonom geliştir:"):
            return self._start(message.partition(":")[2].strip())
        if normalized == "otonom devam et":
            return self._render("DEVAM", self._tasks.resolve("planı devam ettir"))
        if normalized == "otonom durum":
            return self._render("DURUM", self._tasks.resolve("görev durumu"))
        if normalized == "otonom iptal":
            if not self._tasks.has_pending:
                return "OTONOM GELİŞTİRME\nDurum: ETKİN ONAY YOK"
            return self._render("İPTAL", self._tasks.resolve("iptal"))
        if normalized.startswith("otonom"):
            return self._USAGE
        return self._tasks.resolve(message)

    def _start(self, objective):
        if not objective:
            return self._USAGE
        if len(objective) > 4000:
            return "OTONOM GELİŞTİRME\nDurum: REDDEDİLDİ\nHedef en fazla 4000 karakter olabilir."
        if self._tasks.has_pending:
            return "OTONOM GELİŞTİRME\nDurum: ONAY BEKLİYOR\nÖnce etkin akışı tamamlayın veya iptal edin."
        planned = self._tasks.resolve("görev planla: " + objective)
        if not planned or "GÖREV PLANI HAZIRLANDI" not in planned:
            return self._render("PLANLANAMADI", planned)
        started = self._tasks.resolve("planı çalıştır")
        status = "ONAY BEKLİYOR" if self._tasks.has_pending else "DURDU"
        return self._render(status, planned + "\n\n" + (started or ""))

    @staticmethod
    def _render(status, detail):
        return f"OTONOM GELİŞTİRME\nDurum: {status}\n\n{detail or 'Yanıt yok.'}"
