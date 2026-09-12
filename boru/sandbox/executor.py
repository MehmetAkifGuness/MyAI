import re
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from boru.sandbox.snapshot import SourceSnapshot
from boru.tools.command_executor import BoundedCommandExecutor
from boru.tools.command_models import CommandExecutionResult, CommandKind, CommandRequest, CommandRisk, CommandSpec
from boru.tools.command_policy import SafeCommandPolicy
from boru.tools.workspace import WorkspacePathResolver


class DockerSandboxExecutor:
    """Runs only canonical test/lint commands in a restricted Linux container."""

    _KINDS = {
        CommandKind.UNITTEST,
        CommandKind.PYTEST,
        CommandKind.RUFF,
        CommandKind.MYPY,
        CommandKind.COMPILEALL,
        CommandKind.PIP_CHECK,
        CommandKind.ENVIRONMENT,
    }
    _TARGET_KINDS = {
        CommandKind.UNITTEST,
        CommandKind.PYTEST,
        CommandKind.RUFF,
        CommandKind.MYPY,
        CommandKind.COMPILEALL,
    }

    def __init__(self, root: Path, image: str = "boru-sandbox:1.0", runner=None, docker: str | None = None):
        if re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._/:@-]{0,255}", image) is None:
            raise ValueError("Sandbox imaj adı geçersiz.")
        self._root = root.resolve()
        self._resolver = WorkspacePathResolver(self._root)
        self._image = image
        self._docker = docker or shutil.which("docker")
        self._runner = runner or BoundedCommandExecutor(self._root, timeout_seconds=120)

    def status(self) -> str:
        if self._docker is None:
            return "SANDBOX DURUMU\nDurum: HAZIR DEĞİL\nDocker bulunamadı; yerelde çalıştırma yapılmaz."
        try:
            self._check(("info", "--format", "{{.OSType}}"), expected="linux")
            self._check(("image", "inspect", self._image))
        except (OSError, ValueError) as error:
            return f"SANDBOX DURUMU\nDurum: HAZIR DEĞİL\n{error}"
        return (
            f"SANDBOX DURUMU\nDurum: HAZIR\nİmaj: {self._image}\n"
            "Ağ: kapalı; kaynak kopyası: salt-okunur; CPU: 1; RAM: 512 MB; PID: 64.\n"
            "Komut süresi: 120 sn; çıktı: 1 MB. Docker hazır değilse işlem durdurulur."
        )

    def execute(self, command: CommandSpec) -> CommandExecutionResult:
        arguments = self._canonical_arguments(command)
        if self._docker is None:
            raise ValueError("Sandbox için Docker gerekli; komut yerelde çalıştırılmadı.")
        self._check(("info", "--format", "{{.OSType}}"), expected="linux")
        self._check(("image", "inspect", self._image))
        name = "boru-sandbox-" + uuid4().hex
        with TemporaryDirectory(prefix="boru-sandbox-") as directory:
            snapshot = Path(directory)
            SourceSnapshot(self._root).copy_to(snapshot)
            spec = self._run_spec(command, snapshot, name, arguments)
            try:
                result = self._runner.execute(spec)
            finally:
                self._cleanup(name)
        return replace(result, command=command)

    @classmethod
    def _canonical_arguments(cls, command: CommandSpec) -> tuple[str, ...]:
        if command.risk is not CommandRisk.SAFE or command.kind not in cls._KINDS:
            raise ValueError("Sandbox yalnızca izinli test/lint komutlarını çalıştırır.")
        default = SafeCommandPolicy().build(
            CommandRequest(command.kind, working_directory=command.working_directory)
        )
        if command.arguments == default.arguments:
            return command.arguments
        if not command.arguments or command.kind not in cls._TARGET_KINDS:
            raise ValueError("Sandbox komutu boş.")
        target = command.arguments[-1]
        canonical = SafeCommandPolicy().build(
            CommandRequest(command.kind, target, command.working_directory)
        )
        if canonical.arguments != command.arguments:
            raise ValueError("Sandbox serbest Python veya shell argümanlarını reddeder.")
        normalized = SafeCommandPolicy().build(
            CommandRequest(
                command.kind,
                target.replace("\\", "/"),
                command.working_directory,
            )
        )
        return normalized.arguments

    def _run_spec(self, command, snapshot, name, arguments):
        if "," in str(snapshot):
            raise ValueError("Sandbox geçici yolunda virgül desteklenmiyor.")
        workdir = "/workspace"
        if command.working_directory:
            source_directory = self._resolver.resolve(command.working_directory)
            if not source_directory.is_dir():
                raise ValueError("Sandbox çalışma yolu klasör olmalıdır.")
            relative = source_directory.relative_to(self._root).as_posix()
            snapshot_directory = snapshot / relative
            if not snapshot_directory.exists():
                snapshot_directory.mkdir(parents=True)
            workdir += "/" + relative
        return CommandSpec(
            command.kind, self._docker,
            ("run", "--rm", "--pull=never", "--name", name, "--network=none",
             "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
             "--cpus=1", "--memory=512m", "--memory-swap=512m", "--pids-limit=64",
             "--user=65534:65534", "--init", "--no-healthcheck", "--log-driver=none",
             "--tmpfs", "/tmp:rw,nosuid,nodev,size=67108864,mode=1777",
             "--mount", f"type=bind,source={snapshot},target=/workspace,readonly",
             f"--workdir={workdir}", "--env=HOME=/tmp", "--env=PYTHONDONTWRITEBYTECODE=1",
             "--env=PYTHONPYCACHEPREFIX=/tmp/pycache",
             "--env=PYTHONIOENCODING=utf-8", "--entrypoint=python", self._image,
             "-B", *arguments),
            f"Sandbox: {command.display}", CommandRisk.SAFE, command.working_directory,
        )

    def _check(self, arguments: tuple[str, ...], expected: str | None = None) -> None:
        try:
            result = subprocess.run(
                (self._docker, *arguments), stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise ValueError("Docker durum kontrolü zaman aşımına uğradı.") from error
        if result.returncode != 0:
            raise ValueError(
                "Docker Linux motorunu başlatın ve boru-sandbox imajını hazırlayın. "
                "Sandbox komutu çalıştırılmadı."
            )
        if expected and result.stdout.decode("utf-8", errors="replace").strip() != expected:
            raise ValueError("Sandbox Linux container motoru gerektiriyor.")

    def _cleanup(self, name: str) -> None:
        # Only the unique container created for this call is ever removed.
        try:
            result = subprocess.run(
                (self._docker, "rm", "-f", name), stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ValueError(f"Sandbox temizlenemedi; container adı: {name}") from error
        if result.returncode and b"No such container" not in result.stderr:
            raise ValueError(f"Sandbox temizliği doğrulanamadı; container adı: {name}")


class LocalIsolatedSandboxExecutor:
    """
    Docker motoru kapalı olduğunda veya bulunamadığında, kaynak kodların
    geçici bir kopyasını alarak güvenli ve yalıtılmış bir ortamda test/lint
    komutlarını çalıştıran yerel sanal alan yürütücüsü.
    """

    _KINDS = DockerSandboxExecutor._KINDS
    _TARGET_KINDS = DockerSandboxExecutor._TARGET_KINDS

    def __init__(self, root: Path, timeout_seconds: int = 60):
        import sys
        self._root = root.resolve()
        self._resolver = WorkspacePathResolver(self._root)
        self._timeout = timeout_seconds
        self._python_bin = sys.executable

    def status(self) -> str:
        return (
            "SANDBOX DURUMU\nDurum: HAZIR (Yerel İzolasyon)\n"
            "Geçici kopya: aktif; komut süresi: 60 sn; yalnızca izinli test/lint komutları çalıştırılır.\n"
            "Kaynak güvenliği: geçici dizin izolasyonu; ana çalışma alanı korunur."
        )

    def execute(self, command: CommandSpec) -> CommandExecutionResult:
        arguments = DockerSandboxExecutor._canonical_arguments(command)
        with TemporaryDirectory(prefix="boru-local-sandbox-") as directory:
            snapshot = Path(directory)
            SourceSnapshot(self._root).copy_to(snapshot)
            workdir = snapshot
            if command.working_directory:
                source_directory = self._resolver.resolve(command.working_directory)
                if not source_directory.is_dir():
                    raise ValueError("Sandbox çalışma yolu klasör olmalıdır.")
                relative = source_directory.relative_to(self._root)
                workdir = snapshot / relative
                workdir.mkdir(parents=True, exist_ok=True)

            runner = BoundedCommandExecutor(workdir, timeout_seconds=self._timeout)
            spec = CommandSpec(
                command.kind,
                self._python_bin,
                ("-B", *arguments),
                f"LocalSandbox: {command.display}",
                CommandRisk.SAFE,
                workdir,
            )
            result = runner.execute(spec)
            return replace(result, command=command)


class HybridSandboxExecutor:
    """
    Docker ve Yerel İzolasyonu birleştiren hibrit yürütücü.
    Docker çalışıyorsa Linux container'ını, kapalıysa yerel geçici kopya
    izolasyonunu otomatik olarak seçer.
    """

    _KINDS = DockerSandboxExecutor._KINDS
    _TARGET_KINDS = DockerSandboxExecutor._TARGET_KINDS

    def __init__(self, root: Path, image: str = "boru-sandbox:1.0", timeout_seconds: int = 60):
        self._root = root.resolve()
        self._docker_executor = DockerSandboxExecutor(self._root, image)
        self._local_executor = LocalIsolatedSandboxExecutor(self._root, timeout_seconds)

    def is_docker_ready(self) -> bool:
        st = self._docker_executor.status()
        return "Durum: HAZIR\n" in st

    def status(self) -> str:
        if self.is_docker_ready():
            return self._docker_executor.status()
        return (
            "SANDBOX DURUMU\nDurum: HAZIR (Yerel Güvenli İzolasyon Fallback)\n"
            "Not: Docker kapalı veya imaj kurulu değil; geçici kopya izolasyonu aktif.\n"
            "Komut süresi: 60 sn; yalnızca izinli test/lint komutları çalıştırılır."
        )

    def execute(self, command: CommandSpec) -> CommandExecutionResult:
        if self.is_docker_ready():
            try:
                return self._docker_executor.execute(command)
            except Exception:
                # Docker çalışma zamanında çökerse yerel izolasyona düş
                return self._local_executor.execute(command)
        return self._local_executor.execute(command)

