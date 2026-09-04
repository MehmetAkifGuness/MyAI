import os
import subprocess
import tempfile
import time
from pathlib import Path

from boru.tools.command_models import (
    CommandExecutionResult,
    CommandRisk,
    CommandSpec,
)


class BoundedCommandExecutor:
    """İzinli komutları shell olmadan, süre ve çıktı sınırlarıyla çalıştırır."""

    def __init__(
        self,
        workspace_root: Path,
        timeout_seconds: float = 120.0,
        max_output_bytes: int = 1024 * 1024,
        allowed_risks: tuple[CommandRisk, ...] = (CommandRisk.SAFE,),
    ) -> None:
        root = workspace_root.resolve()
        if not root.is_dir():
            raise ValueError("Komut workspace'i mevcut bir klasör olmalıdır.")
        if timeout_seconds <= 0:
            raise ValueError("Komut zaman aşımı pozitif olmalıdır.")
        if max_output_bytes < 1:
            raise ValueError("Komut çıktı limiti pozitif olmalıdır.")
        if not allowed_risks:
            raise ValueError("En az bir komut risk seviyesi izinli olmalıdır.")

        self._workspace_root = root
        self._timeout_seconds = timeout_seconds
        self._max_output_bytes = max_output_bytes
        self._allowed_risks = frozenset(allowed_risks)

    def execute(self, command: CommandSpec) -> CommandExecutionResult:
        if command.risk not in self._allowed_risks:
            raise PermissionError("Komut risk seviyesi çalıştırıcı tarafından engellendi.")

        started = time.monotonic()
        timed_out = False
        output_limit_exceeded = False
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        with tempfile.TemporaryFile() as output_file:
            process = subprocess.Popen(
                (command.executable, *command.arguments),
                cwd=self._workspace_root,
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=output_file,
                stderr=subprocess.STDOUT,
                creationflags=creation_flags,
            )

            while process.poll() is None:
                elapsed = time.monotonic() - started
                if elapsed > self._timeout_seconds:
                    timed_out = True
                    process.kill()
                    break

                if os.fstat(output_file.fileno()).st_size > self._max_output_bytes:
                    output_limit_exceeded = True
                    process.kill()
                    break

                try:
                    process.wait(timeout=0.05)
                except subprocess.TimeoutExpired:
                    pass

            process.wait()
            output_size = os.fstat(output_file.fileno()).st_size
            output_limit_exceeded = (
                output_limit_exceeded
                or output_size > self._max_output_bytes
            )
            output_file.seek(0)
            output = output_file.read(self._max_output_bytes).decode(
                "utf-8",
                errors="replace",
            )

        return CommandExecutionResult(
            command=command,
            exit_code=process.returncode,
            duration_seconds=time.monotonic() - started,
            output=output,
            timed_out=timed_out,
            output_limit_exceeded=output_limit_exceeded,
            truncated=output_size > self._max_output_bytes,
        )
