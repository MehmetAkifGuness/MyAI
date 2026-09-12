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


DEFAULT_CLEANUP_JOURNAL = Path(__file__).resolve().parent.parent.parent / "data" / "desktop_cleanup_journal.json"


def organize_desktop(
    desktop_dir: Optional[Path | str] = None,
    preview: bool = False,
    journal_file: Optional[Path | str] = None,
) -> Tuple[bool, str, Dict[str, int]]:
    """
    Masaüstündeki gevşek dosyaları ilgili alt klasörlere (Belgeler, Görseller vb.) taşır.
    Masaüstü kısayollarına (.lnk, .url) ve klasörlere kesinlikle dokunmaz.
    preview=True olduğunda dosyaları taşımaz, yalnızca yapılacak işlemin önizlemesini sunar.
    """
    import json
    import time
    desk_path = Path(desktop_dir) if desktop_dir else _get_desktop_path()
    if not desk_path.exists():
        return False, "Masaüstü klasörü bulunamadı.", {}

    moved_counts: Dict[str, int] = {}
    planned_moves: List[Tuple[Path, Path, str]] = []

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
            target_file = target_folder / item.name
            counter = 1
            while target_file.exists():
                target_file = target_folder / f"{item.stem}_{counter}{item.suffix}"
                counter += 1

            planned_moves.append((item, target_file, category))
            moved_counts[category] = moved_counts.get(category, 0) + 1

        total_files = len(planned_moves)
        if total_files == 0:
            return True, "Masaüstünüz zaten tamamen düzenli. Taşınacak dosya bulunamadı.", {}

        parts = [f"{count} {cat.lower()}" for cat, count in moved_counts.items()]

        if preview:
            msg = (
                f"📋 Masaüstü Düzenleme Önizlemesi:\n"
                f"Toplam {total_files} dosya düzenlenecek ({', '.join(parts)} ilgili klasörlere taşınacak).\n"
                f"Onaylıyorsanız 'Masaüstümü düzenle' diyerek taşıma işlemini hemen başlatabilirsiniz."
            )
            return True, msg, moved_counts

        # Gerçek taşıma ve geri alma günlüğü (journal)
        journal_entries = []
        for src, dst, cat in planned_moves:
            dst.parent.mkdir(exist_ok=True)
            shutil.move(str(src), str(dst))
            journal_entries.append({
                "source": str(src),
                "destination": str(dst),
                "category": cat,
                "timestamp": time.time(),
            })

        j_path = Path(journal_file) if journal_file else DEFAULT_CLEANUP_JOURNAL
        try:
            j_path.parent.mkdir(parents=True, exist_ok=True)
            existing_journal = []
            if j_path.exists():
                try:
                    with open(j_path, "r", encoding="utf-8") as jf:
                        existing_journal = json.load(jf)
                except Exception:
                    pass
            existing_journal.extend(journal_entries)
            tmp_j = j_path.with_suffix(".tmp")
            with open(tmp_j, "w", encoding="utf-8") as jf:
                json.dump(existing_journal, jf, ensure_ascii=False, indent=2)
            os.replace(tmp_j, j_path)
            try:
                from boru.persistence.database import BoruDatabase
                BoruDatabase.get_instance().add_cleanup_entries(journal_entries)
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"Masaüstü geri alma günlüğü kaydedilemedi: {e}")

        msg = (
            f"Masaüstündeki toplam {total_files} dosya düzenlendi "
            f"({', '.join(parts)} ilgili klasörlere taşındı).\n"
            f"İstediğiniz zaman 'Masaüstü düzenlemesini geri al' diyerek eski haline döndürebilirsiniz."
        )
        return True, msg, moved_counts
    except Exception as e:
        logger.error(f"Masaüstü düzenleme hatası: {e}")
        return False, f"Masaüstü düzenlenirken hata oluştu: {e}", {}


def undo_organize_desktop(journal_file: Optional[Path | str] = None) -> Tuple[bool, str]:
    """
    Son masaüstü düzenleme işleminde taşınan dosyaları orijinal konumlarına geri döndürür.
    """
    import json
    j_path = Path(journal_file) if journal_file else DEFAULT_CLEANUP_JOURNAL
    if not j_path.exists():
        return False, "Geri alınacak bir masaüstü düzenleme geçmişi bulunamadı."

    try:
        with open(j_path, "r", encoding="utf-8") as f:
            entries = json.load(f)
        if not entries or not isinstance(entries, list):
            return False, "Geri alınacak işlem kaydı bulunamadı."

        restored_count = 0
        for entry in reversed(entries):
            src_str = entry.get("source")
            dst_str = entry.get("destination")
            if not src_str or not dst_str:
                continue
            src = Path(src_str)
            dst = Path(dst_str)
            if dst.exists():
                src.parent.mkdir(parents=True, exist_ok=True)
                final_src = src
                counter = 1
                while final_src.exists():
                    final_src = src.parent / f"{src.stem}_geri_{counter}{src.suffix}"
                    counter += 1
                shutil.move(str(dst), str(final_src))
                restored_count += 1

        # Günlüğü temizle
        try:
            os.remove(j_path)
        except Exception:
            pass
        try:
            from boru.persistence.database import BoruDatabase
            BoruDatabase.get_instance().clear_cleanup_journal()
        except Exception:
            pass

        if restored_count == 0:
            return True, "Geri taşınacak dosya bulunamadı veya dosyalar zaten taşınmış."
        return True, f"Masaüstü düzenlemesi başarıyla geri alındı. Toplam {restored_count} dosya orijinal yerine döndürüldü."
    except Exception as e:
        logger.error(f"Masaüstü geri alma hatası: {e}")
        return False, f"Geri alma sırasında hata oluştu: {e}"


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

    # Geri alma (Undo)
    if any(k in cleaned for k in (
        "masaüstü düzenlemesini geri al",
        "masaüstünü geri al",
        "masaüstü geri al",
        "düzenlemeyi geri al",
        "taşınan dosyaları geri al",
        "masaüstünü geri yükle",
    )):
        ok, msg = undo_organize_desktop()
        return msg

    # Önizleme (Dry-run / Preview)
    if any(k in cleaned for k in (
        "masaüstü düzenleme önizleme",
        "düzenlemeden önce göster",
        "masaüstünü düzenlemeden önce göster",
        "masaüstü önizleme",
        "masaüstü önizlemesi",
        "ne taşınacak",
    )):
        ok, msg, _ = organize_desktop(preview=True)
        return msg

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

