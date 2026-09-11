"""
Börü AI — Windows Kalıcı Servis & Arka Plan Yöneticisi
======================================================
IDE (VS Code / Antigravity) kapalı olsa bile Börü'nün arka planda bir Windows
servisi gibi kesintisiz çalışmasını sağlar.

Kullanım:
  python boru_service.py install     (Windows Görev Zamanlayıcı'ya otomatik servis olarak kaydeder)
  python boru_service.py start       (Arka planda bağımsız daemon olarak hemen başlatır)
  python boru_service.py stop        (Çalışan tüm Börü süreçlerini durdurur)
  python boru_service.py status      (Servis ve süreç durumunu kontrol eder)
  python boru_service.py uninstall   (Servisi kaldırır)
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

TASK_NAME = "BoruAIService"


def get_project_root() -> Path:
    here = Path(__file__).resolve().parent
    if (here / "main.py").exists():
        return here
    primary = Path(r"C:\Users\gunes\KendiYapayZekam")
    if (primary / "main.py").exists():
        return primary
    return here


def get_pythonw() -> Path:
    py_dir = Path(sys.executable).parent
    pythonw = py_dir / "pythonw.exe"
    if pythonw.exists():
        return pythonw
    return Path(sys.executable)


def install_service() -> bool:
    """Windows Görev Zamanlayıcı'ya (Task Scheduler) Börü'yü otomatik servis olarak kaydeder."""
    project_root = get_project_root()
    pythonw = get_pythonw()
    main_py = project_root / "main.py"

    if not main_py.exists():
        print(f"❌ main.py bulunamadı: {main_py}")
        return False

    vbs_path = project_root / "Boru_ArkaPlan.vbs"
    vbs_content = (
        'Set WshShell = CreateObject("WScript.Shell")\n'
        f'WshShell.CurrentDirectory = "{str(project_root)}"\n'
        f'WshShell.Run """{str(sys.executable)}"" ""{str(main_py)}"" --silent", 0, False\n'
    )
    with open(vbs_path, "w", encoding="utf-8") as f:
        f.write(vbs_content)

    # Windows Başlangıç klasörüne de VBS ekle
    appdata = os.environ.get("APPDATA")
    if appdata:
        startup_vbs = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "Boru_AI_Asistan.vbs"
        try:
            with open(startup_vbs, "w", encoding="utf-8") as f:
                f.write(vbs_content)
        except Exception:
            pass

    # Windows Kayıt Defteri (HKCU Run - Yönetici izni gerektirmez)
    try:
        reg_cmd = [
            "reg", "add", "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
            "/v", "BoruAI",
            "/t", "REG_SZ",
            "/d", f'wscript.exe "{str(vbs_path)}"',
            "/f"
        ]
        subprocess.run(reg_cmd, capture_output=True)
        print("✔ Windows Kayıt Defteri (Run) başlangıç anahtarı eklendi.")
    except Exception:
        pass

    cmd = [
        "schtasks", "/create",
        "/tn", TASK_NAME,
        "/tr", f'wscript.exe "{str(vbs_path)}"',
        "/sc", "onlogon",
        "/rl", "limited",
        "/f"
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            print(f"✔ '{TASK_NAME}' Windows Görev Zamanlayıcı'ya başarıyla kaydedildi!")
        print(f"📁 Çalışma Dizini: {project_root}")
        print(f"🚀 Başlatıcı     : {vbs_path}")
        print("Artık bilgisayar her açıldığında Börü IDE'den bağımsız olarak arka planda çalışacak.")
        return True
    except Exception as e:
        print(f"Hata: {e}")
        return False


def uninstall_service() -> bool:
    """Görev Zamanlayıcı'dan, Başlangıç klasöründen ve Kayıt Defterinden kaldırır."""
    try:
        subprocess.run(["schtasks", "/delete", "/tn", TASK_NAME, "/f"], capture_output=True)
        print(f"✔ '{TASK_NAME}' Görev Zamanlayıcı'dan silindi.")
    except Exception:
        pass

    try:
        subprocess.run(["reg", "delete", "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run", "/v", "BoruAI", "/f"], capture_output=True)
        print("✔ Kayıt Defteri (Run) anahtarı silindi.")
    except Exception:
        pass

    appdata = os.environ.get("APPDATA")
    if appdata:
        startup_vbs = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "Boru_AI_Asistan.vbs"
        if startup_vbs.exists():
            try:
                startup_vbs.unlink()
                print(f"✔ Başlangıç kısayolu kaldırıldı: {startup_vbs}")
            except Exception:
                pass
    return True


def get_running_boru_processes() -> list[dict]:
    """Çalışan python/pythonw süreçlerinden Börü'ye ait olanları JSON ile tespit eder."""
    ps_script = (
        "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
        "Select-Object ProcessId, WorkingSetSize, CommandLine | "
        "ConvertTo-Json -Compress"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return []
        data = json.loads(proc.stdout.strip())
        if isinstance(data, dict):
            data = [data]
        res = []
        for item in data:
            if not isinstance(item, dict):
                continue
            cmd = (item.get("CommandLine") or "").lower()
            pid = item.get("ProcessId")
            ws = item.get("WorkingSetSize") or 0
            if pid and ("main.py" in cmd or "run_daemon.py" in cmd) and "pytest" not in cmd:
                res.append({"pid": int(pid), "ws": int(ws), "cmd": cmd})
        return res
    except Exception:
        return []


def start_service() -> bool:
    """Börü'yü bağımsız, terminalden kopuk (detached) bir Windows süreci olarak başlatır."""
    stop_service(quiet=True)
    time.sleep(0.5)

    project_root = get_project_root()
    pythonw = get_pythonw()
    main_py = project_root / "main.py"

    try:
        subprocess.Popen(
            [str(pythonw), str(main_py), "--silent"],
            cwd=str(project_root),
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
        time.sleep(2.5)
        print("✔ Börü arka plan servisi bağımsız olarak başlatıldı!")
        print("💡 IDE'yi (VS Code) kapatsanız dahi Börü arka planda çalışmaya devam eder.")
        print("💡 Kısayollar: Ctrl + Shift + J (Sesli Asistan), Ctrl + Shift + B (Arayüz)")
        return True
    except Exception as e:
        print(f"❌ Başlatma hatası: {e}")
        return False


def stop_service(quiet: bool = False) -> bool:
    """Çalışan tüm Börü süreçlerini (main.py, pythonw, run_daemon) sonlandırır."""
    killed = 0
    try:
        procs = get_running_boru_processes()
        for p in procs:
            try:
                subprocess.run(["taskkill", "/F", "/PID", str(p["pid"])], capture_output=True, timeout=3)
                killed += 1
            except Exception:
                pass
    except Exception as e:
        if not quiet:
            print(f"Hata: {e}")

    if not quiet:
        if killed > 0:
            print(f"✔ {killed} adet Börü süreci sonlandırıldı.")
        else:
            print("ℹ Çalışan aktif Börü süreci bulunamadı.")
    return True


def status_service() -> None:
    """Servis ve çalışan süreçlerin durumunu gösterir."""
    running_instances = get_running_boru_processes()

    print("==================================================================")
    print("🐺 BÖRÜ AI SERVİS DURUMU")
    print("==================================================================")
    if running_instances:
        print(f"🟢 DURUM: AKTİF ÇALIŞIYOR ({len(running_instances)} süreç)")
        for inst in running_instances:
            pid = inst["pid"]
            mb = inst["ws"] / (1024 * 1024)
            cmd = inst["cmd"]
            print(f"   ▶ PID: {pid} | Bellek: {mb:.1f} MB | {cmd[:60]}...")
    else:
        print("⚪ DURUM: ÇALIŞMIYOR")

    try:
        reg_res = subprocess.run(["reg", "query", "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run", "/v", "BoruAI"], capture_output=True, text=True, errors="replace")
        if reg_res.returncode == 0:
            print("🟢 BAŞLANGIÇ KAYDI: Windows Kayıt Defteri (Run) kurulu ve aktif.")
        else:
            print("⚪ BAŞLANGIÇ KAYDI: Windows Kayıt Defteri (Run) kurulu değil.")
    except Exception:
        pass

    try:
        res = subprocess.run(["schtasks", "/query", "/tn", TASK_NAME], capture_output=True, text=True, errors="replace")
        if res.returncode == 0:
            print(f"🟢 GÖREV ZAMANLAYICI: '{TASK_NAME}' kurulu ve aktif.")
        else:
            print(f"⚪ GÖREV ZAMANLAYICI: '{TASK_NAME}' kurulu değil.")
    except Exception:
        pass
    print("==================================================================")


def main():
    parser = argparse.ArgumentParser(description="Börü AI Kalıcı Arka Plan Servis Yöneticisi")
    parser.add_argument("action", choices=["install", "start", "stop", "restart", "status", "uninstall"],
                        nargs="?", default="status", help="İşlem seçin")
    args = parser.parse_args()

    if args.action == "install":
        install_service()
    elif args.action == "uninstall":
        uninstall_service()
    elif args.action == "start":
        start_service()
    elif args.action == "stop":
        stop_service()
    elif args.action == "restart":
        stop_service()
        time.sleep(1)
        start_service()
    elif args.action == "status":
        status_service()


if __name__ == "__main__":
    main()
