"""
Börü — Sessiz Arka Plan Servisi (Headless Daemon)
=================================================
Bu script pythonw.exe ile çalıştırıldığında hiçbir konsol penceresi veya
büyük arayüz açmaz; arka planda sessizce bekler.

Kullanıcı:
  - "Börü" veya "Hey Börü" dediğinde, VEYA
  - 'Ctrl + Shift + B' / 'Ctrl + Shift + J' kısayollarına bastığında

Börü hızlı komut çubuğu ekranın ortasında belirir, doğal sesle cevap verir
ve işlem bittiğinde tekrar sessiz arka plan moduna döner.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

# Proje dizinini başa al
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import main_v170


def main():
    app = main_v170.build_application()
    # Ana pencereyi gizle (tamamen arka planda çalış)
    app.withdraw()
    app.mainloop()


if __name__ == "__main__":
    main()
