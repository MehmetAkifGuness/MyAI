from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

import customtkinter as ctk

logger = logging.getLogger(__name__)


class JarvisOverlayWindow(ctk.CTkToplevel):
    """
    Ekranın üst-orta kısmında anında beliren, Raycast / Spotlight / Siri tarzında
    modern koyu temalı Jarvis Hızlı Komut ve Ses Çubuğu.
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
        self.overrideredirect(True)  # Çerçevesiz, şık yüzen pencere
        self.configure(fg_color="#10121a")

        self._is_expanded = False
        self._is_busy = False

        self._setup_layout()
        self._position_window()
        self._bind_keys()

        # İlk başta gizli başla
        self.withdraw()

    def _setup_layout(self) -> None:
        # Dış Koyu Çerçeve
        self.container = ctk.CTkFrame(
            self,
            fg_color="#161822",
            border_color="#3182ce",
            border_width=2,
            corner_radius=14,
        )
        self.container.pack(fill="both", expand=True, padx=2, pady=2)

        # ── 1. Üst Başlık & Rozet Çubuğu ────────────────────────────
        header = ctk.CTkFrame(self.container, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(8, 4))

        title_label = ctk.CTkLabel(
            header,
            text="🐺 BÖRÜ",
            font=("Segoe UI", 12, "bold"),
            text_color="#ecc94b",
        )
        title_label.pack(side="left")

        self.status_badge = ctk.CTkLabel(
            header,
            text="🟢 Hazır",
            font=("Segoe UI", 10),
            text_color="#48bb78",
        )
        self.status_badge.pack(side="left", padx=(10, 0))

        # Sağ butonlar: Ana Pencere & Kapat
        close_btn = ctk.CTkButton(
            header,
            text="✕",
            width=26,
            height=20,
            font=("Segoe UI", 11, "bold"),
            fg_color="#2d3748",
            hover_color="#e53e3e",
            command=self.hide,
        )
        close_btn.pack(side="right", padx=(4, 0))

        if self._on_open_main:
            main_btn = ctk.CTkButton(
                header,
                text="🖥️ Ana Pencere",
                width=85,
                height=20,
                font=("Segoe UI", 10),
                fg_color="#2d3748",
                hover_color="#4a5568",
                command=self._handle_open_main,
            )
            main_btn.pack(side="right")

        # ── 2. Giriş & Butonlar Çubuğu ──────────────────────────────
        input_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        input_frame.pack(fill="x", padx=12, pady=(4, 8))

        self.entry = ctk.CTkEntry(
            input_frame,
            placeholder_text="Börü'ye sor veya komut ver... (Esc: Kapat, Enter: Gönder)",
            font=("Segoe UI", 13),
            fg_color="#1a202c",
            border_color="#4a5568",
            height=38,
        )
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.mic_btn = ctk.CTkButton(
            input_frame,
            text="🎙️",
            width=38,
            height=38,
            font=("Segoe UI Emoji", 15),
            fg_color="#2b6cb0",
            hover_color="#2c5282",
            command=self._handle_mic_click,
        )
        self.mic_btn.pack(side="left", padx=(0, 6))

        self.send_btn = ctk.CTkButton(
            input_frame,
            text="Gönder",
            width=70,
            height=38,
            font=("Segoe UI", 12, "bold"),
            fg_color="#3182ce",
            hover_color="#2b6cb0",
            command=self._handle_submit,
        )
        self.send_btn.pack(side="left")

        # ── 3. Yanıt & Çıktı Kartı (Gerektiğinde Genişler) ──────────
        self.result_frame = ctk.CTkFrame(self.container, fg_color="#0f111a", corner_radius=8)
        self.result_box = ctk.CTkTextbox(
            self.result_frame,
            height=120,
            font=("Consolas", 11),
            fg_color="transparent",
            text_color="#e2e8f0",
            wrap="word",
        )
        self.result_box.pack(fill="both", expand=True, padx=8, pady=8)

    def _position_window(self, expanded: bool = False) -> None:
        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        width = 680
        height = 240 if expanded else 105
        x = (screen_w - width) // 2
        y = max(60, screen_h // 5)

        self.geometry(f"{width}x{height}+{x}+{y}")

    def _bind_keys(self) -> None:
        self.entry.bind("<Return>", lambda e: self._handle_submit())
        self.bind("<Escape>", lambda e: self.hide())
        self.entry.bind("<Escape>", lambda e: self.hide())

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
        self.set_status("🟢 Hazır", "#48bb78")

    def toggle(self) -> None:
        """Açıksa gizler, gizliyse gösterir."""
        if self.winfo_viewable():
            self.hide()
        else:
            self.show()

    def set_status(self, text: str, color: str = "#48bb78") -> None:
        self.status_badge.configure(text=text, text_color=color)

    def set_input_text(self, text: str) -> None:
        self.entry.delete(0, "end")
        self.entry.insert(0, text)
        self.entry.focus_set()

    def show_result(self, result_text: str, is_error: bool = False) -> None:
        """Sonucu overlay kartı içinde gösterir ve pencereyi genişletir."""
        if not self._is_expanded:
            self.result_frame.pack(fill="both", expand=True, padx=12, pady=(0, 10))
            self._is_expanded = True
            self._position_window(expanded=True)

        self.result_box.configure(state="normal")
        self.result_box.delete("1.0", "end")
        self.result_box.insert("end", result_text)
        self.result_box.configure(state="disabled")

        if is_error:
            self.set_status("❌ Hata", "#f56565")
        else:
            self.set_status("✔ Tamamlandı", "#48bb78")

    def _handle_submit(self) -> None:
        cmd = self.entry.get().strip()
        if not cmd or self._is_busy:
            return

        self._is_busy = True
        self.set_status("⚡ İşleniyor...", "#ecc94b")
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
            self.set_status("🎙️ Dinleme servisi bağlı değil", "#f56565")

    def set_mic_active(self, active: bool) -> None:
        """Mikrofon butonunun durumunu (dinliyor/hazır) günceller."""
        if active:
            self.mic_btn.configure(fg_color="#e53e3e", text="🛑")
        else:
            self.mic_btn.configure(fg_color="#2b6cb0", text="🎙️")

    def _handle_open_main(self) -> None:
        self.hide()
        if self._on_open_main:
            self._on_open_main()


# Geriye dönük uyumluluk için alias
BoruOverlayWindow = JarvisOverlayWindow


