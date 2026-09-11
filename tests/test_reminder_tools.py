from __future__ import annotations

import time
from unittest.mock import MagicMock, patch
import pytest

from boru.tools.reminder_tools import ReminderService, resolve_reminder_command


class TestReminderTools:
    def test_schedule_and_cancel(self):
        service = ReminderService()
        r_id, msg = service.schedule(100, "test hatırlatıcı")
        assert "1 dakika 40 saniye" in msg
        assert r_id in service._reminders

        active_str = service.list_active()
        assert "test hatırlatıcı" in active_str

        cancel_msg = service.cancel_all()
        assert "1 adet aktif hatırlatıcı iptal edildi" in cancel_msg
        assert len(service._reminders) == 0

    def test_resolve_reminder_command(self):
        with patch.object(ReminderService, "schedule", return_value=(1, "Hatırlatıcı kuruldu.")) as mock_sched:
            res = resolve_reminder_command("10 saniye sonra uyar: çayı kapat")
            assert res == "Hatırlatıcı kuruldu."
            mock_sched.assert_called_with(10, "çayı kapat")

            res = resolve_reminder_command("5 dakikalık sayaç başlat")
            assert res == "Hatırlatıcı kuruldu."
            mock_sched.assert_called_with(300, "5 dakika süresi doldu")

        with patch.object(ReminderService, "list_active", return_value="Aktif sayaçlar var."):
            res = resolve_reminder_command("aktif sayaçlar")
            assert res == "Aktif sayaçlar var."

        with patch.object(ReminderService, "cancel_all", return_value="İptal edildi."):
            res = resolve_reminder_command("sayaçları iptal et")
            assert res == "İptal edildi."

        assert resolve_reminder_command("bu bir hatırlatıcı değil") is None

