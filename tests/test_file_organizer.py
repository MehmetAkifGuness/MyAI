import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest

from boru.tools.file_organizer import (
    organize_desktop,
    get_downloads_info,
    resolve_file_organizer_command,
)


class TestFileOrganizer:
    def test_organize_desktop_moves_files_and_preserves_shortcuts(self):
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            # Örnek masaüstü oluştur
            doc_file = tmp_path / "rapor.pdf"
            doc_file.write_text("dummy doc")

            img_file = tmp_path / "ekran_goruntusu.png"
            img_file.write_text("dummy img")

            lnk_file = tmp_path / "Chrome.lnk"
            lnk_file.write_text("dummy shortcut")

            ini_file = tmp_path / "desktop.ini"
            ini_file.write_text("system ini")

            sub_folder = tmp_path / "OzelKlasor"
            sub_folder.mkdir()

            ok, msg, moved = organize_desktop(tmp_path)
            assert ok
            assert moved.get("Belgeler") == 1
            assert moved.get("Görseller") == 1

            # Belgeler ve Görseller klasörleri oluşmalı
            assert (tmp_path / "Belgeler" / "rapor.pdf").exists()
            assert (tmp_path / "Görseller" / "ekran_goruntusu.png").exists()

            # Kısayol, ini ve klasör yerinde kalmalı
            assert lnk_file.exists()
            assert ini_file.exists()
            assert sub_folder.exists()

    def test_organize_desktop_already_clean(self):
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            ok, msg, moved = organize_desktop(tmp_path)
            assert ok
            assert "düzenli" in msg
            assert len(moved) == 0

    def test_get_downloads_info(self):
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            f1 = tmp_path / "setup.exe"
            f1.write_bytes(b"x" * 1024 * 1024 * 2)  # 2 MB
            f2 = tmp_path / "sample.pdf"
            f2.write_bytes(b"x" * 1024 * 512)  # 0.5 MB

            ok, msg, data = get_downloads_info(tmp_path)
            assert ok
            assert data["file_count"] == 2
            assert "setup.exe" in msg

    def test_resolve_file_organizer_command(self):
        with patch("boru.tools.file_organizer.organize_desktop", return_value=(True, "Masaüstü düzenlendi.", {})):
            res1 = resolve_file_organizer_command("masaüstümü düzenle")
            assert res1 == "Masaüstü düzenlendi."

            res2 = resolve_file_organizer_command("masaüstünü toparla")
            assert res2 == "Masaüstü düzenlendi."

        with patch("boru.tools.file_organizer.get_downloads_info", return_value=(True, "İndirilenler 2 GB.", {})):
            res3 = resolve_file_organizer_command("indirilenler ne kadar yer kaplıyor")
            assert res3 == "İndirilenler 2 GB."
