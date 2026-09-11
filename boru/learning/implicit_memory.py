"""
Börü Sezgisel ve Örtük Hafıza Motoru (Implicit Memory Learner).
Kullanıcının açıkça 'bunu hatırla' demesine gerek kalmadan;
şehir, teknoloji yığını, uygulama tercihleri ve kişisel alışkanlıklarını
doğal sohbet akışından sezgisel olarak öğrenir ve kalıcı olarak depolar.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TURKISH_CITIES = {
    "adana", "adıyaman", "afyonkarahisar", "ağrı", "amasya", "ankara", "antalya", "artvin",
    "aydın", "balıkesir", "bilecik", "bingöl", "bitlis", "bolu", "burdur", "bursa", "çanakkale",
    "çankırı", "çorum", "denizli", "diyarbakır", "edirne", "elazığ", "erzincan", "erzurum",
    "eskişehir", "gaziantep", "antep", "giresun", "gümüşhane", "hakkari", "hatay", "ısparta",
    "mersin", "içel", "istanbul", "izmir", "kars", "kastamonu", "kayseri", "kırklareli",
    "kırşehir", "kocaeli", "izmit", "konya", "kütahya", "malatya", "manisa", "kahramanmaraş",
    "maraş", "mardin", "muğla", "muş", "nevşehir", "niğde", "ordu", "rize", "sakarya",
    "adapazarı", "samsun", "siirt", "sinop", "sivas", "tekirdağ", "tokat", "trabzon",
    "tunceli", "şanlıurfa", "urfa", "uşak", "van", "yozgat", "zonguldak", "aksaray",
    "bayburt", "karaman", "kırıkkale", "batman", "şırnak", "bartın", "ardahan", "Iğdır",
    "yalova", "karabük", "kilis", "osmaniye", "düzce"
}

CITY_CANONICAL = {
    "maraş": "Kahramanmaraş",
    "kahramanmaraş": "Kahramanmaraş",
    "antep": "Gaziantep",
    "gaziantep": "Gaziantep",
    "urfa": "Şanlıurfa",
    "şanlıurfa": "Şanlıurfa",
    "içel": "Mersin",
    "mersin": "Mersin",
    "izmit": "Kocaeli",
    "kocaeli": "Kocaeli",
    "adapazarı": "Sakarya",
    "sakarya": "Sakarya",
}

KNOWN_TECHS = {
    "python": "Python",
    "fastapi": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "react": "React",
    "vue": "Vue",
    "angular": "Angular",
    "svelte": "Svelte",
    "nextjs": "Next.js",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "mysql": "MySQL",
    "sqlite": "SQLite",
    "mongodb": "MongoDB",
    "redis": "Redis",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "huggingface": "HuggingFace",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "c#": "C#",
    "c++": "C++",
    "rust": "Rust",
    "golang": "Go",
    "go": "Go",
    "git": "Git",
    "linux": "Linux",
    "windows": "Windows",
}

APP_CATEGORIES = {
    "music": {
        "spotify": "Spotify",
        "youtube music": "YouTube Music",
        "yt music": "YouTube Music",
        "apple music": "Apple Music",
        "deezer": "Deezer",
    },
    "browser": {
        "chrome": "Chrome",
        "google chrome": "Chrome",
        "edge": "Edge",
        "msedge": "Edge",
        "firefox": "Firefox",
        "brave": "Brave",
        "opera": "Opera",
    },
    "editor": {
        "vscode": "VS Code",
        "vs code": "VS Code",
        "code": "VS Code",
        "pycharm": "PyCharm",
        "sublime": "Sublime Text",
        "cursor": "Cursor",
        "notepad": "Not Defteri",
        "not defteri": "Not Defteri",
    },
}


class ImplicitMemoryLearner:
    """
    Sohbet akışını dinleyerek kullanıcının bağlamını
    otonom ve sezgisel olarak öğrenen kalıcı bellek sınıfı.
    """

    def __init__(self, storage_path: Optional[Path | str] = None):
        if storage_path is None:
            base_dir = Path(__file__).resolve().parent.parent.parent
            self._storage_path = base_dir / "data" / "user_learned_profile.json"
        else:
            self._storage_path = Path(storage_path)

        self._lock = RLock()
        self._data: Dict[str, Any] = {
            "primary_city": None,
            "locations": {},
            "tech_stack": {},
            "app_preferences": {},
            "personal_facts": {},
            "habits": {},
            "last_updated": None,
        }
        self.load()

    def load(self) -> Dict[str, Any]:
        with self._lock:
            if self._storage_path.exists():
                try:
                    with open(self._storage_path, "r", encoding="utf-8") as f:
                        saved = json.load(f)
                        if isinstance(saved, dict):
                            self._data.update(saved)
                except Exception as e:
                    logger.debug(f"Implicit memory yükleme hatası: {e}")
            return self._data

    def save(self) -> None:
        with self._lock:
            try:
                self._storage_path.parent.mkdir(parents=True, exist_ok=True)
                self._data["last_updated"] = datetime.now().isoformat()
                temp_path = self._storage_path.with_suffix(".tmp")
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, ensure_ascii=False, indent=2)
                if os.path.exists(temp_path):
                    os.replace(temp_path, self._storage_path)
            except Exception as e:
                logger.debug(f"Implicit memory kaydetme hatası: {e}")

    def observe(self, user_message: str) -> None:
        """MessageObserver uyumluluğu için tek mesajlık dinleyici."""
        self.observe_turn(user_message, "")

    def observe_turn(self, user_message: str, assistant_message: str) -> None:
        """
        TurnObserver protokolü: Her kullanıcı-asistan diyaloğundan
        örtük çıkarımlarda bulunur.
        """
        text = user_message.strip()
        if not text:
            return

        changed = False
        with self._lock:
            if self._extract_locations(text):
                changed = True

            if self._extract_tech_stack(text):
                changed = True

            if self._extract_app_preferences(text):
                changed = True

            if self._extract_personal_facts(text):
                changed = True

            if changed:
                self.save()

    def _extract_locations(self, text: str) -> bool:
        changed = False
        lower_text = text.lower()
        now_iso = datetime.now().isoformat()

        live_patterns = [
            r"\b([a-zğüşıöç]+)(?:'da|'de|'ta|'te)?\s+(?:yaşıyorum|oturuyorum|ikamet\s+ediyorum|bulunuyorum|yerleşiğim)",
            r"\b([a-zğüşıöç]+)(?:'dayım|'deyim|'tayım|'teyim)\b",
            r"\b(?:şehrim|yaşadığım\s+yer|memleketim)\s+([a-zğüşıöç]+)\b",
            r"\bbizim\s+bura(?:sı)?\s+([a-zğüşıöç]+)\b",
        ]

        for pat in live_patterns:
            m = re.search(pat, lower_text)
            if m:
                cand = m.group(1).strip()
                if cand in TURKISH_CITIES:
                    canonical = CITY_CANONICAL.get(cand, cand.title())
                    loc_info = self._data["locations"].setdefault(canonical, {"count": 0, "last_seen": now_iso, "explicit": False})
                    loc_info["count"] += 5
                    loc_info["last_seen"] = now_iso
                    loc_info["explicit"] = True
                    self._data["primary_city"] = canonical
                    changed = True

        if any(w in lower_text for w in ("hava", "derece", "sıcaklık")):
            for city_token in TURKISH_CITIES:
                if re.search(rf"\b{re.escape(city_token)}\b", lower_text):
                    canonical = CITY_CANONICAL.get(city_token, city_token.title())
                    loc_info = self._data["locations"].setdefault(canonical, {"count": 0, "last_seen": now_iso, "explicit": False})
                    loc_info["count"] += 1
                    loc_info["last_seen"] = now_iso
                    if not self._data.get("primary_city"):
                        self._data["primary_city"] = canonical
                    else:
                        current_primary = self._data["primary_city"]
                        curr_count = self._data["locations"].get(current_primary, {}).get("count", 0)
                        if loc_info["count"] > curr_count + 2 and not self._data["locations"].get(current_primary, {}).get("explicit", False):
                            self._data["primary_city"] = canonical
                    changed = True

        return changed

    def _extract_tech_stack(self, text: str) -> bool:
        changed = False
        lower_text = text.lower()
        now_iso = datetime.now().isoformat()

        tech_context_words = ("yazıyorum", "kodluyorum", "kullanıyorum", "proje", "uygulama", "api", "backend", "frontend", "model", "veri", "geliştiriyorum")
        has_context = any(w in lower_text for w in tech_context_words)

        for raw_token, display_name in KNOWN_TECHS.items():
            if re.search(rf"\b{re.escape(raw_token)}\b", lower_text):
                tech_info = self._data["tech_stack"].setdefault(display_name, {"count": 0, "last_seen": now_iso})
                weight = 2 if has_context else 1
                tech_info["count"] += weight
                tech_info["last_seen"] = now_iso
                changed = True

        return changed

    def _extract_app_preferences(self, text: str) -> bool:
        changed = False
        lower_text = text.lower()

        for category, apps in APP_CATEGORIES.items():
            for app_token, app_name in apps.items():
                if re.search(rf"\b{re.escape(app_token)}\b", lower_text):
                    self._data["app_preferences"][category] = app_token
                    changed = True
                    break

        return changed

    def _extract_personal_facts(self, text: str) -> bool:
        changed = False
        lower_text = text.lower()

        professions = [
            ("yazılımcıyım", "Yazılımcı / Geliştirici"),
            ("mühendisim", "Mühendis"),
            ("öğrenciyim", "Öğrenci"),
            ("doktorum", "Doktor"),
            ("avukatım", "Avukat"),
            ("tasarımcıyım", "Tasarımcı"),
            ("öğretmenim", "Öğretmen"),
            ("akademisyenim", "Akademisyen"),
        ]
        for trigger, label in professions:
            if re.search(rf"\b{re.escape(trigger)}\b", lower_text):
                self._data["personal_facts"]["profession"] = label
                changed = True

        return changed

    def get_city(self) -> Optional[str]:
        with self._lock:
            if self._data.get("primary_city"):
                return self._data["primary_city"]
            if self._data.get("locations"):
                sorted_locs = sorted(self._data["locations"].items(), key=lambda x: x[1].get("count", 0), reverse=True)
                if sorted_locs:
                    return sorted_locs[0][0]
            return None

    def get_app_preference(self, category: str) -> Optional[str]:
        with self._lock:
            return self._data.get("app_preferences", {}).get(category)

    def get_tech_stack(self, top_k: int = 5) -> List[str]:
        with self._lock:
            sorted_techs = sorted(self._data.get("tech_stack", {}).items(), key=lambda x: x[1].get("count", 0), reverse=True)
            return [tech for tech, _ in sorted_techs[:top_k]]

    def build_context(self, user_message: str = "") -> str:
        """AssistantContextProvider uyumlu bağlam üreticisi."""
        with self._lock:
            items = []
            city = self.get_city()
            if city:
                items.append(f"- Konum / İlgilendiği Şehir: {city}")

            techs = self.get_tech_stack(top_k=5)
            if techs:
                items.append(f"- Aktif İlgilendiği Teknolojiler: {', '.join(techs)}")

            prefs = self._data.get("app_preferences", {})
            pref_strs = []
            if "music" in prefs:
                pref_strs.append(f"Müzik: {prefs['music'].title()}")
            if "browser" in prefs:
                pref_strs.append(f"Tarayıcı: {prefs['browser'].title()}")
            if "editor" in prefs:
                pref_strs.append(f"Editör: {prefs['editor'].title()}")
            if pref_strs:
                items.append(f"- Uygulama Tercihleri: {', '.join(pref_strs)}")

            facts = self._data.get("personal_facts", {})
            if "profession" in facts:
                items.append(f"- Meslek / Rol: {facts['profession']}")

            if not items:
                return ""

            lines = "\n".join(items)
            return (
                f"[Öğrenilmiş Kullanıcı Tercihleri ve Alışkanlıkları (Sezgisel Hafıza)]:\n{lines}\n"
                "(Bu bilgiler kullanıcının doğal sohbetinden sezgisel olarak öğrenilmiştir; yanıtları kişiselleştirmek için gözet.)"
            )
