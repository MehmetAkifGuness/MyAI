from __future__ import annotations

import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def get_clipboard_text() -> Optional[str]:
    """
    Windows panosundaki (Clipboard) mevcut metni hızlı ve güvenli şekilde okur.
    Önce Tkinter, başarısız olursa Win32 ctypes API dener.
    """
    # 1. Tkinter yöntemi (Hafif ve güvenli)
    try:
        import tkinter as tk
        r = tk.Tk()
        r.withdraw()
        try:
            text = r.clipboard_get()
            if text and text.strip():
                return text.strip()
        finally:
            r.destroy()
    except Exception:
        pass

    # 2. Win32 ctypes alternatifi
    try:
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        if user32.OpenClipboard(0):
            try:
                # CF_UNICODETEXT = 13
                h = user32.GetClipboardData(13)
                if h:
                    p = kernel32.GlobalLock(h)
                    val = ctypes.c_wchar_p(p).value
                    kernel32.GlobalUnlock(h)
                    if val and val.strip():
                        return val.strip()
            finally:
                user32.CloseClipboard()
    except Exception as e:
        logger.debug(f"Pano okuma hatası: {e}")

    return None


def get_default_llm_model() -> str:
    """Ollama üzerinde kurulu aktif modeli bulur."""
    try:
        import ollama
        models_resp = ollama.list()
        models = [m.model for m in models_resp.models] if hasattr(models_resp, "models") else []
        if models:
            for pref in ("qwen2.5:7b", "llama3.2", "mistral", "gemma2"):
                for m in models:
                    if pref in m:
                        return m
            return models[0]
    except Exception:
        pass
    return "qwen2.5:7b"


def resolve_clipboard_command(user_text: str) -> Optional[str]:
    """
    Pano ile ilgili komutları çözümler:
    - "panoda ne var", "panoyu oku"
    - "panoyu çevir", "panodaki metni türkçeye çevir"
    - "panodaki metni özetle", "panoyu özetle"
    - "panodaki kodu açıkla", "panodaki hatayı çöz"
    """
    cleaned = user_text.lower().strip().strip(".!?,")

    if not ("pano" in cleaned or "kopyalanan" in cleaned or "clipboard" in cleaned):
        return None

    clip_text = get_clipboard_text()

    # 1. Panoyu Okuma / İçeriğini Gösterme
    if any(k in cleaned for k in ("panoda ne var", "panoyu oku", "panodaki metin", "panoyu göster", "panoda ne yazıyor")):
        if not clip_text:
            return "Panoda şu anda herhangi bir metin bulunmuyor."
        preview = clip_text if len(clip_text) <= 300 else clip_text[:300] + "..."
        return f"Panodaki metin:\n\n{preview}"

    # Panoda metin yoksa devamındaki işlemler yapılamaz
    if not clip_text:
        return "Panonuz şu anda boş. Lütfen önce bir metin veya kod kopyalayın."

    # 2. Panoyu Çevirme
    if any(k in cleaned for k in ("çevir", "türkçeye çevir", "ingilizceye çevir", "tercüme")):
        target_lang = "Türkçe"
        if "ingilizce" in cleaned:
            target_lang = "İngilizce"
        prompt = f"Lütfen aşağıdaki panodan kopyalanmış metni akıcı ve doğal bir dille {target_lang}'ye çevir:\n\n{clip_text}"
        return _query_ollama(prompt)

    # 3. Panoyu Özetleme
    if any(k in cleaned for k in ("özetle", "özet çıkar", "kısaca anlat")):
        prompt = f"Lütfen aşağıdaki panodan kopyalanmış metni ana hatlarıyla, kısa ve anlaşılır şekilde özetle:\n\n{clip_text}"
        return _query_ollama(prompt)

    # 4. Kod Açıklama / Hata Analizi
    if any(k in cleaned for k in ("kod", "hata", "açıkla", "düzelt", "analiz")):
        prompt = f"Lütfen panodaki aşağıdaki kod veya hata çıktısını incele, ne yaptığını ve varsa hatanın çözümünü net bir şekilde açıkla:\n\n{clip_text}"
        return _query_ollama(prompt)

    return None


def _query_ollama(prompt: str) -> str:
    try:
        import ollama
        model = get_default_llm_model()
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        ans = response.get("message", {}).get("content", "").strip()
        if ans:
            return ans
        return "Model yanıt üretemedi."
    except Exception as e:
        logger.debug(f"Ollama pano sorgu hatası: {e}")
        return f"Pano işlenirken model çağrısı başarısız oldu: {e}"

