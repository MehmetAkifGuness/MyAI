import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from threading import Event, RLock, Thread
from time import monotonic
from uuid import uuid4

from boru.benchmark.cases import catalog
from boru.benchmark.runner import BenchmarkProgress


@dataclass(frozen=True, slots=True)
class BenchmarkRequest:
    models: tuple[str, ...]
    case_ids: tuple[str, ...] = ()
    limit: int = 3
    repeats: int = 1
    budget_seconds: int = 1800
    repair_attempts: int = 1
    fallback_model: str = ""


class BenchmarkCoordinator:
    """Runs the bounded benchmark off the UI thread and reports its state."""

    _MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}")
    _USAGE = (
        "Biçimler: 'benchmark görevleri'; 'benchmark çalıştır: model | limit=5'; "
        "'benchmark durumu'; 'benchmark iptal'. Yedek model: '| yedek=model'. "
        "İsterseniz güvenli 'python -B -m boru.benchmark "
        "--model MODEL --limit 5' biçimini de kullanabilirsiniz."
    )

    def __init__(self, root: Path, runner_factory, model_factory):
        self._root = root.resolve()
        self._runner_factory = runner_factory
        self._model_factory = model_factory
        self._lock = RLock()
        self._state = "idle"
        self._summary = None
        self._error = ""
        self._output: Path | None = None
        self._started = 0.0
        self._worker: Thread | None = None
        self._cancel = Event()
        self._progress = BenchmarkProgress(0, 0)

    @property
    def has_pending(self):
        return False

    def resolve(self, message: str) -> str | None:
        normalized = " ".join(message.casefold().strip().split())
        if normalized == "benchmark görevleri":
            return self._render_cases()
        if normalized == "benchmark durumu":
            return self._render_status()
        if normalized == "benchmark iptal":
            return self._cancel_run()
        try:
            request = self._parse(message)
        except ValueError as error:
            return f"BENCHMARK\nDurum: GEÇERSİZ\n{error}\n{self._USAGE}"
        if request is None:
            return self._USAGE if normalized.startswith("benchmark") else None
        with self._lock:
            if self._state == "running":
                return "BENCHMARK\nDurum: ZATEN ÇALIŞIYOR\n" + self._status_detail()
            self._state = "running"
            self._summary = None
            self._error = ""
            self._output = None
            self._started = monotonic()
            self._cancel.clear()
            self._progress = BenchmarkProgress(
                0, request.limit * request.repeats * len(request.models)
            )
            self._worker = Thread(target=self._run, args=(request,), daemon=True)
            self._worker.start()
        return (
            "BENCHMARK\nDurum: BAŞLATILDI\n"
            f"Model: {', '.join(request.models)}; görev: {request.limit}; tekrar: {request.repeats}"
            + (f"; yedek: {request.fallback_model}" if request.fallback_model else "") + "\n"
            "Sonucu görmek için 'benchmark durumu' yazın."
        )

    def _run(self, request: BenchmarkRequest) -> None:
        try:
            cases = catalog()
            if request.case_ids:
                cases = tuple(case for case in cases if case.identifier in request.case_ids)
            cases = cases[: request.limit]
            models = {name: self._model_factory(name) for name in request.models}
            fallback_model = (
                (request.fallback_model, self._model_factory(request.fallback_model))
                if request.fallback_model else None
            )
            report = self._runner_factory(request.repair_attempts).run(
                models,
                cases,
                repeats=request.repeats,
                budget_seconds=request.budget_seconds,
                fallback_model=fallback_model,
                progress_callback=self._update_progress,
                cancel_requested=self._cancel.is_set,
            )
            output = self._root / "data" / "benchmarks" / f"{uuid4().hex}.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8") as stream:
                json.dump(report, stream, ensure_ascii=False, indent=2)
            with self._lock:
                self._state = report.get("state", "completed")
                self._summary = report.get("summary", {})
                self._output = output
        except Exception as error:
            # Background task failures must become visible status, not kill the UI thread.
            with self._lock:
                self._state = "failed"
                self._error = str(error)[:2000]

    def _render_status(self) -> str:
        with self._lock:
            state = self._state
            detail = self._status_detail()
            if state == "idle":
                return "BENCHMARK\nDurum: HENÜZ ÇALIŞTIRILMADI"
            if state == "running":
                return "BENCHMARK\nDurum: ÇALIŞIYOR\n" + detail
            if state == "failed":
                return "BENCHMARK\nDurum: BAŞARISIZ\n" + self._error
            summary = json.dumps(self._summary, ensure_ascii=False, indent=2)
            labels = {"completed": "TAMAMLANDI", "cancelled": "İPTAL EDİLDİ",
                      "budget_exhausted": "SÜRE SINIRI"}
            return f"BENCHMARK\nDurum: {labels.get(state, state.upper())}\nRapor: {self._output}\n{summary}"

    def _status_detail(self) -> str:
        elapsed = max(0.0, monotonic() - self._started)
        progress = self._progress
        lines = [f"Geçen süre: {elapsed:.1f} sn",
                 f"İlerleme: {progress.completed}/{progress.total}"]
        if progress.current_model:
            lines.append(
                f"Aktif: {progress.current_model} / {progress.current_case} / tekrar {progress.repeat}"
            )
        if progress.last_status:
            lines.append(f"Sonuç: {progress.last_status}")
        if progress.completed and progress.completed < progress.total:
            eta = elapsed / progress.completed * (progress.total - progress.completed)
            lines.append(f"Tahmini kalan: {eta:.1f} sn")
        if self._cancel.is_set():
            lines.append("İptal istendi; aktif değerlendirme tamamlanınca duracak.")
        return "\n".join(lines)

    def _update_progress(self, progress: BenchmarkProgress) -> None:
        with self._lock:
            self._progress = progress

    def _cancel_run(self) -> str:
        with self._lock:
            if self._state != "running":
                return "BENCHMARK\nDurum: ÇALIŞAN BENCHMARK YOK"
            self._cancel.set()
            return "BENCHMARK\nDurum: İPTAL İSTENDİ\n" + self._status_detail()

    @classmethod
    def _parse(cls, message: str) -> BenchmarkRequest | None:
        match = re.fullmatch(r"\s*benchmark\s+çalıştır\s*:\s*(.*?)\s*", message, re.IGNORECASE)
        if match:
            return cls._parse_native(match.group(1))
        try:
            parts = shlex.split(message, posix=False)
        except ValueError as error:
            raise ValueError("Komut ayrıştırılamadı.") from error
        folded = [part.casefold() for part in parts]
        if folded[:4] != ["python", "-b", "-m", "boru.benchmark"]:
            return None
        return cls._parse_flags(parts[4:])

    @classmethod
    def _parse_native(cls, text: str) -> BenchmarkRequest:
        pieces = [piece.strip() for piece in text.split("|") if piece.strip()]
        if not pieces:
            raise ValueError("En az bir model adı gereklidir.")
        models = tuple(item.strip() for item in pieces[0].split(",") if item.strip())
        values = {"limit": 3, "repeats": 1, "budget_seconds": 1800, "repair_attempts": 1}
        fallback_model = ""
        aliases = {"limit": "limit", "tekrar": "repeats", "süre": "budget_seconds", "onarım": "repair_attempts"}
        for piece in pieces[1:]:
            key, separator, value = piece.partition("=")
            if separator and key.casefold() == "yedek":
                fallback_model = value.strip()
                continue
            if not separator or key.casefold() not in aliases:
                raise ValueError(f"Bilinmeyen benchmark ayarı: {piece}")
            try:
                values[aliases[key.casefold()]] = int(value)
            except ValueError as error:
                raise ValueError(f"Benchmark ayarı tam sayı olmalıdır: {piece}") from error
        return cls._validated(models=models, fallback_model=fallback_model, **values)

    @classmethod
    def _parse_flags(cls, parts: list[str]) -> BenchmarkRequest:
        models: list[str] = []
        cases: list[str] = []
        fallback_model = ""
        values = {"limit": 3, "repeats": 1, "budget_seconds": 1800, "repair_attempts": 1}
        names = {"--limit": "limit", "--repeats": "repeats", "--budget-seconds": "budget_seconds",
                 "--repair-attempts": "repair_attempts"}
        index = 0
        while index < len(parts):
            flag = parts[index].casefold()
            if flag not in {"--model", "--fallback-model", "--case", *names} or index + 1 >= len(parts):
                raise ValueError(f"İzin verilmeyen veya eksik benchmark seçeneği: {parts[index]}")
            value = parts[index + 1]
            if flag == "--model":
                models.append(value)
            elif flag == "--fallback-model":
                fallback_model = value
            elif flag == "--case":
                cases.append(value)
            else:
                try:
                    values[names[flag]] = int(value)
                except ValueError as error:
                    raise ValueError(f"Sayısal benchmark değeri geçersiz: {value}") from error
            index += 2
        return cls._validated(
            models=tuple(models), fallback_model=fallback_model, case_ids=tuple(cases), **values
        )

    @classmethod
    def _validated(
        cls, *, models, fallback_model="", case_ids=(), limit, repeats,
        budget_seconds, repair_attempts
    ):
        models = tuple(dict.fromkeys(models))
        known = {case.identifier for case in catalog()}
        if not models or len(models) > 4 or not all(cls._MODEL.fullmatch(name) for name in models):
            raise ValueError("1-4 geçerli Ollama model adı gereklidir.")
        if fallback_model and not cls._MODEL.fullmatch(fallback_model):
            raise ValueError("Geçerli bir yedek Ollama model adı gereklidir.")
        if set(case_ids) - known:
            raise ValueError("Bilinmeyen benchmark görevi.")
        if not 1 <= limit <= 30 or not 1 <= repeats <= 3 or not 1 <= budget_seconds <= 7200:
            raise ValueError("Limit 1-30, tekrar 1-3, süre 1-7200 olmalıdır.")
        if repair_attempts not in {0, 1}:
            raise ValueError("Onarım denemesi 0 veya 1 olmalıdır.")
        return BenchmarkRequest(
            models=models,
            case_ids=tuple(dict.fromkeys(case_ids)),
            limit=limit,
            repeats=repeats,
            budget_seconds=budget_seconds,
            repair_attempts=repair_attempts,
            fallback_model=fallback_model,
        )

    @staticmethod
    def _render_cases() -> str:
        lines = ["BENCHMARK GÖREVLERİ", f"Toplam: {len(catalog())}"]
        lines.extend(f"- {case.identifier} [{case.category}]" for case in catalog())
        return "\n".join(lines)
