"""
boru.tools.closed_loop
=======================
Closed-Loop Execution & Verification (Doğrulamalı Çalıştırma Motoru).

Ajanın körlemesine 'Açıldı', 'Kapandı' demesini engeller.
Her işletim sistemi eyleminden sonra arka plandaki gerçek durumu
(PID, tasklist, ses seviyesi veya pencere varlığı) sorgulayarak
asla yalan söylemeyen dürüst raporlama sağlar.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Yaygın Türkçe ve İngilizce uygulama eşleşmeleri
APP_NAME_TO_EXE = {
    "not defteri": "notepad.exe",
    "notepad": "notepad.exe",
    "hesap makinesi": "calc.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "tarayıcı": "chrome.exe",
    "browser": "chrome.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "msedge": "msedge.exe",
    "spotify": "spotify.exe",
    "müzik": "spotify.exe",
    "vs code": "code.exe",
    "vscode": "code.exe",
    "code": "code.exe",
    "terminal": "windowsterminal.exe",
    "powershell": "powershell.exe",
    "cmd": "cmd.exe",
    "komut istemi": "cmd.exe",
    "gezgin": "explorer.exe",
    "dosya gezgini": "explorer.exe",
    "explorer": "explorer.exe",
    "görev yöneticisi": "taskmgr.exe",
    "taskmgr": "taskmgr.exe",
    "paint": "mspaint.exe",
    "discord": "discord.exe",
    "telegram": "telegram.exe",
    "steam": "steam.exe",
}


class SystemExecutionVerifier:
    """
    Windows süreçlerini ve sistem durumunu doğrulayan sıfır bağımlılıklı denetim servisi.
    """

    @classmethod
    def resolve_exe_name(cls, app_name_or_alias: str) -> str:
        """Kullanıcının söylediği adı geçerli bir .exe adına çözümler."""
        cleaned = app_name_or_alias.lower().strip()
        normalized = re.sub(r"'(?:[ıiuüae]|y[ıiuüae]|n[ıiuüae])?$", "", cleaned).strip()
        normalized = re.sub(r"(?:ini|ını|unu|ünü|yi|yı|yu|yü|i|ı|u|ü)$", "", normalized).strip()

        if normalized in APP_NAME_TO_EXE:
            return APP_NAME_TO_EXE[normalized]
        if cleaned in APP_NAME_TO_EXE:
            return APP_NAME_TO_EXE[cleaned]

        if cleaned.endswith(".exe"):
            return cleaned
        return f"{normalized}.exe"

    @classmethod
    def is_process_running(cls, app_name_or_alias: str) -> bool:
        """
        Windows tasklist sorgusu ile sürecin aktif olarak çalışıp çalışmadığını doğrular.
        """
        exe_name = cls.resolve_exe_name(app_name_or_alias)

        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | 0x00000008

            res = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=3.0,
                startupinfo=startupinfo,
                creationflags=creationflags,
            )
            output = res.stdout.lower()
            if res.returncode == 0 and exe_name.lower() in output and "bilgi yok" not in output and "no tasks" not in output:
                return True
            return False
        except Exception as e:
            logger.debug(f"Süreç kontrol hatası ({exe_name}): {e}")
            return False

    @classmethod
    def verify_app_started(cls, app_name_or_alias: str, wait_seconds: float = 0.25, max_attempts: int = 3) -> Tuple[bool, str]:
        """
        Bir uygulamanın başlatıldığını doğrular.
        Kısa aralıklarla kontrol ederek sürecin belleğe oturmasını bekler.
        """
        exe_name = cls.resolve_exe_name(app_name_or_alias)
        display_name = app_name_or_alias.capitalize()

        for attempt in range(max_attempts):
            time.sleep(wait_seconds)
            if cls.is_process_running(exe_name):
                return True, f"Doğrulandı: {display_name} ({exe_name}) başarıyla başlatıldı ve arka planda çalışıyor."

        return False, f"Doğrulama Başarısız: {display_name} başlatma komutu verildi ancak arka planda '{exe_name}' süreci oluşmadı veya kapandı."

    @classmethod
    def verify_app_stopped(cls, app_name_or_alias: str, wait_seconds: float = 0.2, max_attempts: int = 3) -> Tuple[bool, str]:
        """
        Bir uygulamanın gerçekten sonlandırıldığını doğrular.
        """
        exe_name = cls.resolve_exe_name(app_name_or_alias)
        display_name = app_name_or_alias.capitalize()

        for attempt in range(max_attempts):
            time.sleep(wait_seconds)
            if not cls.is_process_running(exe_name):
                return True, f"Doğrulandı: {display_name} ({exe_name}) süreci başarıyla sonlandırıldı."

        return False, f"Doğrulama Uyarısı: {display_name} için sonlandırma komutu gönderildi ancak '{exe_name}' süreci hala bellekte çalışmaya devam ediyor."


class ClosedLoopActionExecutor:
    """
    İşletim sistemi eylemlerini çalıştıran ve ardından
    durumu denetleyerek dürüst sonuç döndüren yürütücü.
    """

    @classmethod
    def open_app_verified(cls, app_name: str) -> Tuple[bool, str]:
        """
        Uygulamayı açar ve arkasından sürecin çalıştığını kesin olarak teyit eder.
        """
        from boru.tools.system_tools import open_application
        ok_launch, msg_launch = open_application(app_name)
        if not ok_launch:
            return False, f"Başlatılamadı: {msg_launch}"

        # Web siteleri veya protokol çağrıları (.com / http / mailto) süreç listesinde görünmez, doğrudan döner
        if any(app_name.lower().startswith(p) for p in ("http://", "https://", "www.")) or "youtube" in app_name.lower():
            return True, msg_launch

        # Yerel Windows uygulaması ise sürecin varlığını doğrula
        verified, verify_msg = SystemExecutionVerifier.verify_app_started(app_name)
        if verified:
            return True, f"{app_name.capitalize()} açıldı (Süreç doğrulandı)."
        else:
            return False, f"{app_name.capitalize()} açılmaya çalışıldı ancak doğrulanamadı: Süreç yanıt vermedi."

    @classmethod
    def close_app_verified(cls, app_name: str, force_tree: bool = False) -> Tuple[bool, str]:
        """
        Uygulamayı sonlandırır ve ardından sürecin kapandığını doğrular.
        force_tree=True ise doğrudan /F /T ile zorla ağaç sonlandırması yapar.
        """
        exe_name = SystemExecutionVerifier.resolve_exe_name(app_name)
        display_name = app_name.capitalize()

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | 0x00000008

        cmd = ["taskkill"]
        if force_tree:
            cmd.extend(["/F", "/T"])
        else:
            cmd.append("/F")
        cmd.extend(["/IM", exe_name])

        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5.0,
                startupinfo=startupinfo,
                creationflags=creationflags,
            )
        except Exception as e:
            logger.debug(f"taskkill çalıştırma hatası ({exe_name}): {e}")

        # Sürecin gerçekten kapandığını doğrula
        verified, verify_msg = SystemExecutionVerifier.verify_app_stopped(exe_name)
        if verified:
            strat_info = "Zorla sonlandırılarak (Force Kill) " if force_tree else ""
            return True, f"{display_name} {strat_info}başarıyla kapatıldı (Doğrulandı)."
        else:
            return False, f"{display_name} kapatılmaya çalışıldı ancak süreç hala açık görünüyor."

