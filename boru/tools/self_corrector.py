"""
boru.tools.self_corrector
==========================
Börü Self-Correction & Multi-Strategy Fallback Engine.

Kullanıcı "Hala açık", "Kapanmadı" veya "Çalışmadı" dediğinde:
1. Ajan inatlaşmaz ve hatayı kabul eder.
2. Önceki başarısız eylemi ve hedefini (örn: Chrome veya Not Defteri) hatırlar.
3. Aynı başarısız komutu körü körüne tekrarlamaz; otomatik olarak bir üst kademedeki
   alternatif stratejiye (Tier 2: Force Kill / Tree Kill, Tier 3: PowerShell Force Kill) geçer.
4. Eylemi yeniden doğrular ve sonucu dürüstçe raporlar.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple

from boru.tools.closed_loop import ClosedLoopActionExecutor, SystemExecutionVerifier

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ActionRecord:
    action_type: str  # "close_app", "open_app", "play_music", "system_volume"
    target: str
    strategy_tier: int  # 1 = normal, 2 = fallback/force, 3 = deep kernel/ps
    success: bool
    timestamp: float


class ActionHistoryTracker:
    """
    Asistanın son yürüttüğü işletim sistemi eylemlerini hafızada tutan izleyici.
    """
    _instance: Optional[ActionHistoryTracker] = None
    _lock = threading.RLock()

    def __init__(self):
        self._last_action: Optional[ActionRecord] = None

    @classmethod
    def get_instance(cls) -> ActionHistoryTracker:
        with cls._lock:
            if cls._instance is None:
                cls._instance = ActionHistoryTracker()
            return cls._instance

    def record_action(
        self,
        action_type: str,
        target: str,
        strategy_tier: int = 1,
        success: bool = True,
    ) -> None:
        with self._lock:
            self._last_action = ActionRecord(
                action_type=action_type,
                target=target,
                strategy_tier=strategy_tier,
                success=success,
                timestamp=time.time(),
            )

    def get_last_action(self) -> Optional[ActionRecord]:
        with self._lock:
            return self._last_action

    def clear(self) -> None:
        with self._lock:
            self._last_action = None


class SelfCorrectionDispatcher:
    """
    Başarısız eylemleri tespit edip alternatif stratejileri yürüten düzeltici.
    """

    @classmethod
    def handle_correction(cls, user_text: str) -> Optional[str]:
        """
        Kullanıcının "Hala açık", "Kapanmadı", "Açılmadı" gibi düzeltme ifadelerini
        önceki eylem bağlamıyla eşleştirip alternatif strateji uygular.
        Eğer eşleşen bir düzeltme yoksa None döner.
        """
        cleaned = user_text.lower().strip()
        tracker = ActionHistoryTracker.get_instance()
        last = tracker.get_last_action()

        # Son eylem yoksa veya çok eskiyse (örn. 5 dakikadan önce yapılmışsa)
        if last is None or (time.time() - last.timestamp > 300):
            return None

        # ── Durum 1: "Hala açık", "Kapanmadı", "Gitmedi", "Kapatamadın" ──────────
        is_close_complaint = any(k in cleaned for k in (
            "hala açık", "kapanmadı", "kapanmamış", "kapatamadın", "gitmedi",
            "kapatmadın", "duruyor", "hala çalışıyor"
        ))

        if is_close_complaint and last.action_type == "close_app":
            target = last.target
            current_tier = last.strategy_tier

            if current_tier == 1:
                # 2. Kademe Strateji: Force Tree Kill (/F /T)
                logger.info(f"Self-Correction: {target} için Strateji 2 (Force Tree Kill) uygulanıyor.")
                ok, msg = ClosedLoopActionExecutor.close_app_verified(target, force_tree=True)
                if ok:
                    tracker.record_action("close_app", target, strategy_tier=2, success=True)
                    return (
                        f"Haklısınız, ilk kapatma sinyali yanıt vermemiş. "
                        f"Alternatif Strateji (Zorla Ağaç Sonlandırma / Force Kill) devreye sokuldu; "
                        f"{target.capitalize()} başarıyla tamamen kapatıldı ve süreç doğrulandı."
                    )
                else:
                    # 3. Kademe Strateji: PowerShell Stop-Process -Force
                    return cls._execute_tier3_kill(target)

            elif current_tier >= 2:
                # 3. Kademe Strateji: PowerShell Stop-Process
                return cls._execute_tier3_kill(target)

        # ── Durum 2: "Açılmadı", "Başlamadı", "Çalışmadı" (Uygulama Açma Düzeltmesi)
        is_open_complaint = any(k in cleaned for k in (
            "açılmadı", "açılmamış", "başlamadı", "başlatamadın", "çalışmadı"
        ))

        if is_open_complaint and last.action_type == "open_app":
            target = last.target
            logger.info(f"Self-Correction: {target} açma için Strateji 2 (Shell Start) uygulanıyor.")
            # Alternatif Strateji 2: CMD /c start
            try:
                subprocess.Popen(f'cmd.exe /c start "" "{target}"', shell=True)
                verified, _ = SystemExecutionVerifier.verify_app_started(target, wait_seconds=0.4, max_attempts=3)
                if verified:
                    tracker.record_action("open_app", target, strategy_tier=2, success=True)
                    return (
                        f"Önceki başlatma denemesi başarısız olmuştu. "
                        f"Alternatif kabuk başlatıcı (Shell Start) stratejisiyle {target.capitalize()} "
                        f"başlatıldı ve sürecin çalıştığı doğrulandı."
                    )
            except Exception as e:
                logger.debug(f"Shell start hatası: {e}")

            return (
                f"Kusura bakmayın, {target.capitalize()} uygulamasını alternatif başlatıcıyla da "
                f"çalıştırmayı denedim ancak işletim sistemi süreci başlatamadı. "
                f"Uygulamanın kurulu olduğundan ve yolunun doğru olduğundan emin misiniz?"
            )

        # ── Durum 3: Müzik Çalmadı Düzeltmesi ──────────────────────────────────
        is_music_complaint = any(k in cleaned for k in ("şarkı çalmadı", "müzik çalmadı", "çalmıyor", "ses gelmiyor"))
        if is_music_complaint and last.action_type == "play_music":
            target = last.target
            logger.info(f"Self-Correction: {target} müzik için Strateji 2 (Tarayıcı YouTube Fallback) uygulanıyor.")
            import urllib.parse
            import webbrowser
            encoded = urllib.parse.quote_plus(target)
            yt_url = f"https://www.youtube.com/results?search_query={encoded}"
            webbrowser.open(yt_url)
            tracker.record_action("play_music", target, strategy_tier=2, success=True)
            return (
                f"Spotify istemcisi parçayı başlatamadığı için alternatif strateji devreye alındı: "
                f"'{target}' parçasını dinleyebilmeniz için YouTube Web üzerinde otomatik açtım."
            )

        return None

    @classmethod
    def _execute_tier3_kill(cls, app_name: str) -> str:
        """3. Seviye Derin Kapatma: PowerShell Stop-Process -Force"""
        exe_name = SystemExecutionVerifier.resolve_exe_name(app_name)
        base_name = exe_name.replace(".exe", "")
        tracker = ActionHistoryTracker.get_instance()

        try:
            ps_cmd = f"Get-Process -Name '{base_name}' -ErrorAction SilentlyContinue | Stop-Process -Force"
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, timeout=5)
            time.sleep(0.3)
            verified, _ = SystemExecutionVerifier.verify_app_stopped(exe_name)
            if verified:
                tracker.record_action("close_app", app_name, strategy_tier=3, success=True)
                return (
                    f"Standart yöntemler yanıt vermediği için en yüksek seviye (PowerShell Force Kill) "
                    f"stratejisi uygulandı; {app_name.capitalize()} süreci tamamen sonlandırıldı ve doğrulandı."
                )
        except Exception as e:
            logger.debug(f"PowerShell Stop-Process hatası: {e}")

        return (
            f"{app_name.capitalize()} kapatılmaya çalışıldı ancak sistem düzeyinde kilitlenmiş görünüyor. "
            f"Lütfen Görev Yöneticisi üzerinden kontrol ediniz."
        )

