"""
tests/test_closed_loop_verification.py
=======================================
Börü Closed-Loop Execution & Verification Birim Testleri.
"""

from unittest.mock import MagicMock, patch
import pytest

from boru.tools.closed_loop import ClosedLoopActionExecutor, SystemExecutionVerifier


class TestClosedLoopVerification:
    """Doğrulamalı çalıştırma ve süreç denetimi testleri."""

    def test_resolve_exe_name(self):
        assert SystemExecutionVerifier.resolve_exe_name("Not Defteri") == "notepad.exe"
        assert SystemExecutionVerifier.resolve_exe_name("chrome") == "chrome.exe"
        assert SystemExecutionVerifier.resolve_exe_name("spotify'ı") == "spotify.exe"
        assert SystemExecutionVerifier.resolve_exe_name("calc.exe") == "calc.exe"

    @patch("subprocess.run")
    def test_is_process_running_found(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='"notepad.exe","1234","Console"')
        assert SystemExecutionVerifier.is_process_running("notepad") is True

    @patch("subprocess.run")
    def test_is_process_running_not_found(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='INFO: No tasks are running which match the specified criteria.')
        assert SystemExecutionVerifier.is_process_running("notepad") is False

    @patch.object(SystemExecutionVerifier, "is_process_running")
    def test_verify_app_started_success(self, mock_running):
        mock_running.return_value = True
        ok, msg = SystemExecutionVerifier.verify_app_started("notepad", wait_seconds=0.01, max_attempts=1)
        assert ok is True
        assert "Doğrulandı" in msg

    @patch.object(SystemExecutionVerifier, "is_process_running")
    def test_verify_app_started_failure(self, mock_running):
        mock_running.return_value = False
        ok, msg = SystemExecutionVerifier.verify_app_started("notepad", wait_seconds=0.01, max_attempts=1)
        assert ok is False
        assert "Doğrulama Başarısız" in msg

    @patch.object(SystemExecutionVerifier, "is_process_running")
    def test_verify_app_stopped_success(self, mock_running):
        mock_running.return_value = False
        ok, msg = SystemExecutionVerifier.verify_app_stopped("notepad", wait_seconds=0.01, max_attempts=1)
        assert ok is True
        assert "Doğrulandı" in msg

    @patch.object(SystemExecutionVerifier, "is_process_running")
    def test_verify_app_stopped_failure(self, mock_running):
        mock_running.return_value = True
        ok, msg = SystemExecutionVerifier.verify_app_stopped("notepad", wait_seconds=0.01, max_attempts=1)
        assert ok is False
        assert "Doğrulama Uyarısı" in msg

    @patch("subprocess.run")
    @patch.object(SystemExecutionVerifier, "verify_app_stopped")
    def test_close_app_verified_calls_taskkill_and_verifies(self, mock_verify, mock_run):
        mock_verify.return_value = (True, "Doğrulandı: Notepad süreci başarıyla sonlandırıldı.")
        mock_run.return_value = MagicMock(returncode=0)

        ok, msg = ClosedLoopActionExecutor.close_app_verified("notepad", force_tree=True)
        assert ok is True
        assert "Zorla sonlandırılarak" in msg
        # Doğrula: taskkill /F /T çağrıldı mı
        args, kwargs = mock_run.call_args
        assert "/F" in args[0]
        assert "/T" in args[0]

