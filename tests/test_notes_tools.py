from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest

from boru.tools.notes_tools import NotesService, resolve_notes_command


class TestNotesTools:
    def test_notes_service_crud(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            temp_path = Path(tf.name)

        try:
            service = NotesService(notes_path=temp_path)
            ok, msg = service.list_notes()
            assert ok
            assert "herhangi bir notunuz bulunmuyor" in msg

            ok, msg = service.add_note("Docker ayarlarını yap")
            assert ok
            assert "Notunuz kaydedildi" in msg

            ok, msg = service.add_note("Toplantıya katıl")
            assert ok

            ok, msg = service.list_notes()
            assert ok
            assert "Toplam 2 adet notunuz var" in msg
            assert "Docker ayarlarını yap" in msg
            assert "Toplantıya katıl" in msg

            ok, msg = service.get_last_note()
            assert ok
            assert "Toplantıya katıl" in msg

            ok, msg = service.clear_notes()
            assert ok
            assert "2 adet" in msg

            ok, msg = service.list_notes()
            assert "herhangi bir notunuz bulunmuyor" in msg
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_resolve_notes_command_patterns(self):
        with patch("boru.tools.notes_tools.get_notes_service") as mock_get:
            mock_srv = mock_get.return_value
            mock_srv.add_note.return_value = (True, "Not eklendi.")
            mock_srv.list_notes.return_value = (True, "Notlar: 1. test")
            mock_srv.get_last_note.return_value = (True, "Son not: test")
            mock_srv.clear_notes.return_value = (True, "Temizlendi.")

            res = resolve_notes_command("bunu not al: yarın sınav var")
            assert res == "Not eklendi."
            mock_srv.add_note.assert_called_with("yarın sınav var")

            res = resolve_notes_command("notlarıma ekle: ekmek al")
            assert res == "Not eklendi."

            res = resolve_notes_command("notlarımı oku")
            assert res == "Notlar: 1. test"

            res = resolve_notes_command("son notum neydi")
            assert res == "Son not: test"

            res = resolve_notes_command("notlarımı temizle")
            assert res == "Temizlendi."

        assert resolve_notes_command("hava nasıl") is None
