from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

import customtkinter as ctk

logger = logging.getLogger(__name__)


class JarvisOverlayWindow(ctk.CTkToplevel):
    """
    Ekranın üst-orta kısmında anında beliren, 2026 Apple Spotlight / Raycast / Siri
    kalitesinde ultra-modern, yarı saydam obsidian cam kapsül (Dynamic Command Island).
    """

    def __init__(
        self,
        master=None,
        on_submit_command: Optional[Callable[[str], str]] = None,
        on_voice_requested: Optional[Callable[[], None]] = None,
        on_open_main_ui: Optional[Callable[[], None]] = None,
    ):
        super().__init__(master)

        self._on_submit = on_submit_command
        self._on_voice = on_voice_requested
        self._on_open_main = on_open_main_ui

        self.title("🐺 Börü Hızlı Komut")
        self.attributes("-topmost", True)
        self.overrideredirect(True)  # Çerçevesiz yüzen Spotlight kapsülü
        self.configure(fg_color="#07090E")

        self._is_expanded = False
        self._is_busy = False
        self._last_result = ""

        self._setup_layout()
        self._position_window()
        self._bind_keys()

        # İlk başta gizli başla
        self.withdraw()

    def _setup_layout(self) -> None:
        # Ana Dış Kapsül (Raycast Obsidian Glass Container)
        self.container = ctk.CTkFrame(
            self,
            fg_color="#0B0F19",
            border_color="#38BDF8",
            border_width=1.8,
            corner_radius=22,
        )
        self.container.pack(fill="both", expand=True, padx=2, pady=2)

        # ── 1. Hero Arama Çubuğu (Hero Search Row) ───────────────────
        search_row = ctk.CTkFrame(self.container, fg_color="transparent")
        search_row.pack(fill="x", padx=14, pady=(12, 6))

        # Sol: Parlayan Wolf İkon Rozeti
        wolf_badge = ctk.CTkLabel(
            search_row,
            text="🐺",
            font=("Segoe UI Emoji", 20),
            width=36,
            height=36,
        )
        wolf_badge.pack(side="left", padx=(0, 8))

        # Arama Giriş Kutusu (Geniş, temiz ve modern)
        self.entry = ctk.CTkEntry(
            search_row,
            placeholder_text="Börü'ye sor veya bir komut yaz... (Örn: 'brifing ver', 'masaüstümü düzenle')",
            font=("Segoe UI", 13),
            fg_color="#111827",
            border_color="#1E293B",
            border_width=1,
            text_color="#F8FAFC",
            placeholder_text_color="#64748B",
            corner_radius=14,
            height=42,
        )
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        # Mikrofon Butonu (Dairesel Cyan Parlama)
        self.mic_btn = ctk.CTkButton(
            search_row,
            text="🎙️",
            width=42,
            height=42,
            font=("Segoe UI Emoji", 15),
            fg_color="#0284C7",
            hover_color="#0369A1",
            corner_radius=14,
            command=self._handle_mic_click,
        )
        self.mic_btn.pack(side="left", padx=(0, 6))

        # Çalıştır / Gönder Butonu (İndigo Pill)
        self.send_btn = ctk.CTkButton(
            search_row,
            text="Çalıştır ↵",
            width=88,
            height=42,
            font=("Segoe UI", 12, "bold"),
            fg_color="#6366F1",
            hover_color="#4F46E5",
            corner_radius=14,
            command=self._handle_submit,
        )
        self.send_btn.pack(side="left")

        # ── 2. Hızlı Öneri Hapları (Quick Suggestion Chips) ───────────
        self.chips_row = ctk.CTkFrame(self.container, fg_color="transparent")
        self.chips_row.pack(fill="x", padx=14, pady=(2, 8))

        suggestions = [
            ("🌅 Günün Brifingi", "bana brifing ver"),
            ("📂 Masaüstünü Toparla", "masaüstümü düzenle"),
            ("🧠 Ansiklopedi", "hakkında bilgi ver"),
            ("🎙️ Sesli Not Ekle", "notlarıma ekle: "),
            ("🔋 Sistem Durumu", "sistem durumunu raporla"),
        ]

        for label, cmd in suggestions:
            btn = ctk.CTkButton(
                self.chips_row,
                text=label,
                font=("Segoe UI", 11),
                height=24,
                fg_color="#131B2E",
                hover_color="#1E293B",
                border_color="#1E293B",
                border_width=1,
                corner_radius=10,
                text_color="#94A3B8",
                command=lambda c=cmd: self._apply_suggestion(c),
            )
            btn.pack(side="left", padx=(0, 6))

        # ── 3. Yanıt & Çıktı Kartı (Sonuç Geldiğinde Genişler) ────────
        self.result_frame = ctk.CTkFrame(
            self.container,
            fg_color="#090E17",
            corner_radius=14,
            border_color="#1E293B",
            border_width=1,
        )

        result_header = ctk.CTkFrame(self.result_frame, fg_color="transparent")
        result_header.pack(fill="x", padx=12, pady=(8, 4))

        self.status_badge = ctk.CTkLabel(
            result_header,
            text="🟢 Çevrimiçi",
            font=("Segoe UI", 10, "bold"),
            text_color="#10B981",
            fg_color="#064E3B",
            corner_radius=8,
            padx=8,
            pady=2,
        )
        self.status_badge.pack(side="left")

        self.copy_btn = ctk.CTkButton(
            result_header,
            text="📋 Kopyala",
            width=70,
            height=22,
            font=("Segoe UI", 10),
            fg_color="#1E293B",
            hover_color="#334155",
            corner_radius=8,
            command=self._copy_result,
        )
        self.copy_btn.pack(side="right")

        self.result_box = ctk.CTkTextbox(
            self.result_frame,
            height=140,
            font=("Segoe UI", 12),
            fg_color="transparent",
            text_color="#F1F5F9",
            wrap="word",
        )
        self.result_box.pack(fill="both", expand=True, padx=12, pady=(2, 10))

        # ── 4. Raycast Footer Bar (Klavye İpuçları & Durum) ────────────
        self.footer_bar = ctk.CTkFrame(self.container, fg_color="transparent")
        self.footer_bar.pack(fill="x", padx=14, pady=(2, 8))

        footer_left = ctk.CTkLabel(
            self.footer_bar,
            text="🐺 BÖRÜ RAYCAST • V14.0 PRO",
            font=("Segoe UI", 10, "bold"),
            text_color="#475569",
        )
        footer_left.pack(side="left")

        footer_right = ctk.CTkFrame(self.footer_bar, fg_color="transparent")
        footer_right.pack(side="right")

        if self._on_open_main:
            main_link = ctk.CTkButton(
                footer_right,
                text="🖥️ Ana Pencere",
                width=85,
                height=20,
                font=("Segoe UI", 10),
                fg_color="transparent",
                hover_color="#1E293B",
                text_color="#60A5FA",
                command=self._handle_open_main,
            )
            main_link.pack(side="right", padx=(4, 0))

        hints_lbl = ctk.CTkLabel(
            footer_right,
            text="[Esc] Kapat  •  [↵] Çalıştır",
            font=("Segoe UI", 10),
            text_color="#64748B",
        )
        hints_lbl.pack(side="right", padx=(0, 6))

    def _apply_suggestion(self, cmd: str) -> None:
        self.entry.delete(0, "end")
        self.entry.insert(0, cmd)
        self.entry.focus_set()
        if not cmd.endswith(":") and not cmd.endswith(" "):
            self._handle_submit()

    def _position_window(self, expanded: bool = False) -> None:
        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        width = 720
        height = 320 if expanded else 135
        x = (screen_w - width) // 2
        y = max(70, screen_h // 5)

        self.geometry(f"{width}x{height}+{x}+{y}")

    def _bind_keys(self) -> None:
        self.entry.bind("<Return>", lambda e: self._handle_submit())
        self.bind("<Escape>", lambda e: self.hide())
        self.entry.bind("<Escape>", lambda e: self.hide())
        self.bind("<Control-c>", lambda e: self._copy_result())

    def show(self) -> None:
        """Overlay çubuğunu öne çıkarır ve odağı giriş kutusuna verir."""
        self._position_window(expanded=self._is_expanded)
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after(50, lambda: self.entry.focus_force())

    def hide(self) -> None:
        """Overlay'i gizler ve durumunu temizler."""
        self.withdraw()
        self.set_status("🟢 Çevrimiçi", "#10B981")

    def toggle(self) -> None:
        """Açıksa gizler, gizliyse gösterir."""
        if self.winfo_viewable():
            self.hide()
        else:
            self.show()

    def set_status(self, text: str, color: str = "#10B981") -> None:
        self.status_badge.configure(text=text, text_color=color)

    def set_input_text(self, text: str) -> None:
        self.entry.delete(0, "end")
        self.entry.insert(0, text)
        self.entry.focus_set()

    def show_result(self, result_text: str, is_error: bool = False) -> None:
        """Sonucu overlay kartı içinde gösterir ve pencereyi genişletir."""
        self._last_result = result_text
        if not self._is_expanded:
            self.result_frame.pack(fill="both", expand=True, padx=14, pady=(0, 6), before=self.footer_bar)
            self._is_expanded = True
            self._position_window(expanded=True)

        self.result_box.configure(state="normal")
        self.result_box.delete("1.0", "end")
        self.result_box.insert("end", result_text)
        self.result_box.configure(state="disabled")

        if is_error:
            self.set_status("❌ Hata", "#EF4444")
        else:
            self.set_status("✔ Tamamlandı", "#10B981")

    def _copy_result(self) -> None:
        if self._last_result:
            try:
                self.clipboard_clear()
                self.clipboard_append(self._last_result)
                self.set_status("📋 Kopyalandı", "#38BDF8")
                self.copy_btn.configure(text="✓ Kopyalandı")
                self.after(2000, lambda: self.copy_btn.configure(text="📋 Kopyala"))
            except Exception:
                pass

    def _handle_submit(self) -> None:
        cmd = self.entry.get().strip()
        if not cmd or self._is_busy:
            return

        self._is_busy = True
        self.set_status("⚡ İşleniyor...", "#F59E0B")
        self.send_btn.configure(state="disabled")

        def _worker():
            try:
                if self._on_submit:
                    output = self._on_submit(cmd)
                else:
                    output = f"Komut alındı: {cmd}"
                self.after(0, self.show_result, output, False)
            except Exception as e:
                self.after(0, self.show_result, f"İşlem hatası: {e}", True)
            finally:
                self._is_busy = False
                self.after(0, lambda: self.send_btn.configure(state="normal"))

        threading.Thread(target=_worker, daemon=True).start()

    def _handle_mic_click(self) -> None:
        if self._on_voice:
            self._on_voice()
        else:
            self.set_status("🎙️ Bağlı Değil", "#EF4444")

    def set_mic_active(self, active: bool) -> None:
        """Mikrofon butonunun durumunu (dinliyor/hazır) günceller."""
        if active:
            self.mic_btn.configure(fg_color="#EF4444", text="🛑", hover_color="#DC2626")
            self.set_status("🎙️ Dinliyor...", "#38BDF8")
        else:
            self.mic_btn.configure(fg_color="#0284C7", text="🎙️", hover_color="#0369A1")
            self.set_status("🟢 Çevrimiçi", "#10B981")

    def _handle_open_main(self) -> None:
        self.hide()
        if self._on_open_main:
            self._on_open_main()


# Geriye dönük tam uyumluluk alias
BoruOverlayWindow = JarvisOverlayWindow
