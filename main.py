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

            # Modern WebView uygulamasını başlat
            # Tkinter penceresini gizle, arka plan servislerini koru
            app.withdraw()

            def _toggle_voice():
                if getattr(app, "_continuous_voice", None):
                    if app._continuous_voice.is_active:
                        app._continuous_voice.stop()
                        return False
                    else:
                        app._continuous_voice.start()
                        return True
                return False

            def _open_spotlight():
                if getattr(app, "_jarvis_overlay", None):
                    app._jarvis_overlay.show()

            run_modern_app(
                assistant=app._assistant,
                title=f"Börü {args.version} — Yeni Nesil Yapay Zekâ",
                on_voice_toggle=_toggle_voice,
                on_open_spotlight=_open_spotlight,
            )
            return
        except Exception as e:
            logger.warning(f"Modern WebView başlatılamadı, klasik arayüze dönülüyor: {e}")
            app.deiconify()

    app.mainloop()


if __name__ == "__main__":
    main()
