"""
boru.context.reference_resolver
===============================
Konuşma geçmişinde geçen dosya adlarını, fonksiyonları, sınıfları
ve kod öğelerini tespit ederek çok turlu konuşmalarda zamir veya
belirteç ('o dosya', 'az önce bahsettiğin dosya') referanslarını çözer.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from boru.models import ChatMessage


class ConversationReferenceResolver:
    """Çok turlu konuşma geçmişinden bağlamsal referansları ve odak öğelerini çıkarır."""

    # Dosya yolları veya dosya adları (.py, .json, .md, .txt vb.)
    _FILE_PATTERN = re.compile(
        r"\b(?:[a-zA-Z0-9_\-\./\\]+\.(?:py|json|md|txt|sql|html|css|js|yaml|yml|toml))\b",
        re.IGNORECASE,
    )

    # Fonksiyon ve sınıf tanımları veya semboller (def foo, class Bar, vb.)
    _SYMBOL_PATTERN = re.compile(
        r"\b(?:def|class)\s+([a-zA-Z_][a-zA-Z0-9_]*)\b"
    )

    def extract_recent_references(
        self,
        history: Sequence[ChatMessage],
        max_items: int = 5,
    ) -> dict[str, list[str]]:
        """
        Geçmiş mesajlardan en son bahsedilen dosya adlarını ve sembolleri döndürür.
        """
        found_files: list[str] = []
        found_symbols: list[str] = []

        # En son mesajlardan geriye doğru tara
        for message in reversed(history):
            content = message.content or ""

            # Dosyaları bul
            for match in self._FILE_PATTERN.finditer(content):
                filename = match.group(0)
                if filename not in found_files:
                    found_files.append(filename)

            # Sembolleri bul
            for match in self._SYMBOL_PATTERN.finditer(content):
                symbol = match.group(1)
                if symbol not in found_symbols:
                    found_symbols.append(symbol)

        return {
            "files": found_files[:max_items],
            "symbols": found_symbols[:max_items],
        }

    def build_reference_context(
        self,
        history: Sequence[ChatMessage],
    ) -> str:
        """
        Model için konuşma geçmişinde geçen odak nesnelerini özetleyen sistem bağlamı üretir.
        """
        if not history:
            return ""

        refs = self.extract_recent_references(history)
        parts = []

        if refs["files"]:
            files_str = ", ".join(f"`{f}`" for f in refs["files"])
            parts.append(f"Son konuşulan dosyalar: {files_str}")

        if refs["symbols"]:
            symbols_str = ", ".join(f"`{s}`" for s in refs["symbols"])
            parts.append(f"Son konuşulan semboller/fonksiyonlar: {symbols_str}")

        if not parts:
            return ""

        return (
            "[Konuşma Odak Bağlamı]\n"
            + "\n".join(parts)
            + "\nKullanıcı 'bu dosya', 'o kod', 'az önce bahsettiğimiz' gibi atıfta bulunursa bu odak öğelerini temel al."
        )
