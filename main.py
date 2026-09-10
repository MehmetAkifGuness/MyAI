import argparse
from boru.release import build_release, _RELEASES


def main():
    parser = argparse.ArgumentParser(description="Börü - Yerel Yapay Zekâ ve Otonom Kodlama Asistanı")
    parser.add_argument(
        "--version",
        default="V13.0",
        choices=_RELEASES,
        help="Başlatılacak sürüm dönüm noktası (varsayılan: V13.0)",
    )
    args = parser.parse_args()
    app = build_release(version=args.version)
    app.mainloop()


if __name__ == "__main__":
    main()
