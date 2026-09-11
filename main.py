import argparse
import logging
import sys
from boru.release import build_release, _RELEASES

logger = logging.getLogger(__name__)


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
    args = parser.parse_args()
    app = build_release(version=args.version)

    if args.ui == "modern":
        try:
            import threading
            import time
            from boru.ui_modern_webview import run_modern_app

            app.withdraw()

            # Tkinter olay döngüsünü ve arka plan servislerini canlı tutan pompa
            def _pump_tkinter():
                while True:
                    time.sleep(0.04)
                    try:
                        app.update_idletasks()
                        app.update()
                    except Exception:
                        break

            threading.Thread(target=_pump_tkinter, daemon=True, name="BoruTkPump").start()

            modern_window_ref = [None]

            def _toggle_voice():
                if getattr(app, "_toggle_continuous_voice", None):
                    app._toggle_continuous_voice()
                    is_active = bool(getattr(app, "_continuous_voice", None) and app._continuous_voice.is_active)
                    if modern_window_ref[0]:
                        try:
                            modern_window_ref[0].evaluate_js(f"updateMicState({str(is_active).lower()})")
                        except Exception:
                            pass
                    return is_active
                return False

            def _open_spotlight():
                if getattr(app, "_jarvis_overlay", None):
                    app._jarvis_overlay.show()

            # Global hotkey'leri doğrudan modern UI ve ses sistemine bağla
            if getattr(app, "_hotkey_mgr", None):
                app._hotkey_mgr.stop()
                from boru.hotkey import GlobalHotkeyManager
                modern_hotkey_mgr = GlobalHotkeyManager()
                modern_hotkey_mgr.register("ctrl+shift+j", _toggle_voice)
                modern_hotkey_mgr.register("ctrl+shift+b", _open_spotlight)
                modern_hotkey_mgr.start()
                app._hotkey_mgr = modern_hotkey_mgr

            def _on_window_created(win):
                modern_window_ref[0] = win

            run_modern_app(
                assistant=app._assistant,
                title=f"Börü {args.version} — Yeni Nesil Yapay Zekâ",
                on_voice_toggle=_toggle_voice,
                on_open_spotlight=_open_spotlight,
                on_window_created=_on_window_created,
            )
            return
        except Exception as e:
            logger.warning(f"Modern WebView başlatılamadı, klasik arayüze dönülüyor: {e}")
            app.deiconify()

    app.mainloop()


if __name__ == "__main__":
    main()
