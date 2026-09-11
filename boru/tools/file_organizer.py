"""
boru.tools.file_organizer
=========================
Akıllı Masaüstü ve İndirilenler Dosya Düzenleyicisi.
Masaüstündeki dağınık dosyaları (belgeler, görseller, arşivler, kurulumlar)
kısayollara ve sistem dosyalarına asla dokunmadan kategorilerine göre güvenle toparlar.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import re
import shutil
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Dosya uzantı kategorileri
EXTENSION_CATEGORIES: Dict[str, str] = {
    # Belgeler
    ".pdf": "Belgeler",
    ".docx": "Belgeler",
    ".doc": "Belgeler",
    ".xlsx": "Belgeler",
    ".xls": "Belgeler",
    ".pptx": "Belgeler",
    ".txt": "Belgeler",
    ".csv": "Belgeler",
    # Görseller
    ".png": "Görseller",
    ".jpg": "Görseller",
    ".jpeg": "Görseller",
    ".gif": "Görseller",
    ".bmp": "Görseller",
    ".svg": "Görseller",
    ".webp": "Görseller",
    # Arşivler
    ".zip": "Arşivler",
    ".rar": "Arşivler",
    ".7z": "Arşivler",
    ".tar": "Arşivler",
    ".gz": "Arşivler",
    # Kurulum Dosyaları
    ".exe": "Kurulumlar",
    ".msi": "Kurulumlar",
    # Medya
    ".mp3": "Medya",
    ".mp4": "Medya",
    ".wav": "Medya",
    ".mkv": "Medya",
    ".avi": "Medya",
}

# Asla dokunulmayacak dosya uzantıları ve adları
IGNORED_EXTENSIONS = {".lnk", ".url", ".ini"}
IGNORED_FILENAMES = {"desktop.ini"}


def _get_desktop_path() -> Path:
    userprofile = Path(os.environ.get("USERPROFILE", str(Path.home())))
    onedrive_desk = userprofile / "OneDrive" / "Desktop"
    if onedrive_desk.exists():
        return onedrive_desk
    standard_desk = userprofile / "Desktop"
    if standard_desk.exists():
        return standard_desk
    return Path.home() / "Desktop"


def _get_downloads_path() -> Path:
    userprofile = Path(os.environ.get("USERPROFILE", str(Path.home())))
    dl = userprofile / "Downloads"
    if dl.exists():
        return dl
    return Path.home() / "Downloads"


def organize_desktop(desktop_dir: Optional[Path] = None) -> Tuple[bool, str, Dict[str, int]]:
    """
    Masaüstündeki gevşek dosyaları ilgili alt klasörlere (Belgeler, Görseller vb.) taşır.
    Masaüstü kısayollarına (.lnk, .url) ve klasörlere kesinlikle dokunmaz.
    """
    desk_path = desktop_dir or _get_desktop_path()
    if not desk_path.exists():
        return False, "Masaüstü klasörü bulunamadı.", {}

    moved_counts: Dict[str, int] = {}
    total_moved = 0

    try:
        for item in desk_path.iterdir():
            # Yalnızca dosyalara işlem yap, klasörlere ve sistem/kısayol dosyalarına dokunma
            if not item.is_file():
                continue
            ext = item.suffix.lower()
            name = item.name.lower()

            if ext in IGNORED_EXTENSIONS or name in IGNORED_FILENAMES or name.startswith("~"):
                continue

            category = EXTENSION_CATEGORIES.get(ext)
            if not category:
                continue

            target_folder = desk_path / category
            target_folder.mkdir(exist_ok=True)

            target_file = target_folder / item.name
            # İsim çakışması varsa numaralandır
            counter = 1
            while target_file.exists():
                target_file = target_folder / f"{item.stem}_{counter}{item.suffix}"
                counter += 1

            shutil.move(str(item), str(target_file))
            moved_counts[category] = moved_counts.get(category, 0) + 1
            total_moved += 1

        if total_moved == 0:
            return True, "Masaüstünüz zaten tamamen düzenli. Taşınacak dosya bulunamadı.", {}

        parts = [f"{count} {cat.lower()}" for cat, count in moved_counts.items()]
        msg = f"Masaüstündeki toplam {total_moved} dosya düzenlendi ({', '.join(parts)} ilgili klasörlere taşındı)."
        return True, msg, moved_counts
    except Exception as e:
        logger.error(f"Masaüstü düzenleme hatası: {e}")
        return False, f"Masaüstü düzenlenirken hata oluştu: {e}", {}


def get_downloads_info(downloads_dir: Optional[Path] = None) -> Tuple[bool, str, Dict]:
    """
    İndirilenler klasöründeki toplam dosya sayısını, kapladığı alanı ve en büyük dosyaları raporlar.
    """
    dl_path = downloads_dir or _get_downloads_path()
    if not dl_path.exists():
        return False, "İndirilenler klasörü bulunamadı.", {}

    total_bytes = 0
    file_count = 0
    files_with_size: List[Tuple[str, int]] = []

    try:
        for item in dl_path.iterdir():
            if item.is_file():
                try:
                    size = item.stat().st_size
                    total_bytes += size
                    file_count += 1
                    files_with_size.append((item.name, size))
                except Exception:
                    pass

        # Boyut formatla
        mb = total_bytes / (1024 * 1024)
        if mb >= 1024:
            size_str = f"{mb / 1024:.1f} GB"
        else:
            size_str = f"{mb:.0f} MB"

        # En büyük 3 dosya
        files_with_size.sort(key=lambda x: x[1], reverse=True)
        top_files = []
        for name, b in files_with_size[:3]:
            f_mb = b / (1024 * 1024)
            top_files.append(f"{name} ({f_mb:.0f} MB)")

        top_str = f" En büyük dosyalar: {', '.join(top_files)}." if top_files else ""
        msg = f"İndirilenler klasöründe {file_count} dosya toplam {size_str} yer kaplıyor.{top_str}"
        return True, msg, {"file_count": file_count, "total_bytes": total_bytes, "size_str": size_str}
    except Exception as e:
        logger.error(f"İndirilenler bilgisi alma hatası: {e}")
        return False, f"İndirilenler klasörü taranırken hata oluştu: {e}", {}


def resolve_file_organizer_command(user_text: str) -> Optional[str]:
    """
    Kullanıcının masaüstü ve dosya düzenleme komutlarını çözer.
    Örnek:
      - 'masaüstümü düzenle'
      - 'masaüstünü toparla'
      - 'masaüstünü temizle'
      - 'indirilenler klasörü ne kadar yer kaplıyor'
      - 'indirilenler boyutu'
    """
    cleaned = user_text.lower().strip().strip("?!.,")

    if any(k in cleaned for k in (
        "masaüstümü düzenle",
        "masaüstünü düzenle",
        "masaüstü düzenle",
        "masaüstümü toparla",
        "masaüstünü toparla",
        "masaüstü toparla",
        "masaüstünü temizle",
        "masaüstü temizle",
    )):
        ok, msg, _ = organize_desktop()
        return msg

    if any(k in cleaned for k in (
        "indirilenler klasörü ne kadar",
        "indirilenler ne kadar yer",
        "indirilenler boyutu",
        "indirilenler klasöründe ne kadar",
        "indirilenlerde ne kadar yer",
    )):
        ok, msg, _ = get_downloads_info()
        return msg

    return None
