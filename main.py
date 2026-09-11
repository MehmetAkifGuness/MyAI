import argparse
import json
import logging
import os
import subprocess
import sys
from boru.release import build_release, _RELEASES

# pythonw altında stdout/stderr None olabilir, çökmeyi önle
if sys.stdout is None:
    try:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        pass
if sys.stderr is None:
    try:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        pass

logger = logging.getLogger(__name__)


def _cleanup_stale_processes():
    try:
        current_pid = os.getpid()
        ps_script = (
            "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
            "Select-Object ProcessId, CommandLine | "
            "ConvertTo-Json -Compress"
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return
        data = json.loads(proc.stdout.strip())
        if isinstance(data, dict):
            data = [data]
        for item in data:
            if not isinstance(item, dict):
                continue
            pid = item.get("ProcessId")
            cmdline = (item.get("CommandLine") or "").lower()
            if pid and pid != current_pid and ("run_daemon.py" in cmdline or ("main.py" in cmdline and "pytest" not in cmdline)):
                try:
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=2)
                except Exception:
                    pass
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="Börü - Yerel Yapay Zekâ ve Otonom Kodlama Asistanı")
    parser.add_argument(
        "--version",
        default="V13.0",
        choices=_RELEASES,
        help="Başlatılacak sürüm dönüm noktası (varsayılan: V13.0)",
    )
    parser.add_argument(
        "--ui",
        default="modern",
        choices=["modern", "classic"],
        help="Arayüz stili: 'modern' (2026 WebView2 Glassmorphic Arayüz) veya 'classic' (CustomTkinter)",
    )
    parser.add_argument(
        "--silent",
        "--minimized",
        action="store_true",
        dest="silent",
        help="Uygulamayı ekranda pencere açmadan, doğrudan sistem tepsisinde (arka planda) başlatır.",
    )
    args = parser.parse_args()
    _cleanup_stale_processes()
    app = build_release(version=args.version)

    if args.ui == "modern":
        try:
            from boru.ui_modern_webview import run_modern_app

            app.withdraw()
            # NOT: _suppress_tk_overlay artık ayarlanmıyor —
            # Tkinter JarvisOverlayWindow yerine yeni WebView2 overlay kullanıyoruz.

            modern_window_ref = [None]
            overlay_window_ref = [None]   # WebView2 sesli diyalog overlay penceresi
            _allow_exit = [False]

            def _show_modern_window():
                if modern_window_ref[0]:
                    try:
                        modern_window_ref[0].show()
                        modern_window_ref[0].restore()
                    except Exception:
                        pass

            def _on_voice_state_changed(is_active: bool):
                if modern_window_ref[0]:
                    try:
                        modern_window_ref[0].evaluate_js(f"updateMicState({str(is_active).lower()})")
                    except Exception:
                        pass
                # Win32 hotkey yoluyla tetiklendiğinde de overlay göster/gizle
                if overlay_window_ref[0]:
                    try:
                        if is_active:
                            overlay_window_ref[0].show()
                        else:
                            overlay_window_ref[0].hide()
                    except Exception:
                        pass

            def _on_speech_recognized(user_text: str, bot_reply: str):
                import json
                u_json = json.dumps(user_text)
                b_json = json.dumps(bot_reply)
                if modern_window_ref[0]:
                    try:
                        modern_window_ref[0].evaluate_js(f"appendSpeechExchange({u_json}, {b_json})")
                    except Exception:
                        pass
                # Overlay'i de güncelle ve görünür yap
                if overlay_window_ref[0]:
                    try:
                        overlay_window_ref[0].show()
                        overlay_window_ref[0].evaluate_js(f"addExchange({u_json}, {b_json})")
                    except Exception:
                        pass

            def _on_voice_status(text: str, color: str):
                import json
                t_json = json.dumps(text)
                c_json = json.dumps(color)
                if modern_window_ref[0]:
                    try:
                        modern_window_ref[0].evaluate_js(f"updateVoiceStatus({t_json}, {c_json})")
                    except Exception:
                        pass
                # Overlay durum rozetini de güncelle
                if overlay_window_ref[0]:
                    try:
                        overlay_window_ref[0].evaluate_js(f"updateStatus({t_json}, {c_json})")
                    except Exception:
                        pass

            def _toggle_voice():
                if getattr(app, "_toggle_continuous_voice", None):
                    app._toggle_continuous_voice()
                    is_active = bool(getattr(app, "_continuous_voice", None) and app._continuous_voice.is_active)
                    # Ses başladıysa overlay'i göster, durduysa gizle
                    if overlay_window_ref[0]:
                        try:
                            if is_active:
                                overlay_window_ref[0].show()
                            else:
                                overlay_window_ref[0].hide()
                        except Exception:
                            pass
                    return is_active
                return False

            def _open_spotlight():
                _show_modern_window()
                if modern_window_ref[0]:
                    try:
                        modern_window_ref[0].evaluate_js("switchTab('tools')")
                    except Exception:
                        pass

            def _on_window_closing():
                if _allow_exit[0]:
                    return True  # Gerçek çıkışa izin ver
                if modern_window_ref[0]:
                    try:
                        modern_window_ref[0].hide()
                    except Exception:
                        pass
                if getattr(app, "_tray", None) and app._tray.is_running:
                    try:
                        app._tray.notify(
                            "🐺 Börü Arka Planda Aktif",
                            "Börü saatin yanında çalışmaya devam ediyor. Açmak için simgeye tıklayabilir veya Ctrl+Shift+B tuşlayabilirsiniz.",
                        )
                    except Exception:
                        pass
                return False  # Pencereyi kapatma, arka planda gizle!

            def _full_exit():
                _allow_exit[0] = True
                if getattr(app, "_tray", None):
                    try:
                        app._tray.stop()
                    except Exception:
                        pass
                if getattr(app, "_continuous_voice", None):
                    try:
                        app._continuous_voice.stop()
                    except Exception:
                        pass
                if getattr(app, "_wake_listener", None):
                    try:
                        app._wake_listener.stop()
                    except Exception:
                        pass
                if getattr(app, "_hotkey_mgr", None):
                    try:
                        app._hotkey_mgr.stop()
                    except Exception:
                        pass
                if overlay_window_ref[0]:
                    try:
                        overlay_window_ref[0].destroy()
                    except Exception:
                        pass
                if modern_window_ref[0]:
                    try:
                        modern_window_ref[0].destroy()
                    except Exception:
                        pass
                try:
                    app.destroy()
                except Exception:
                    pass
                import os
                os._exit(0)

            # Sistem tepsisi (System Tray) menü aksiyonlarını modern arayüze bağla
            if getattr(app, "_tray", None):
                app._tray._on_open = _show_modern_window
                app._tray._on_voice = _toggle_voice
                app._tray._on_spotlight = _open_spotlight
                app._tray._on_exit = _full_exit

            app._on_voice_state_changed_listener = _on_voice_state_changed
            app._on_speech_recognized_listener = _on_speech_recognized
            app._on_voice_status_listener = _on_voice_status
            app._on_spotlight_custom = _open_spotlight

            def _on_window_created(win):
                modern_window_ref[0] = win

            def _on_overlay_window_created(ov_win, ov_api):
                """Overlay penceresi oluşturulduğunda VoiceOverlayApi callback'lerini bağlar."""
                overlay_window_ref[0] = ov_win
                # Overlay'den gelen komutları main.py bağlamında yönet
                ov_api._on_toggle_voice = _toggle_voice
                ov_api._on_open_main = _show_modern_window
                ov_api._on_close = lambda: _safe_hide_overlay(ov_win)
                ov_api._on_execute_command = lambda cmd: app._assistant.reply(cmd) if getattr(app, "_assistant", None) else f"Alındı: {cmd}"

            def _safe_hide_overlay(ov_win):
                try:
                    ov_win.hide()
                except Exception:
                    pass

            try:
                run_modern_app(
                    assistant=app._assistant,
                    title=f"Börü {args.version} — Yeni Nesil Yapay Zekâ",
                    on_voice_toggle=_toggle_voice,
                    on_open_spotlight=_open_spotlight,
                    on_window_created=_on_window_created,
                    on_closing=_on_window_closing,
                    on_overlay_window_created=_on_overlay_window_created,
                    hidden=bool(args.silent),
                )
            finally:
                _full_exit()
            return
        except Exception as e:
            logger.warning(f"Modern WebView başlatılamadı, klasik arayüze dönülüyor: {e}")
            app.deiconify()

    app.mainloop()


if __name__ == "__main__":
    main()
