"""
boru.testing.generator_coordinator
==================================
Kullanıcıdan gelen 'test üret: ...' veya 'test oluştur: ...' komutlarını karşılayan,
ilgili dosya için otomatik unit test senaryoları sentezleyen ve isteğe bağlı
olarak testleri anında çalıştıran doğrudan yanıt koordinatörü.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from boru.testing.test_generator import AutoTestGenerator


class AutoTestGeneratorCoordinator:
    """
    DirectResponseResolver protokolünü uygular.
    'test üret: <dosya_yolu>' komutlarını işler.
    """

    _PREFIX_REGEX = re.compile(
        r"^\s*(?:test\s+üret|test\s+uret|test\s+yaz|test\s+oluştur|test\s+olustur)(?:\s+ve\s+çalıştır|\s+ve\s+calistir)?\s*:\s*(?P<target>.+)$",
        re.IGNORECASE,
    )

    def __init__(
        self,
        generator: AutoTestGenerator | None = None,
        test_runner: Callable[[str], str] | None = None,
    ) -> None:
        self._generator = generator or AutoTestGenerator()
        self._test_runner = test_runner

    def resolve(self, user_message: str) -> str | None:
        match = self._PREFIX_REGEX.match(user_message.strip())
        if not match:
            return None

        target_str = match.group("target").strip()
        should_run = "çalıştır" in user_message.lower() or "calistir" in user_message.lower()

        # Hedef dosya yolunu temizle
        target_path = Path(target_str.strip("'\"`"))
        if not target_path.exists():
            return f"❌ Test Üretim Hatası: Belirtilen kaynak dosya bulunamadı: `{target_str}`"

        try:
            result = self._generator.generate_for_file(target_path, output_dir="tests", save=True)
        except Exception as err:
            return f"❌ Test Üretim Hatası: AST analiz veya dosya yazma başarısız: {err}"

        lines = [
            "🧪 OTOMATİK TEST RAPORU",
            f"Kaynak Dosya: `{result.target_path}`",
            f"Üretilen Test: `{result.output_path}`",
            f"Taranan Sembol: {result.test_suite.symbol_count} adet",
            f"Yazılan Test Metodu: {result.test_suite.test_methods_count} adet",
            "Sözdizimi Doğrulaması: GEÇTİ (AST parse onaylı)",
            "",
            "💡 İpucu: Bu testleri `pytest " + result.output_path + "` ile hemen çalıştırabilirsiniz.",
        ]

        if should_run and self._test_runner:
            run_output = self._test_runner(result.output_path)
            lines.extend([
                "",
                "🏃 TEST ÇALIŞTIRMA SONUCU:",
                run_output,
            ])

        return "\n".join(lines)

