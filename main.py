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
            from boru.ui_modern_webview import run_modern_app

            app.withdraw()
            app._suppress_tk_overlay = True

            modern_window_ref = [None]
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

            def _toggle_voice():
                if getattr(app, "_toggle_continuous_voice", None):
                    app._toggle_continuous_voice()
                    return bool(getattr(app, "_continuous_voice", None) and app._continuous_voice.is_active)
                return False

            def _open_spotlight():
                _show_modern_window()
                if modern_window_ref[0]:
                    try:
                        modern_window_ref[0].evaluate_js("switchTab('actions')")
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
            app._on_spotlight_custom = _open_spotlight

            def _on_window_created(win):
                modern_window_ref[0] = win

            try:
                run_modern_app(
                    assistant=app._assistant,
                    title=f"Börü {args.version} — Yeni Nesil Yapay Zekâ",
                    on_voice_toggle=_toggle_voice,
                    on_open_spotlight=_open_spotlight,
                    on_window_created=_on_window_created,
                    on_closing=_on_window_closing,
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
