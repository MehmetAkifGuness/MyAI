import re
from pathlib import PurePosixPath

from boru.tools.command_models import CommandKind, CommandRequest
from boru.tools.command_policy import SafeCommandPolicy
from boru.tools.test_results import TestOutputParser
from boru.tools.workspace import WorkspacePathResolver


class SandboxTerminalCoordinator:
    """Small CLI grammar mapped to canonical sandbox commands, never a shell."""

    _COMMAND = re.compile(
        r"^(?:python\s+-m\s+)?(unittest|pytest|ruff|mypy|compileall)"
        r"(?:\s+(.*))?$", re.IGNORECASE,
    )
    _USAGE = (
        "İzinli terminal komutları: unittest [hedef], pytest [hedef], "
        "ruff check [hedef], mypy [hedef], compileall [hedef], pip check."
    )

    def __init__(self, root, executor, history=None, *, feature_level=9):
        if type(feature_level) is not int or not 0 <= feature_level <= 9:
            raise ValueError("Terminal özellik seviyesi 0-9 arasında olmalıdır.")
        self._resolver = WorkspacePathResolver(root)
        self._executor = executor
        self._history = history
        self._feature_level = feature_level
        self._working_directory = ""

    @property
    def has_pending(self):
        return False

    def resolve(self, message):
        try:
            return self._resolve(message)
        except (OSError, RuntimeError, ValueError) as error:
            return f"TERMİNAL RAPORU\nDurum: ÇALIŞTIRILAMADI\n{error}"

    def _resolve(self, message):
        normalized = " ".join(message.strip().casefold().split())
        known = self._known_command(normalized)
        if known is not None:
            return known
        structured = self._structured_request(message)
        if structured is not None:
            return structured
        if not normalized.startswith("terminal"):
            return None
        prefix, separator, command = message.partition(":")
        if not separator or prefix.strip().casefold() != "terminal":
            return self._USAGE
        return self._execute(self._parse(command.strip()))

    def _structured_request(self, message):
        directory = self._directory_request(message)
        if directory is not None:
            return directory
        return self._quality_request(message)

    def _known_command(self, normalized):
        if normalized == "terminal durumu":
            return (
                "TERMİNAL DURUMU\n"
                f"Çalışma dizini: {self._display_working_directory()}\n"
                "Yürütme: Docker Linux; Python modülleri; shell kapalı.\n"
                + self._executor.status() + "\n" + self._USAGE
            )
        if normalized == "terminal ortamı":
            self._require_level(3, "Ortam inceleme V3.3 ile kullanılabilir.")
            return self._execute(self._fixed_spec(CommandKind.ENVIRONMENT))
        if normalized in {"terminal pwd", "terminal çalışma dizini"}:
            self._require_level(1, "Çalışma dizini V3.1 ile kullanılabilir.")
            return f"TERMİNAL ÇALIŞMA DİZİNİ\n{self._display_working_directory()}"
        if normalized == "terminal geçmişi":
            self._require_level(2, "Terminal geçmişi V3.2 ile kullanılabilir.")
            return self._history.render() if self._history else "TERMİNAL GEÇMİŞİ\nKayıt: 0"
        return None

    def _fixed_spec(self, kind):
        return SafeCommandPolicy().build(
            CommandRequest(kind, working_directory=self._working_directory)
        )

    def _display_working_directory(self):
        return "/workspace" + ("/" + self._working_directory if self._working_directory else "")

    def _execute(self, spec):
        try:
            result = self._executor.execute(spec)
        except (OSError, RuntimeError, ValueError) as error:
            return f"TERMİNAL RAPORU\nDurum: ÇALIŞTIRILAMADI\n{error}"
        report, status = self._render(spec, result)
        if self._history:
            try:
                self._history.append(
                    " ".join(spec.arguments),
                    spec.working_directory,
                    status,
                    result.exit_code,
                )
            except (OSError, RuntimeError, ValueError) as error:
                report += f"\nGeçmiş uyarısı: {error}"
        return report

    @staticmethod
    def _render(spec, result):
        summary = TestOutputParser().parse(result)
        status = "BAŞARILI" if result.succeeded else "BAŞARISIZ"
        if result.timed_out:
            status = "ZAMAN AŞIMI"
        elif result.output_limit_exceeded:
            status = "ÇIKTI SINIRI"
        elif spec.kind in {CommandKind.UNITTEST, CommandKind.PYTEST}:
            if not summary or not summary.total:
                status = "TEST BULUNAMADI" if result.succeeded else "BAŞARISIZ"
        cwd = "/workspace" + (
            f"/{spec.working_directory}" if spec.working_directory else ""
        )
        report = (
            f"TERMİNAL RAPORU\nDurum: {status}\nKomut: {' '.join(spec.arguments)}"
            f"\nÇalışma dizini: {cwd}"
            f"\nÇıkış kodu: {result.exit_code}\nSüre: {result.duration_seconds:.2f} sn"
            + (f"\nTest: {summary.passed}/{summary.total}" if summary else "")
            + f"\n{result.output[:8000]}"
        )
        return report, status

    def _parse(self, command):
        if len(command) > 1000 or re.search(r"[;&|><`$\r\n]", command):
            raise ValueError("Shell operatörleri ve çoklu komutlar desteklenmez.")
        normalized = " ".join(command.casefold().split())
        if normalized in {"pip check", "python -m pip check"}:
            self._require_level(4, "Bağımlılık kontrolü V3.4 ile kullanılabilir.")
            return self._fixed_spec(CommandKind.PIP_CHECK)
        if normalized == "python --version":
            return self._fixed_spec(CommandKind.ENVIRONMENT)
        match = self._COMMAND.fullmatch(command)
        if not match:
            raise ValueError(self._USAGE)
        kind = CommandKind(match.group(1).casefold())
        if kind is CommandKind.COMPILEALL:
            self._require_level(5, "Syntax kontrolü V3.5 ile kullanılabilir.")
        target = (match.group(2) or "").strip()
        if kind is CommandKind.RUFF:
            if target != "check" and not target.startswith("check "):
                raise ValueError("Ruff yalnızca check işlemini destekler.")
            target = target[5:].strip()
        if target:
            # Existing safe policy rejects flags, absolute paths and traversal.
            SafeCommandPolicy().build(
                CommandRequest(kind, target, self._working_directory)
            )
            scoped = PurePosixPath(self._working_directory, target).as_posix()
            self._resolver.resolve(scoped)
        return SafeCommandPolicy().build(
            CommandRequest(kind, target, self._working_directory)
        )

    def _directory_request(self, message):
        match = re.fullmatch(
            r"\s*terminal\s+(?:cd|çalışma\s+dizini)\s*:\s*(.*?)\s*",
            message,
            re.IGNORECASE,
        )
        if not match:
            return None
        self._require_level(1, "Çalışma dizini V3.1 ile kullanılabilir.")
        requested = match.group(1)
        if requested in {"", ".", "/workspace"}:
            self._working_directory = ""
        else:
            SafeCommandPolicy()._validate_target(requested)
            target = self._resolver.resolve(requested)
            if not target.is_dir():
                raise ValueError("Terminal çalışma yolu klasör olmalıdır.")
            self._working_directory = target.relative_to(self._resolver.root).as_posix()
        return f"TERMİNAL ÇALIŞMA DİZİNİ\n{self._display_working_directory()}"

    def _quality_request(self, message):
        match = re.fullmatch(
            r"\s*terminal\s+kalite\s*:\s*(.*?)\s*",
            message,
            re.IGNORECASE,
        )
        if not match:
            return None
        self._require_level(6, "Kalite hattı V3.6 ile kullanılabilir.")
        target = match.group(1)
        if not target:
            raise ValueError("Kalite hattı mevcut bir hedef gerektirir.")
        reports = []
        for command in (
            f"compileall {target}",
            f"ruff check {target}",
            f"mypy {target}",
        ):
            reports.append(self._execute(self._parse(command)))
        passed = sum(
            report.startswith("TERMİNAL RAPORU\nDurum: BAŞARILI\n")
            for report in reports
        )
        return (
            f"TERMİNAL KALİTE HATTI\nDurum: {'BAŞARILI' if passed == len(reports) else 'BAŞARISIZ'}"
            f"\nAşama: {passed}/{len(reports)} geçti\n\n"
            + "\n\n".join(reports)
        )

    def _require_level(self, level, message):
        if self._feature_level < level:
            raise ValueError(message)
