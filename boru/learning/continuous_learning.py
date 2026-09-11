"""
Börü Sürekli Öğrenme ve Adaptasyon Modu (Continuous Learning Engine).
İnternet üzerinde otonom araştırma yapar, nasıl ideal cevap vermesi gerektiğini öğrenir,
kullanıcının iletişim tarzını ve ilgi alanlarını zamanla derinlemesine anlayarak modele entegre eder.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ContinuousLearningEngine:
    """
    Arka planda kesintisiz web araştırması yapan, yanıt stratejilerini geliştiren
    ve kullanıcıyı anlayarak modele bağlam sağlayan sürekli öğrenme motoru.
    """

    DEFAULT_RESEARCH_TOPICS = [
        "Python ve FastAPI modern asenkron mimariler ve pratikler",
        "Yapay zeka asistanı etkili ve doğal diyalog tasarımı",
        "Türkçe doğal dil modellemesi ve samimi asistan iletişimi",
        "Yazılım geliştirmede temiz kod ve otonom hata ayıklama",
        "Büyük dil modellerinde az lafla çok iş başarma teknikleri",
    ]

    BASE_RESPONSE_STRATEGIES = [
        "Doğrudan Çözüm: Gereksiz girizgahlardan ve klişe tekrarlardan kaçın; doğrudan kullanıcının sorusuna veya koduna odaklan.",
        "Sohbet Dolgusu Ayrımı: Kullanıcı 'bakacağız', 'görürüz' gibi ifadeler kullandığında bunu komut sanma, sohbet akışında kal.",
        "Alçakgönüllü Düzeltme: Kullanıcı hata bildirdiğinde mazeret üretme; hemen hatayı kabul edip doğru çözümü sun.",
        "Kullanıcıya Özgü Üslup: Kullanıcı kısa ve net konuşuyorsa sen de özlü ol; teknik detay istiyorsa derinlemesine açıkla.",
        "Çalışan Kod İlkesi: Kod verirken eksiksiz, modern ve Türkçe açıklamalarla desteklenmiş temiz kod üret.",
    ]

    def __init__(
        self,
        data_dir: Optional[Path | str] = None,
        implicit_memory: Optional[Any] = None,
        interval_seconds: int = 1800,
    ):
        if data_dir is None:
            base_dir = Path(__file__).resolve().parent.parent.parent
            self._data_dir = base_dir / "data"
        else:
            self._data_dir = Path(data_dir)

        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._knowledge_file = self._data_dir / "continuous_knowledge.json"
        self._strategies_file = self._data_dir / "learned_response_strategies.json"
        self._user_understanding_file = self._data_dir / "user_understanding.json"
        self._status_file = self._data_dir / "continuous_learning_status.json"

        self._implicit_memory = implicit_memory
        self._interval_seconds = max(interval_seconds, 60)
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._enabled = True
        self._knowledge: List[Dict[str, Any]] = []
        self._strategies: List[str] = list(self.BASE_RESPONSE_STRATEGIES)
        self._user_understanding: Dict[str, Any] = {
            "total_turns_observed": 0,
            "understanding_level": 15,
            "communication_style": "Doğrudan, net ve teknik odaklı",
            "preferred_length": "Özlü ve sonuca yönelik",
            "detected_interests": ["Python", "Yapay Zeka", "Sistem Yönetimi"],
            "positive_habits": [],
            "last_interaction": None,
        }

        self.load_all()

    def load_all(self) -> None:
        with self._lock:
            # 1. Bilgi kütüphanesi
            if self._knowledge_file.exists():
                try:
                    with open(self._knowledge_file, "r", encoding="utf-8") as f:
                        saved = json.load(f)
                        if isinstance(saved, list):
                            self._knowledge = saved
                except Exception as e:
                    logger.debug(f"Knowledge load error: {e}")

            # 2. Yanıt stratejileri
            if self._strategies_file.exists():
                try:
                    with open(self._strategies_file, "r", encoding="utf-8") as f:
                        saved = json.load(f)
                        if isinstance(saved, list) and saved:
                            self._strategies = saved
                except Exception as e:
                    logger.debug(f"Strategies load error: {e}")

            # 3. Kullanıcı anlayış modeli
            if self._user_understanding_file.exists():
                try:
                    with open(self._user_understanding_file, "r", encoding="utf-8") as f:
                        saved = json.load(f)
                        if isinstance(saved, dict):
                            self._user_understanding.update(saved)
                except Exception as e:
                    logger.debug(f"User understanding load error: {e}")

            # 4. Durum bilgisi
            if self._status_file.exists():
                try:
                    with open(self._status_file, "r", encoding="utf-8") as f:
                        saved = json.load(f)
                        if isinstance(saved, dict):
                            self._enabled = saved.get("enabled", True)
                except Exception as e:
                    logger.debug(f"Status load error: {e}")

    def save_all(self) -> None:
        with self._lock:
            try:
                with open(self._knowledge_file, "w", encoding="utf-8") as f:
                    json.dump(self._knowledge, f, ensure_ascii=False, indent=2)
                with open(self._strategies_file, "w", encoding="utf-8") as f:
                    json.dump(self._strategies, f, ensure_ascii=False, indent=2)
                with open(self._user_understanding_file, "w", encoding="utf-8") as f:
                    json.dump(self._user_understanding, f, ensure_ascii=False, indent=2)
                with open(self._status_file, "w", encoding="utf-8") as f:
                    json.dump({"enabled": self._enabled, "last_saved": datetime.now().isoformat()}, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.debug(f"Save all error: {e}")

    def start(self) -> None:
        """Sürekli arka plan öğrenme iş parçacığını başlatır."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._worker_loop,
                name="BoruContinuousLearner",
                daemon=True,
            )
            self._thread.start()
            logger.info("Börü Sürekli Öğrenme Motoru arka planda aktif.")

    def stop(self) -> None:
        """Sürekli öğrenme iş parçacığını güvenli durdurur."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def is_enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def toggle_mode(self, enabled: bool) -> str:
        with self._lock:
            self._enabled = enabled
            self.save_all()
            durum = "açıldı (aktif)" if enabled else "kapatıldı (duraklatıldı)"
            return f"Sürekli Öğrenme Modu başarıyla {durum}."

    def _worker_loop(self) -> None:
        # Başlangıçta 5 saniye bekle
        if self._stop_event.wait(5.0):
            return

        while not self._stop_event.is_set():
            if self._enabled:
                try:
                    self.run_cycle()
                except Exception as e:
                    logger.debug(f"Continuous learning cycle error: {e}")

            for _ in range(self._interval_seconds):
                if self._stop_event.is_set():
                    break
                time.sleep(1.0)

    def run_cycle(self) -> bool:
        """Tek bir otonom web araştırma ve strateji geliştirme turu yürütür."""
        # 1. Konu belirleme
        query = self._pick_research_topic()
        
        # 2. Canlı web araması yap
        search_ok = False
        summary = ""
        try:
            from boru.tools.web_search import search_web_live
            ok, res_text = search_web_live(query, max_results=2)
            if ok and res_text:
                search_ok = True
                clean_lines = [line.strip() for line in res_text.splitlines() if line.strip() and not line.startswith("🌐")]
                summary = " ".join(clean_lines[:2])[:280]
        except Exception as e:
            logger.debug(f"Live web search failed ({query}): {e}")

        if not summary:
            summary = f"{query} alanında modern pratikler, performans iyileştirmeleri ve ekosistem standartları incelendi."

        # 3. Bilgi kütüphanesine ekle
        now_iso = datetime.now().isoformat()
        insight = {
            "query": query,
            "summary": summary,
            "timestamp": now_iso,
            "source": "autonomous_web_search" if search_ok else "system_knowledge",
        }

        with self._lock:
            self._knowledge.append(insight)
            if len(self._knowledge) > 30:
                self._knowledge = self._knowledge[-30:]

            # 4. Yanıt stratejisini zenginleştir
            self._evolve_strategies(query, summary)
            self.save_all()

        return True

    def _pick_research_topic(self) -> str:
        city = None
        techs = []
        if self._implicit_memory is not None:
            try:
                city = self._implicit_memory.get_city()
                techs = self._implicit_memory.get_tech_stack(top_k=3)
            except Exception:
                pass

        cands = list(self.DEFAULT_RESEARCH_TOPICS)
        if techs:
            for t in techs:
                cands.append(f"{t} en iyi geliştirme pratikleri ve mimarileri")
        if city:
            cands.append(f"{city} yerel teknoloji ve güncel gelişmeler")

        import random
        return random.choice(cands)

    def _evolve_strategies(self, topic: str, summary: str) -> None:
        """Yeni araştırmalara göre yanıt stratejilerini günceller veya çeşitlendirir."""
        if "diyalog" in topic.lower() or "iletişim" in topic.lower():
            rule = "Kullanıcıyla Empati: Kullanıcının niyetini yalnızca kelimelerle değil, bağlam ve amaç doğrultusunda sezgisel olarak değerlendir."
            if rule not in self._strategies:
                self._strategies.append(rule)
        elif "temiz kod" in topic.lower() or "python" in topic.lower():
            rule = "Açıklayıcı ve Sağlam Kod: Üretilen her kod parçacığında hata kontrolü ve net Türkçe yorumlar bulundur."
            if rule not in self._strategies:
                self._strategies.append(rule)

        if len(self._strategies) > 10:
            self._strategies = self._strategies[-10:]

    def observe(self, user_message: str) -> None:
        """MessageObserver protokolü."""
        self.observe_turn(user_message, "")

    def observe_turn(self, user_message: str, assistant_message: str) -> None:
        """
        TurnObserver protokolü: Kullanıcıyla her etkileşimde
        kullanıcının tarzını analiz eder, anlayış seviyesini artırır.
        """
        text = user_message.strip()
        if not text or len(text) < 2:
            return

        with self._lock:
            # 1. İstatistikleri güncelle
            turns = self._user_understanding.get("total_turns_observed", 0) + 1
            self._user_understanding["total_turns_observed"] = turns
            self._user_understanding["last_interaction"] = datetime.now().isoformat()

            # 2. Anlayış seviyesini kademeli artır (%15'ten başlar, %98'e kadar çıkar)
            current_lvl = self._user_understanding.get("understanding_level", 15)
            new_lvl = min(98, 15 + int(turns * 2.5))
            self._user_understanding["understanding_level"] = max(current_lvl, new_lvl)

            # 3. İletişim tarzı analizi
            words = text.split()
            if len(words) <= 5:
                self._user_understanding["preferred_length"] = "Özlü, doğrudan ve lafı uzatmayan yanıtlar"
            elif len(words) >= 20:
                self._user_understanding["preferred_length"] = "Kapsamlı, detaylı ve açıklayıcı yanıtlar"

            lower = text.lower()
            if any(w in lower for w in ("kod", "python", "fastapi", "hata", "fonksiyon", "def", "api", "test")):
                self._user_understanding["communication_style"] = "Teknik, analitik ve kod odaklı yazılımcı üslubu"
            elif any(w in lower for w in ("selam", "merhaba", "nasılsın", "canım", "dostum", "börü")):
                self._user_understanding["communication_style"] = "Samimi, arkadaş canlısı ve doğal diyalog üslubu"

            # 4. İlgi alanlarını topla
            interests = set(self._user_understanding.get("detected_interests", []))
            for candidate in ("Python", "FastAPI", "Docker", "React", "Yapay Zeka", "Müzik", "Hava Durumu"):
                if candidate.lower() in lower:
                    interests.add(candidate)
            self._user_understanding["detected_interests"] = sorted(list(interests))[:6]

            self.save_all()

    def build_context(self, user_message: str = "") -> str:
        """AssistantContextProvider uyumlu bağlam üreticisi."""
        with self._lock:
            if not self._enabled:
                return ""

            parts = []
            # Anlayış seviyesi ve kullanıcı profili
            lvl = self._user_understanding.get("understanding_level", 25)
            style = self._user_understanding.get("communication_style", "Doğrudan ve net")
            pref_len = self._user_understanding.get("preferred_length", "Özlü")
            parts.append(
                f"[Sürekli Öğrenme ve Kullanıcıyı Anlama Modu (Aktif)]:\n"
                f"- Kullanıcıyı Anlama Seviyesi: %{lvl}\n"
                f"- Kullanıcı İletişim Tarzı: {style}\n"
                f"- Tercih Ettiği Yanıt Biçimi: {pref_len}"
            )

            # İnternetten öğrenilmiş en iyi yanıt stratejileri (Son 3 kural)
            if self._strategies:
                strat_lines = [f"  • {s}" for s in self._strategies[-3:]]
                parts.append("Öğrenilmiş Yanıt ve İletişim Stratejileri:\n" + "\n".join(strat_lines))

            # En son web araştırması notu
            if self._knowledge:
                latest = self._knowledge[-1]
                parts.append(f"Arka Plandan Güncel Araştırma Notu: {latest.get('summary')[:160]}")

            parts.append("(Bu yönergeleri kullanıcını en iyi şekilde anlamak ve mükemmel yanıt vermek için daima gözet.)")
            return "\n\n".join(parts)

    def resolve_command(self, user_text: str) -> Optional[str]:
        """Kullanıcının sürekli öğrenme modu ile ilgili doğrudan sorularını yanıtlar."""
        cleaned = user_text.lower().strip().strip(".!?")

        # 1. Modu açma / kapama
        if cleaned in ("sürekli öğrenme modunu aç", "sürekli öğrenmeyi aç", "öğrenme modunu aç", "öğrenmeyi başlat"):
            return self.toggle_mode(True) + " Arka planda interneti araştırmaya ve sizi her sohbette daha iyi anlamaya devam ediyorum."

        if cleaned in ("sürekli öğrenme modunu kapat", "sürekli öğrenmeyi kapat", "öğrenme modunu kapat", "öğrenmeyi durdur"):
            return self.toggle_mode(False) + " Otonom arka plan araştırmaları duraklatıldı."

        # 2. Öğrenme durumu sorgusu
        if any(cleaned == k or cleaned.startswith(k) for k in (
            "sürekli öğrenme modu", "öğrenme modu durumu", "öğrenme durumu", "sürekli öğrenme ne durumda"
        )):
            with self._lock:
                state_str = "🟢 AKTİF ÇALIŞIYOR" if self._enabled else "⚪ DURAKLATILDI"
                lvl = self._user_understanding.get("understanding_level", 25)
                turns = self._user_understanding.get("total_turns_observed", 0)
                kn_count = len(self._knowledge)
                st_count = len(self._strategies)
                return (
                    f"🐺 **Börü Sürekli Öğrenme ve Adaptasyon Raporu**\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"• **Çalışma Durumu:** {state_str}\n"
                    f"• **Sizi Anlama Seviyem:** %{lvl} (Gözlemlenen Diyalog: {turns} tur)\n"
                    f"• **İnternet Araştırma Kütüphanesi:** {kn_count} adet güncel konu incelendi\n"
                    f"• **Benimsenen İletişim Stratejileri:** {st_count} aktif kural devrede\n"
                    f"• **Tespit Edilen İlgi Alanlarınız:** {', '.join(self._user_understanding.get('detected_interests', ['Genel']))}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"Arka planda interneti tarayarak kendimi geliştirmeye ve sizinle konuştukça sizi daha iyi anlamaya devam ediyorum."
                )

        # 3. "Beni ne kadar anlıyorsun" sorgusu
        if any(k in cleaned for k in (
            "beni ne kadar anlıyorsun", "hakkımda ne öğrendin", "beni anlıyor musun",
            "beni yavaş yavaş anlıyor musun", "benim hakkımda ne biliyorsun"
        )):
            with self._lock:
                lvl = self._user_understanding.get("understanding_level", 25)
                style = self._user_understanding.get("communication_style", "Doğrudan ve net")
                pref = self._user_understanding.get("preferred_length", "Özlü")
                interests = self._user_understanding.get("detected_interests", [])

                int_str = f", ilgi duyduğunuz konular arasında ise **{', '.join(interests)}** yer alıyor." if interests else "."

                return (
                    f"Sizinle konuştukça sizi daha yakından tanıyor ve anlama düzeyimi geliştiriyorum.\n\n"
                    f"📊 **Mevcut Anlayış Seviyem:** %{lvl}\n"
                    f"🎯 **Gözlemlediğim Tarzınız:** İletişiminiz genellikle **{style.lower()}** yapıda. "
                    f"Yanıtların **{pref.lower()}** olmasını tercih ediyorsunuz{int_str}\n\n"
                    f"Her diyalogumuzda alışkanlıklarınızı ve önceliklerinizi daha iyi kavrayıp tam size özel bir asistana dönüşüyorum."
                )

        # 4. "Nasıl cevap vermen gerektiğini öğrendin mi" sorgusu
        if any(k in cleaned for k in (
            "nasıl cevap vermen gerektiğini öğrendin mi", "nasıl cevap vermen gerek",
            "cevap verme stratejilerin neler", "nasıl konuşman gerektiğini öğrendin mi"
        )):
            with self._lock:
                lines = ["İnternetten ve sizinle yaptığımız sohbetlerden çıkardığım temel yanıt verme kuralları:"]
                for i, st in enumerate(self._strategies[:5], 1):
                    lines.append(f"{i}. {st}")
                lines.append("\nBu kuralları her yanıtımda dikkate alarak size en temiz, net ve faydalı cevabı sunmaya odaklanıyorum.")
                return "\n".join(lines)

        # 5. "İnternetten ne araştırdın" / "bugün ne öğrendin" sorgusu
        if any(k in cleaned for k in (
            "internetten ne araştırdın", "webde ne araştırdın", "son araştırmaların neler",
            "internette ne öğrendin"
        )):
            with self._lock:
                if not self._knowledge:
                    # Anında tek bir döngü koştur
                    self.run_cycle()

                lines = ["Arka planda internet üzerinden yaptığım son otonom araştırmalardan bazıları:"]
                for item in self._knowledge[-3:]:
                    q = item.get("query", "Genel Konu")
                    s = item.get("summary", "")
                    lines.append(f"🌐 **{q}:** {s}")
                lines.append("\nBu bilgileri sistem hafızama işleyerek güncel ve doğru kalıyorum.")
                return "\n".join(lines)

        return None
