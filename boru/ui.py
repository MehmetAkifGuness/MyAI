import queue
import threading
import time

import customtkinter as ctk

from boru.contracts import AssistantPort
from boru.voice import VoiceInputService, VoiceOutputService

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class ChatAppUI(ctk.CTk):
    """
    Modernleştirilmiş, ses destekli Börü masaüstü arayüzü.
    """

    def __init__(
        self,
        assistant: AssistantPort,
        title: str,
        startup_message: str,
    ):
        super().__init__()

        self._assistant = assistant
        self._voice_input = VoiceInputService()
        self._voice_output = VoiceOutputService(enabled=False)

        self._ui_events: queue.Queue[tuple[str, tuple]] = queue.Queue()
        self._busy_started_at: float | None = None
        self._status_after_id: str | None = None
        self._is_listening = False

        self.title(title)
        self.geometry("780x880")
        self.minsize(650, 700)

        self._build_ui(title)
        self._process_ui_events()

        self._write_message("SİSTEM", startup_message)

    def _build_ui(self, title: str) -> None:
        # ── 1. Modern Üst Bar (Header Panel) ──────────────────────────
        header_frame = ctk.CTkFrame(self, fg_color="#1a1c23", corner_radius=12)
        header_frame.pack(fill="x", padx=16, pady=(16, 8))

        # Sol taraf: Logo + Başlık + Canlı Gösterge
        brand_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        brand_frame.pack(side="left", padx=12, pady=10)

        logo_label = ctk.CTkLabel(
            brand_frame,
            text="🐺",
            font=("Segoe UI Emoji", 26),
        )
        logo_label.pack(side="left", padx=(0, 8))

        title_info_frame = ctk.CTkFrame(brand_frame, fg_color="transparent")
        title_info_frame.pack(side="left")

        title_label = ctk.CTkLabel(
            title_info_frame,
            text=title,
            font=("Segoe UI", 16, "bold"),
            text_color="#e2e8f0",
        )
        title_label.pack(anchor="w")

        self.live_indicator = ctk.CTkLabel(
            title_info_frame,
            text="🟢 Çevrimiçi & Hazır",
            font=("Segoe UI", 11),
            text_color="#48bb78",
        )
        self.live_indicator.pack(anchor="w")

        # Sağ taraf: Sesli Yanıt Toggle + Sıfırla Butonu
        control_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        control_frame.pack(side="right", padx=12, pady=10)

        self.voice_toggle = ctk.CTkSwitch(
            control_frame,
            text="🔊 Sesli Yanıt",
            font=("Segoe UI", 12),
            command=self._toggle_voice_output,
            onvalue=True,
            offvalue=False,
            progress_color="#3182ce",
        )
        self.voice_toggle.pack(side="left", padx=(0, 12))

        self.reset_button = ctk.CTkButton(
            control_frame,
            text="Temizle",
            width=80,
            height=28,
            fg_color="#2d3748",
            hover_color="#4a5568",
            font=("Segoe UI", 12),
            command=self._reset_conversation,
        )
        self.reset_button.pack(side="left")

        # ── 2. Sohbet Alanı (Chat Box) ─────────────────────────────────
        chat_container = ctk.CTkFrame(self, fg_color="#13141c", corner_radius=12)
        chat_container.pack(fill="both", expand=True, padx=16, pady=8)

        self.chat_box = ctk.CTkTextbox(
            chat_container,
            state="disabled",
            wrap="word",
            font=("Segoe UI", 13),
            fg_color="transparent",
            text_color="#f7fafc",
        )
        self.chat_box.pack(fill="both", expand=True, padx=12, pady=12)

        # ── 3. Hızlı Eylem Çipleri (Quick Action Chips) ────────────────
        chips_frame = ctk.CTkFrame(self, fg_color="transparent")
        chips_frame.pack(fill="x", padx=16, pady=(4, 6))

        chips = [
            ("❓ Yardım", "yardım"),
            ("🌐 Web Durum", "web durum"),
            ("🔧 İyileştir", "iyileştir: "),
            ("💻 Kodla", "kodla: "),
            ("📊 Değerlendir", "kendini değerlendir:"),
        ]

        for label, cmd in chips:
            btn = ctk.CTkButton(
                chips_frame,
                text=label,
                font=("Segoe UI", 11),
                height=26,
                fg_color="#232734",
                hover_color="#32384a",
                text_color="#cbd5e0",
                command=lambda c=cmd: self._insert_chip(c),
            )
            btn.pack(side="left", padx=(0, 6))

        # ── 4. Giriş Paneli (Input + Mic + Send) ────────────────────────
        input_panel = ctk.CTkFrame(self, fg_color="#1a1c23", corner_radius=12)
        input_panel.pack(fill="x", padx=16, pady=(4, 8))

        self.mic_button = ctk.CTkButton(
            input_panel,
            text="🎙️",
            width=42,
            height=40,
            font=("Segoe UI Emoji", 16),
            fg_color="#2b6cb0",
            hover_color="#2c5282",
            command=self._listen_voice,
        )
        self.mic_button.pack(side="left", padx=(10, 8), pady=8)

        self.input_box = ctk.CTkEntry(
            input_panel,
            placeholder_text="Börü'ye yazın veya mikrofona konuşun...",
            font=("Segoe UI", 13),
            height=40,
            fg_color="#232734",
            border_color="#2d3748",
        )
        self.input_box.pack(side="left", fill="x", expand=True, padx=(0, 8), pady=8)
        self.input_box.bind("<Return>", lambda _: self._send_message())

        self.send_button = ctk.CTkButton(
            input_panel,
            text="Gönder",
            width=85,
            height=40,
            font=("Segoe UI", 13, "bold"),
            fg_color="#3182ce",
            hover_color="#2b6cb0",
            command=self._send_message,
        )
        self.send_button.pack(side="left", padx=(0, 10), pady=8)

        # ── 5. Alt Bilgi / Durum Çubuğu ────────────────────────────────
        self.status_label = ctk.CTkLabel(
            self,
            text="Hazır",
            font=("Segoe UI", 11),
            text_color="#718096",
        )
        self.status_label.pack(pady=(0, 8))

    def _insert_chip(self, cmd: str) -> None:
        self.input_box.delete(0, "end")
        self.input_box.insert(0, cmd)
        self.input_box.focus_set()

    def _toggle_voice_output(self) -> None:
        self._voice_output.enabled = bool(self.voice_toggle.get())

    def _listen_voice(self) -> None:
        if self._is_listening:
            return

        self._is_listening = True
        self.mic_button.configure(fg_color="#e53e3e", text="🛑")
        self.status_label.configure(text="Dinleniyor... Lütfen konuşun.", text_color="#fc8181")
        self.live_indicator.configure(text="🔴 Dinleniyor...", text_color="#fc8181")

        def worker():
            try:
                recognized_text = self._voice_input.listen_once()
                self._ui_events.put(("voice_text", (recognized_text,)))
            except Exception as err:
                self._ui_events.put(("voice_error", (str(err),)))

        threading.Thread(target=worker, daemon=True).start()

    def _process_ui_events(self) -> None:
        while True:
            try:
                event_name, args = self._ui_events.get_nowait()
            except queue.Empty:
                break

            if event_name == "write":
                self._write_message(*args)

            elif event_name == "stream_start":
                self._stream_start(*args)

            elif event_name == "stream_chunk":
                self._stream_chunk(*args)

            elif event_name == "stream_end":
                self._stream_end()

            elif event_name == "voice_text":
                text = args[0]
                self._is_listening = False
                self.mic_button.configure(fg_color="#2b6cb0", text="🎙️")
                self.live_indicator.configure(text="🟢 Çevrimiçi & Hazır", text_color="#48bb78")
                self.status_label.configure(text="Hazır", text_color="#718096")
                self.input_box.delete(0, "end")
                self.input_box.insert(0, text)
                self._send_message()

            elif event_name == "voice_error":
                err_msg = args[0]
                self._is_listening = False
                self.mic_button.configure(fg_color="#2b6cb0", text="🎙️")
                self.live_indicator.configure(text="🟢 Çevrimiçi & Hazır", text_color="#48bb78")
                self.status_label.configure(text=f"Ses algılanamadı: {err_msg}", text_color="#cbd5e0")

            elif event_name == "busy":
                self._set_busy(*args)

        self.after(40, self._process_ui_events)

    def _write_message(self, sender: str, message: str) -> None:
        self.chat_box.configure(state="normal")
        divider = "─" * 45
        self.chat_box.insert("end", f"\n{sender}\n{message}\n{divider}\n")
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def _stream_start(self, sender: str) -> None:
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", f"\n{sender}\n")
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def _stream_chunk(self, chunk: str) -> None:
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", chunk)
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def _stream_end(self) -> None:
        self.chat_box.configure(state="normal")
        divider = "─" * 45
        self.chat_box.insert("end", f"\n{divider}\n")
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def _queue_message(self, sender: str, message: str) -> None:
        self._ui_events.put(("write", (sender, message)))

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.send_button.configure(state=state)
        self.reset_button.configure(state=state)
        self.input_box.configure(state=state)

        if busy:
            self._busy_started_at = time.monotonic()
            self.live_indicator.configure(text="🟡 Düşünüyor...", text_color="#ecc94b")
            self._update_busy_status()
        else:
            self._busy_started_at = None
            if self._status_after_id is not None:
                self.after_cancel(self._status_after_id)
                self._status_after_id = None
            self.live_indicator.configure(text="🟢 Çevrimiçi & Hazır", text_color="#48bb78")
            self.status_label.configure(text="Hazır", text_color="#718096")

        if not busy:
            self.input_box.focus_set()

    def _update_busy_status(self) -> None:
        if self._busy_started_at is None:
            return
        elapsed = time.monotonic() - self._busy_started_at
        self.status_label.configure(text=f"İşleniyor... {elapsed:.1f} sn")
        self._status_after_id = self.after(250, self._update_busy_status)

    def _queue_busy(self, busy: bool) -> None:
        self._ui_events.put(("busy", (busy,)))

    def _send_message(self) -> None:
        message = self.input_box.get().strip()
        if not message:
            return

        self.input_box.delete(0, "end")
        self._write_message("👤 Sen", message)
        self._set_busy(True)

        threading.Thread(
            target=self._generate_reply,
            args=(message,),
            daemon=True,
        ).start()

    def _generate_reply(self, message: str) -> None:
        try:
            stream_func = getattr(self._assistant, "reply_stream", None)
            full_response = ""
            if callable(stream_func):
                self._ui_events.put(("stream_start", ("🐺 Börü",)))
                for chunk in stream_func(message):
                    full_response += chunk
                    self._ui_events.put(("stream_chunk", (chunk,)))
                self._ui_events.put(("stream_end", ()))
            else:
                full_response = self._assistant.reply(message)
                self._queue_message("🐺 Börü", full_response)

            # Sesli yanıt açıksa seslendir
            if self._voice_output.enabled and full_response:
                self._voice_output.speak(full_response)

        except Exception as error:
            self._queue_message("❌ Hata", f"Yanıt üretilemedi: {error}")
        finally:
            self._queue_busy(False)

    def _reset_conversation(self) -> None:
        self._assistant.reset_conversation()
        self._write_message(
            "SİSTEM",
            "Kısa süreli konuşma geçmişi temizlendi. Kalıcı profil ve öğrenilen dersler korunuyor.",
        )
