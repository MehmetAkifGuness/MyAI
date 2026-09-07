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


class DockerSandboxExecutor:
    """Runs only canonical test/lint commands in a restricted Linux container."""

    _KINDS = {CommandKind.UNITTEST, CommandKind.PYTEST, CommandKind.RUFF, CommandKind.MYPY}

    def __init__(self, root: Path, image: str = "boru-sandbox:1.0", runner=None, docker: str | None = None):
        if re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._/:@-]{0,255}", image) is None:
            raise ValueError("Sandbox imaj adı geçersiz.")
        self._root = root.resolve()
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
        default = SafeCommandPolicy().build(CommandRequest(command.kind))
        if command.arguments == default.arguments:
            return command.arguments
        if not command.arguments:
            raise ValueError("Sandbox komutu boş.")
        target = command.arguments[-1]
        canonical = SafeCommandPolicy().build(CommandRequest(command.kind, target))
        if canonical.arguments != command.arguments:
            raise ValueError("Sandbox serbest Python veya shell argümanlarını reddeder.")
        normalized = SafeCommandPolicy().build(CommandRequest(command.kind, target.replace("\\", "/")))
        return normalized.arguments

    def _run_spec(self, command, snapshot, name, arguments):
        if "," in str(snapshot):
            raise ValueError("Sandbox geçici yolunda virgül desteklenmiyor.")
        return CommandSpec(
            command.kind, self._docker,
            ("run", "--rm", "--pull=never", "--name", name, "--network=none",
             "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
             "--cpus=1", "--memory=512m", "--memory-swap=512m", "--pids-limit=64",
             "--user=65534:65534", "--init", "--no-healthcheck", "--log-driver=none",
             "--tmpfs", "/tmp:rw,nosuid,nodev,size=67108864,mode=1777",
             "--mount", f"type=bind,source={snapshot},target=/workspace,readonly",
             "--workdir=/workspace", "--env=HOME=/tmp", "--env=PYTHONDONTWRITEBYTECODE=1",
             "--env=PYTHONIOENCODING=utf-8", "--entrypoint=python", self._image,
             "-B", *arguments),
            f"Sandbox: {command.display}", CommandRisk.SAFE,
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
