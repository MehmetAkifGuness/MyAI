from __future__ import annotations

import base64
import io
import logging
import os
import tempfile
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def capture_screen(save_path: Optional[str] = None) -> Tuple[bool, str]:
    """Mevcut ekranın görüntüsünü alır ve PNG olarak kaydeder."""
    try:
        from PIL import ImageGrab

        try:
            img = ImageGrab.grab(all_screens=True)
        except Exception:
            img = ImageGrab.grab()

        if not save_path:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                target_path = f.name
        else:
            target_path = save_path

        img.save(target_path, format="PNG")
        return True, target_path
    except Exception as e:
        logger.debug(f"Ekran görüntüsü alma hatası: {e}")
        return False, f"Ekran görüntüsü alınamadı: {e}"


def get_available_vision_model() -> Optional[str]:
    """Ollama üzerinde kurulu görsel (multimodal) model olup olmadığını denetler."""
    try:
        import ollama

        models_response = ollama.list()
        models = [m.model for m in models_response.models] if hasattr(models_response, "models") else []
        vision_candidates = ["llava", "qwen2-vl", "minicpm-v", "bakllava", "moondream", "llama3.2-vision"]

        for candidate in vision_candidates:
            for installed in models:
                if candidate in installed.lower():
                    return installed
    except Exception:
        pass
    return None


def analyze_screen(query: str = "Şu anda ekranda ne var, hata veya önemli bilgi var mı?") -> str:
    """
    Ekran görüntüsü alır ve görsel yapay zeka modeliyle inceler.
    Eğer yerel görme modeli yoksa ekranı kaydeder ve kullanıcıyı bilgilendirir.
    """
    ok, path_or_err = capture_screen()
    if not ok:
        return f"Ekran görüntüsü yakalanamadı: {path_or_err}"

    screenshot_path = path_or_err

    try:
        vision_model = get_available_vision_model()

        if vision_model:
            import ollama

            with open(screenshot_path, "rb") as f:
                img_bytes = f.read()

            response = ollama.chat(
                model=vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": f"{query}\nLütfen Türkçe, net ve kısa bir özet ver.",
                        "images": [img_bytes],
                    }
                ],
            )
            analysis = response.message.content.strip()
            return f"📸 Ekran İncelendi ({vision_model}):\n{analysis}"
        else:
            return (
                f"📸 Ekran görüntüsü alındı ({screenshot_path}). "
                "Görsel analiz için Ollama'da bir vision modeli (örneğin: 'ollama run llava' veya 'ollama run qwen2-vl:7b') "
                "çalıştırabilirsiniz."
            )
    except Exception as e:
        return f"Görsel analiz sırasında bir hata oluştu: {e}"
    finally:
        try:
            if os.path.exists(screenshot_path):
                os.remove(screenshot_path)
        except Exception:
            pass
