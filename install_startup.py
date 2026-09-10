"""
Börü — Windows Başlangıç Kurulum Yöneticisi (Auto-Start Installer)
=================================================================
Bilgisayar her açıldığında Börü'nün arka planda sessizce (pythonw ile)
otomatik olarak başlamasını sağlar.

Kullanım:
  python install_startup.py           (Kurulum yapar)
  python install_startup.py --status  (Durumu kontrol eder)
  python install_startup.py --remove  (Başlangıçtan kaldırır)
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def get_startup_folder() -> Path:
    """Windows Başlangıç (Startup) klasörü yolunu döndürür."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        p = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if p.exists():
            return p

    # Yedek yöntem: PowerShell ile sorgula
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Startup')"],
            capture_output=True,
            text=True,
            check=True,
        )
        out = res.stdout.strip()
        if out:
            return Path(out)
    except Exception:
        pass

    raise RuntimeError("Windows Başlangıç (Startup) klasörü bulunamadı.")


def get_pythonw_path() -> Path:
    """Mevcut Python ortamının pythonw.exe yolunu döndürür."""
    python_dir = Path(sys.executable).parent
    pythonw = python_dir / "pythonw.exe"
    if pythonw.exists():
        return pythonw
    return Path(sys.executable)


def install_startup(project_dir: Path | None = None) -> None:
    if project_dir is None:
        local_dir = Path(r"C:\Users\gunes\KendiYapayZekam")
        if local_dir.exists():
            project_dir = local_dir
        else:
            project_dir = Path(__file__).resolve().parent

    daemon_script = project_dir / "run_daemon.py"
    if not daemon_script.exists():
        raise FileNotFoundError(f"Daemon başlatıcısı bulunamadı: {daemon_script}")

    startup_dir = get_startup_folder()
    pythonw = get_pythonw_path()
    target_vbs = startup_dir / "Boru_AI_Asistan.vbs"

    # Sessiz VBScript içeriği
    vbs_content = (
        'Set WshShell = CreateObject("WScript.Shell")\n'
        f'WshShell.CurrentDirectory = "{str(project_dir)}"\n'
        f'WshShell.Run """{str(pythonw)}"" ""{str(daemon_script)}""", 0, False\n'
    )

    with open(target_vbs, "w", encoding="utf-8") as f:
        f.write(vbs_content)

    print("==================================================================")
    print("✔ BÖRÜ BAŞARIYLA WİNDOWS BAŞLANGIÇ KLASÖRÜNE EKLENDİ!")
    print(f"📁 Başlangıç Dosyası : {target_vbs}")
    print(f"🐍 Pythonw Yolu       : {pythonw}")
    print(f"🚀 Proje Dizini       : {project_dir}")
    print("==================================================================")
    print("Artık bilgisayarınız her açıldığında Börü arka planda sessizce bekleyecek,")
    print("'Börü' veya 'Hey Börü' dediğinizde ya da Ctrl+Shift+B bastığınızda ekrana gelecektir.")


def remove_startup() -> None:
    startup_dir = get_startup_folder()
    target_vbs = startup_dir / "Boru_AI_Asistan.vbs"
    if target_vbs.exists():
        target_vbs.unlink()
        print(f"✔ Börü başlangıçtan kaldırıldı: {target_vbs}")
    else:
        print("ℹ Börü zaten başlangıç klasöründe kurulu değil.")


def check_status() -> None:
    startup_dir = get_startup_folder()
    target_vbs = startup_dir / "Boru_AI_Asistan.vbs"
    if target_vbs.exists():
        print(f"🟢 BÖRÜ AKTİF: Windows başlangıcında otomatik çalışıyor ({target_vbs})")
    else:
        print("⚪ BÖRÜ PASİF: Windows başlangıcında kurulu değil.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Börü Windows Başlangıç Kurulum Yöneticisi")
    parser.add_argument("--status", action="store_true", help="Kurulum durumunu kontrol et")
    parser.add_argument("--remove", action="store_true", help="Başlangıçtan kaldır")
    args = parser.parse_args()

    if args.status:
        check_status()
    elif args.remove:
        remove_startup()
    else:
        install_startup()
