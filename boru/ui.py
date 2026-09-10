import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time

import customtkinter as ctk

from boru.contracts import AssistantPort
from boru.voice import VoiceInputService, VoiceOutputService

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class ChatAppUI(ctk.CTk):
    """
    Modernleştirilmiş, Sol Dosya Ağacı, Canlı Konsol/Terminal ve
    Görsel Renkli Diff destekli profesyonel Börü masaüstü arayüzü.
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
        self._project_root = Path(".").resolve()

        self._ui_events: queue.Queue[tuple[str, tuple]] = queue.Queue()
        self._busy_started_at: float | None = None
        self._status_after_id: str | None = None
        self._is_listening = False
        self._sidebar_visible = True
        self._terminal_visible = False

        self.title(title)
        self.geometry("980x880")
        self.minsize(800, 700)

        self._jarvis_overlay = None
        self._hotkey_mgr = None

        self._build_ui(title)
        self._setup_jarvis_hotkey()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._process_ui_events()

        self._write_message("SİSTEM", startup_message)

    def _build_ui(self, title: str) -> None:
        # ── 1. Modern Üst Bar (Header Panel) ──────────────────────────
        header_frame = ctk.CTkFrame(self, fg_color="#1a1c23", corner_radius=12)
        header_frame.pack(fill="x", padx=16, pady=(16, 8))

        # Sol taraf: Sidebar Toggle + Logo + Başlık + Canlı Gösterge
        brand_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        brand_frame.pack(side="left", padx=12, pady=10)

        self.toggle_sidebar_btn = ctk.CTkButton(
            brand_frame,
            text="📂",
            width=36,
            height=32,
            font=("Segoe UI Emoji", 14),
            fg_color="#2d3748",
            hover_color="#4a5568",
            command=self._toggle_sidebar,
        )
        self.toggle_sidebar_btn.pack(side="left", padx=(0, 10))

        logo_label = ctk.CTkLabel(
            brand_frame,
            text="🐺",
            font=("Segoe UI Emoji", 24),
        )
        logo_label.pack(side="left", padx=(0, 8))

        title_info_frame = ctk.CTkFrame(brand_frame, fg_color="transparent")
        title_info_frame.pack(side="left")

        title_label = ctk.CTkLabel(
            title_info_frame,
            text=title,
            font=("Segoe UI", 15, "bold"),
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
        self.voice_toggle.pack(side="left", padx=(0, 10))

        self.terminal_toggle_btn = ctk.CTkButton(
            control_frame,
            text="📟 Terminal",
            width=85,
            height=28,
            fg_color="#2d3748",
            hover_color="#4a5568",
            font=("Segoe UI", 12),
            command=self._toggle_terminal,
        )
        self.terminal_toggle_btn.pack(side="left", padx=(0, 10))

        self.jarvis_btn = ctk.CTkButton(
            control_frame,
            text="⚡ Jarvis (Ctrl+Shift+B)",
            width=150,
            height=28,
            fg_color="#553c9a",
            hover_color="#6b46c1",
            font=("Segoe UI", 12, "bold"),
            command=self._toggle_jarvis,
        )
        self.jarvis_btn.pack(side="left", padx=(0, 10))

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

        # ── 2. Ana Çalışma Alanı (Sidebar + Chat Alanı) ────────────────
        self.main_body = ctk.CTkFrame(self, fg_color="transparent")
        self.main_body.pack(fill="both", expand=True, padx=16, pady=4)

        # Sol: Dosya Ağacı / Proje Gezgini Paneli
        self.sidebar_frame = ctk.CTkFrame(self.main_body, width=220, fg_color="#181a20", corner_radius=12)
        self.sidebar_frame.pack(side="left", fill="y", padx=(0, 10))
        self.sidebar_frame.pack_propagate(False)

        sidebar_title_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        sidebar_title_frame.pack(fill="x", padx=10, pady=(10, 6))

        ctk.CTkLabel(
            sidebar_title_frame,
            text="PROJE DOSYALARI",
            font=("Segoe UI", 11, "bold"),
            text_color="#a0aec0",
        ).pack(side="left")

        refresh_btn = ctk.CTkButton(
            sidebar_title_frame,
            text="🔄",
            width=28,
            height=24,
            font=("Segoe UI Emoji", 11),
            fg_color="#2d3748",
            hover_color="#4a5568",
            command=self._populate_file_tree,
        )
        refresh_btn.pack(side="right")

        self.file_scroll = ctk.CTkScrollableFrame(self.sidebar_frame, fg_color="transparent")
        self.file_scroll.pack(fill="both", expand=True, padx=4, pady=4)
        self._populate_file_tree()

        # Sağ: Sohbet, Diff ve Katlanabilir Terminal Alanı
        self.right_container = ctk.CTkFrame(self.main_body, fg_color="#13141c", corner_radius=12)
        self.right_container.pack(side="left", fill="both", expand=True)

        self.chat_box = ctk.CTkTextbox(
            self.right_container,
            state="disabled",
            wrap="word",
            font=("Segoe UI", 13),
            fg_color="transparent",
            text_color="#f7fafc",
        )
        self.chat_box.pack(fill="both", expand=True, padx=12, pady=(12, 6))

        # Renkli Diff Etiketleri Tanımla (Tkinter Text Tag'leri)
        self.chat_box.tag_config("diff_add", foreground="#48bb78", background="#1c2d20")
        self.chat_box.tag_config("diff_sub", foreground="#f56565", background="#3b1d1d")
        self.chat_box.tag_config("diff_hdr", foreground="#63b3ed", font=("Segoe UI", 12, "bold"))
        self.chat_box.tag_config("sender_user", foreground="#63b3ed", font=("Segoe UI", 13, "bold"))
        self.chat_box.tag_config("sender_bot", foreground="#ecc94b", font=("Segoe UI", 13, "bold"))
        self.chat_box.tag_config("divider", foreground="#4a5568")

        # Katlanabilir Canlı Konsol & Terminal Paneli (Varsayılan kapalı)
        self.terminal_frame = ctk.CTkFrame(self.right_container, height=200, fg_color="#0d1117", corner_radius=10)
        self.terminal_frame.pack_propagate(False)

        term_header = ctk.CTkFrame(self.terminal_frame, fg_color="transparent", height=28)
        term_header.pack(fill="x", padx=8, pady=(6, 2))

        ctk.CTkLabel(
            term_header,
            text="📟 CANLI KONSOL & TEST TERMİNALİ",
            font=("Segoe UI", 11, "bold"),
            text_color="#58a6ff",
        ).pack(side="left")

        ctk.CTkButton(
            term_header,
            text="❌ Kapat",
            width=55,
            height=22,
            font=("Segoe UI", 10),
            fg_color="#30363d",
            hover_color="#da3633",
            command=self._toggle_terminal,
        ).pack(side="right", padx=(4, 0))

        ctk.CTkButton(
            term_header,
            text="🧹 Temizle",
            width=60,
            height=22,
            font=("Segoe UI", 10),
            fg_color="#21262d",
            hover_color="#30363d",
            command=self._clear_terminal,
        ).pack(side="right")

        self.terminal_box = ctk.CTkTextbox(
            self.terminal_frame,
            state="disabled",
            wrap="none",
            font=("Consolas", 11),
            fg_color="#090d13",
            text_color="#c9d1d9",
        )
        self.terminal_box.pack(fill="both", expand=True, padx=8, pady=(2, 4))
        self.terminal_box.tag_config("term_cmd", foreground="#f0883e", font=("Consolas", 11, "bold"))
        self.terminal_box.tag_config("term_success", foreground="#3fb950")
        self.terminal_box.tag_config("term_error", foreground="#f85149")
        self.terminal_box.tag_config("term_info", foreground="#58a6ff")
        self.terminal_box.tag_config("term_dim", foreground="#8b949e")

        term_cmd_bar = ctk.CTkFrame(self.terminal_frame, fg_color="transparent")
        term_cmd_bar.pack(fill="x", padx=8, pady=(0, 6))

        ctk.CTkLabel(
            term_cmd_bar,
            text="❯",
            font=("Consolas", 12, "bold"),
            text_color="#58a6ff",
        ).pack(side="left", padx=(2, 6))

        self.terminal_cmd_entry = ctk.CTkEntry(
            term_cmd_bar,
            placeholder_text="Komut çalıştır (örn: pytest tests/test_v01.py, git status)...",
            font=("Consolas", 11),
            height=26,
            fg_color="#161b22",
            border_color="#30363d",
        )
        self.terminal_cmd_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.terminal_cmd_entry.bind("<Return>", lambda _e: self._execute_terminal_command())

        ctk.CTkButton(
            term_cmd_bar,
            text="Çalıştır",
            width=65,
            height=26,
            font=("Segoe UI", 11),
            fg_color="#238636",
            hover_color="#2ea043",
            command=self._execute_terminal_command,
        ).pack(side="right")

        # ── 3. Hızlı Eylem Çipleri (Quick Action Chips) ────────────────
        chips_frame = ctk.CTkFrame(self, fg_color="transparent")
        chips_frame.pack(fill="x", padx=16, pady=(4, 6))

        chips = [
            ("⚡ Jarvis", "_toggle_jarvis_"),
            ("❓ Yardım", "yardım"),
            ("🧪 Test Üret", "test üret: "),
            ("🕸️ Bağımlılık", "bağımlılıklar: "),
            ("🔍 Sembol", "sembol ara: "),
            ("📟 Terminal", "_toggle_terminal_"),
            ("🔧 İyileştir", "iyileştir: "),
            ("💻 Kodla", "kodla: "),
            ("📊 Değerlendir", "kendini değerlendir:"),
            ("🌐 Web Durum", "web durum"),
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

    def _toggle_sidebar(self) -> None:
        if self._sidebar_visible:
            self.sidebar_frame.pack_forget()
            self._sidebar_visible = False
            self.toggle_sidebar_btn.configure(fg_color="#1a202c")
        else:
            self.sidebar_frame.pack(side="left", fill="y", padx=(0, 10), before=self.main_body.winfo_children()[1])
            self._sidebar_visible = True
            self.toggle_sidebar_btn.configure(fg_color="#2d3748")

    def _toggle_terminal(self) -> None:
        if self._terminal_visible:
            self.terminal_frame.pack_forget()
            self._terminal_visible = False
            self.terminal_toggle_btn.configure(fg_color="#2d3748")
        else:
            self.terminal_frame.pack(fill="x", padx=12, pady=(0, 10))
            self._terminal_visible = True
            self.terminal_toggle_btn.configure(fg_color="#3182ce")
            self.terminal_cmd_entry.focus_set()

    def _clear_terminal(self) -> None:
        self.terminal_box.configure(state="normal")
        self.terminal_box.delete("1.0", "end")
        self.terminal_box.configure(state="disabled")

    def log_terminal(self, message: str, level: str = "info") -> None:
        """Arka plan iş parçacıklarından güvenle canlı terminal paneline log basar."""
        self.after(0, self._append_terminal_log, message, level)

    def _append_terminal_log(self, message: str, level: str) -> None:
        tag = {
            "cmd": "term_cmd",
            "success": "term_success",
            "error": "term_error",
            "info": "term_info",
        }.get(level, "term_dim")
        self.terminal_box.configure(state="normal")
        self.terminal_box.insert("end", f"{message}\n", tag)
        self.terminal_box.see("end")
        self.terminal_box.configure(state="disabled")

    def _execute_terminal_command(self) -> None:
        cmd = self.terminal_cmd_entry.get().strip()
        if not cmd:
            return
        self.terminal_cmd_entry.delete(0, "end")
        if not self._terminal_visible:
            self._toggle_terminal()
        threading.Thread(target=self._run_cmd_async, args=(cmd,), daemon=True).start()

    def _run_cmd_async(self, cmd: str) -> None:
        self.log_terminal(f"❯ {cmd}", "cmd")
        try:
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(self._project_root),
            )
            if process.stdout:
                for line in process.stdout:
                    self.log_terminal(line.rstrip())
            process.wait()
            if process.returncode == 0:
                self.log_terminal("✔ Başarılı (Çıkış kodu: 0)", "success")
            else:
                self.log_terminal(f"❌ Başarısız (Çıkış kodu: {process.returncode})", "error")
        except Exception as err:
            self.log_terminal(f"❌ Komut yürütülemedi: {err}", "error")

    def _populate_file_tree(self) -> None:
        """Proje kökündeki ilgili Python ve konfigürasyon dosyalarını listeler."""
        for widget in self.file_scroll.winfo_children():
            widget.destroy()

        try:
            items: list[tuple[str, str]] = []
            for root, dirs, files in os.walk(self._project_root):
                # .git, __pycache__, .pytest_cache atla
                dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                rel_dir = os.path.relpath(root, self._project_root)
                for file in files:
                    if file.endswith((".py", ".json", ".txt", ".md")):
                        rel_path = file if rel_dir == "." else os.path.join(rel_dir, file).replace("\\", "/")
                        items.append((file, rel_path))

            items.sort(key=lambda x: x[1])
            for filename, rel_path in items[:60]:
                btn = ctk.CTkButton(
                    self.file_scroll,
                    text=f"📄 {rel_path}",
                    anchor="w",
                    height=24,
                    font=("Consolas", 11),
                    fg_color="transparent",
                    hover_color="#232734",
                    text_color="#cbd5e0",
                    command=lambda p=rel_path: self._select_file(p),
                )
                btn.pack(fill="x", pady=1)
        except Exception:
            pass

    def _select_file(self, path: str) -> None:
        """Tıklanan dosya adını giriş kutusuna akıllıca ekler."""
        current = self.input_box.get()
        if not current:
            self.input_box.insert(0, f"{path} dosyasını incele")
        else:
            self.input_box.insert("end", f" {path}")
        self.input_box.focus_set()

    def _insert_chip(self, cmd: str) -> None:
        if cmd == "_toggle_terminal_":
            self._toggle_terminal()
            return
        if cmd == "_toggle_jarvis_":
            self._toggle_jarvis()
            return
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
        """Mesajları renkli diff ve formatlama desteğiyle yazar."""
        self.chat_box.configure(state="normal")
        divider = "─" * 50

        sender_tag = "sender_user" if "Sen" in sender else "sender_bot"
        self.chat_box.insert("end", f"\n{sender}\n", sender_tag)

        # Eğer mesaj bir diff içeriyorsa satır satır renklendir
        for line in message.splitlines(keepends=True):
            if line.startswith("+") and not line.startswith("+++"):
                self.chat_box.insert("end", line, "diff_add")
            elif line.startswith("-") and not line.startswith("---"):
                self.chat_box.insert("end", line, "diff_sub")
            elif line.startswith("@@"):
                self.chat_box.insert("end", line, "diff_hdr")
            else:
                self.chat_box.insert("end", line)

        self.chat_box.insert("end", f"\n{divider}\n", "divider")
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def _stream_start(self, sender: str) -> None:
        self.chat_box.configure(state="normal")
        sender_tag = "sender_user" if "Sen" in sender else "sender_bot"
        self.chat_box.insert("end", f"\n{sender}\n", sender_tag)
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def _stream_chunk(self, chunk: str) -> None:
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", chunk)
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def _stream_end(self) -> None:
        self.chat_box.configure(state="normal")
        divider = "─" * 50
        self.chat_box.insert("end", f"\n{divider}\n", "divider")
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
        self.log_terminal(f"❯ [KULLANICI]: {message}", "cmd")
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

            self.log_terminal(f"✔ Yanıt tamamlandı ({len(full_response)} karakter)", "success")

            # Sesli yanıt açıksa seslendir
            if self._voice_output.enabled and full_response:
                self._voice_output.speak(full_response)

        except Exception as error:
            self.log_terminal(f"❌ Hata: {error}", "error")
            self._queue_message("❌ Hata", f"Yanıt üretilemedi: {error}")
        finally:
            self._queue_busy(False)

    def _reset_conversation(self) -> None:
        self._assistant.reset_conversation()
        self._write_message(
            "SİSTEM",
            "Kısa süreli konuşma geçmişi temizlendi. Kalıcı profil ve öğrenilen dersler korunuyor.",
        )

    def _setup_jarvis_hotkey(self) -> None:
        """Jarvis Overlay ve Global Hotkey yöneticisini başlatır."""
        try:
            from boru.hotkey import GlobalHotkeyManager, JarvisOverlayWindow

            self._jarvis_overlay = JarvisOverlayWindow(
                master=self,
                on_submit_command=self._handle_jarvis_command,
                on_voice_requested=self._handle_jarvis_voice,
                on_open_main_ui=self.bring_to_front,
            )
            self._hotkey_mgr = GlobalHotkeyManager()
            # Ctrl+Shift+B -> Jarvis Spotlight Overlay Aç/Kapat
            self._hotkey_mgr.register("ctrl+shift+b", lambda: self.after(0, self._toggle_jarvis))
            # Ctrl+Shift+J -> Doğrudan Sesli Bas-Konuş (Push-to-Talk)
            self._hotkey_mgr.register("ctrl+shift+j", lambda: self.after(0, self._trigger_jarvis_push_to_talk))
            self._hotkey_mgr.start()
            self.log_terminal("✔ Jarvis Global Hotkey (Ctrl+Shift+B, Ctrl+Shift+J) aktif.", "success")
        except Exception as e:
            self.log_terminal(f"⚠️ Jarvis Hotkey başlatılamadı: {e}", "info")

    def _toggle_jarvis(self) -> None:
        if getattr(self, "_jarvis_overlay", None):
            self._jarvis_overlay.toggle()

    def _trigger_jarvis_push_to_talk(self) -> None:
        if getattr(self, "_jarvis_overlay", None):
            self._jarvis_overlay.show()
            self._handle_jarvis_voice()

    def _handle_jarvis_command(self, cmd: str) -> str:
        """Jarvis Overlay üzerinden gelen komutları yürütür ve ana UI'a da yansıtır."""
        self.log_terminal(f"❯ [JARVIS]: {cmd}", "cmd")
        self._queue_message("👤 Sen (Jarvis)", cmd)
        try:
            reply = self._assistant.reply(cmd)
            self._queue_message("🐺 Börü", reply)
            if self._voice_output.enabled and reply:
                self._voice_output.speak(reply)
            return reply
        except Exception as err:
            self.log_terminal(f"❌ Jarvis komut hatası: {err}", "error")
            raise err

    def _handle_jarvis_voice(self) -> None:
        """Jarvis mikrofonundan ses dinler ve overlay'e aktarır."""
        if not getattr(self, "_jarvis_overlay", None):
            return

        self._jarvis_overlay.set_status("🎙️ Dinliyor...", "#ecc94b")

        def _voice_worker():
            try:
                text = self._voice_input.listen_once(timeout=5.0, phrase_time_limit=10.0)
                self.after(0, lambda: self._jarvis_overlay.set_input_text(text))
                self.after(60, lambda: self._jarvis_overlay._handle_submit())
            except Exception as e:
                self.after(0, lambda: self._jarvis_overlay.set_status(f"❌ {e}", "#f56565"))

        threading.Thread(target=_voice_worker, daemon=True).start()

    def bring_to_front(self) -> None:
        """Ana pencereyi masaüstünde tüm pencerelerin önüne getirir."""
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after(100, lambda: self.attributes("-topmost", False))
        self.focus_force()

    def _on_close(self) -> None:
        """Pencere kapatıldığında global hotkey dinleyicisini temizce durdurur."""
        if getattr(self, "_hotkey_mgr", None):
            self._hotkey_mgr.stop()
        self.destroy()

