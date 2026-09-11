import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time

import math
import tkinter as tk
import customtkinter as ctk

from boru.contracts import AssistantPort
from boru.voice import VoiceInputService, VoiceOutputService, AudioCueService

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class AudioWaveVisualizer(tk.Canvas):
    """
    Siri / Jarvis tarzı akışkan, canlı ses dalgası görselleştiricisi.
    Boşta (idle), Dinliyor (listening), Konuşuyor (speaking) ve Düşünüyor (thinking)
    modları arasında dinamik ve yumuşak geçiş yapar.
    """

    def __init__(self, master, width: int = 100, height: int = 20, bg: str = "#1a1c23", **kwargs):
        super().__init__(master, width=width, height=height, bg=bg, highlightthickness=0, **kwargs)
        self._width = width
        self._height = height
        self._phase = 0.0
        self._mode = "idle"
        self._after_id = None
        self._draw_wave()

    def set_mode(self, mode: str) -> None:
        self._mode = mode

    def _draw_wave(self) -> None:
        if not self.winfo_exists():
            return
        self.delete("all")
        mid_y = self._height / 2.0
        self._phase += 0.15

        if self._mode == "listening":
            # Dinleme Modu: Canlı turkuaz/yeşil ekolayzır barları
            colors = ["#48bb78", "#38b2ac", "#4fd1c5"]
            num_bars = 7
            spacing = self._width / (num_bars + 1)
            for i in range(num_bars):
                x = (i + 1) * spacing
                amp = math.sin(self._phase + i * 0.9) * (self._height * 0.4) + 2.0
                bar_h = max(2.5, abs(amp))
                color = colors[i % len(colors)]
                self.create_line(x, mid_y - bar_h, x, mid_y + bar_h, fill=color, width=2.5, capstyle="round")

        elif self._mode == "speaking":
            # Konuşma Modu: Akışkan çift sinüs ses dalgası
            points = []
            for x in range(0, self._width, 4):
                rel_x = x / self._width
                envelope = math.sin(rel_x * math.pi)
                y = mid_y + math.sin(self._phase + rel_x * 8.0) * (self._height * 0.38) * envelope
                points.extend([x, y])
            if len(points) >= 4:
                self.create_line(*points, fill="#805ad5", width=2, smooth=True)

            points2 = []
            for x in range(0, self._width, 4):
                rel_x = x / self._width
                envelope = math.sin(rel_x * math.pi)
                y = mid_y + math.cos(self._phase * 1.3 + rel_x * 6.0) * (self._height * 0.28) * envelope
                points2.extend([x, y])
            if len(points2) >= 4:
                self.create_line(*points2, fill="#4299e1", width=1.5, smooth=True)

        elif self._mode == "thinking":
            # Düşünme Modu: Amber rengi nabız noktaları
            num_dots = 5
            spacing = self._width / (num_dots + 1)
            for i in range(num_dots):
                x = (i + 1) * spacing
                pulse = math.sin(self._phase * 1.4 + i * 0.8)
                r = 1.8 + max(0.4, pulse * 2.0)
                self.create_oval(x - r, mid_y - r, x + r, mid_y + r, fill="#ecc94b", outline="")

        else:
            # Boşta (Idle) Modu: Sakin, ince parlayan yatay çizgi ve süzülen hafif nokta
            self.create_line(10, mid_y, self._width - 10, mid_y, fill="#374151", width=1.2)
            pulse_x = (math.sin(self._phase * 0.4) * 0.5 + 0.5) * (self._width - 30) + 15
            self.create_oval(pulse_x - 1.5, mid_y - 1.5, pulse_x + 1.5, mid_y + 1.5, fill="#64748b", outline="")

        self._after_id = self.after(50, self._draw_wave)


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
        self._audio_cues = AudioCueService(enabled=True)
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
        self._tray = None

        self._build_ui(title)
        self._setup_jarvis_hotkey()
        self._setup_system_tray()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._process_ui_events()

        self._write_message("SİSTEM", startup_message)

    def _build_ui(self, title: str) -> None:
        # ── 1. Modern Üst Bar (Glassmorphic Header Panel) ──────────────
        header_frame = ctk.CTkFrame(self, fg_color="#0F1420", border_color="#1E293B", border_width=1, corner_radius=16)
        header_frame.pack(fill="x", padx=16, pady=(16, 8))

        # Sol taraf: Sidebar Toggle + Logo + Başlık + Canlı Gösterge
        brand_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        brand_frame.pack(side="left", padx=14, pady=10)

        self.toggle_sidebar_btn = ctk.CTkButton(
            brand_frame,
            text="📂",
            width=36,
            height=32,
            font=("Segoe UI Emoji", 14),
            fg_color="#1E293B",
            hover_color="#334155",
            corner_radius=10,
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
            text_color="#F8FAFC",
        )
        title_label.pack(anchor="w")

        status_sub_frame = ctk.CTkFrame(title_info_frame, fg_color="transparent")
        status_sub_frame.pack(anchor="w")

        self.live_indicator = ctk.CTkLabel(
            status_sub_frame,
            text="🟢 Çevrimiçi | V14.0",
            font=("Segoe UI", 11, "bold"),
            text_color="#10B981",
        )
        self.live_indicator.pack(side="left")

        self.visualizer = AudioWaveVisualizer(status_sub_frame, width=90, height=18, bg="#0F1420")
        self.visualizer.pack(side="left", padx=(10, 0))

        # Sağ taraf: Sesli Yanıt Toggle + Sıfırla Butonu
        control_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        control_frame.pack(side="right", padx=14, pady=10)

        self.voice_toggle = ctk.CTkSwitch(
            control_frame,
            text="🔊 Sesli Yanıt",
            font=("Segoe UI", 12),
            command=self._toggle_voice_output,
            onvalue=True,
            offvalue=False,
            progress_color="#6366F1",
        )
        self.voice_toggle.pack(side="left", padx=(0, 10))

        self.terminal_toggle_btn = ctk.CTkButton(
            control_frame,
            text="📟 Terminal",
            width=85,
            height=28,
            fg_color="#1E293B",
            hover_color="#334155",
            corner_radius=10,
            font=("Segoe UI", 12),
            command=self._toggle_terminal,
        )
        self.terminal_toggle_btn.pack(side="left", padx=(0, 10))

        self.jarvis_btn = ctk.CTkButton(
            control_frame,
            text="⚡ Spotlight (Ctrl+Shift+B)",
            width=170,
            height=28,
            fg_color="#4F46E5",
            hover_color="#4338CA",
            corner_radius=10,
            font=("Segoe UI", 12, "bold"),
            command=self._toggle_jarvis,
        )
        self.jarvis_btn.pack(side="left", padx=(0, 10))

        self.reset_button = ctk.CTkButton(
            control_frame,
            text="Temizle",
            width=75,
            height=28,
            fg_color="#1E293B",
            hover_color="#334155",
            corner_radius=10,
            font=("Segoe UI", 12),
            command=self._reset_conversation,
        )
        self.reset_button.pack(side="left")

        # ── 2. Ana Çalışma Alanı (Sidebar + Chat Alanı) ────────────────
        self.main_body = ctk.CTkFrame(self, fg_color="transparent")
        self.main_body.pack(fill="both", expand=True, padx=16, pady=4)

        # Sol: Dosya Ağacı / Proje Gezgini Paneli
        self.sidebar_frame = ctk.CTkFrame(self.main_body, width=220, fg_color="#0B0F19", border_color="#1E293B", border_width=1, corner_radius=16)
        self.sidebar_frame.pack(side="left", fill="y", padx=(0, 10))
        self.sidebar_frame.pack_propagate(False)

        sidebar_title_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        sidebar_title_frame.pack(fill="x", padx=12, pady=(12, 6))

        ctk.CTkLabel(
            sidebar_title_frame,
            text="PROJE GEZGİNİ",
            font=("Segoe UI", 11, "bold"),
            text_color="#64748B",
        ).pack(side="left")

        refresh_btn = ctk.CTkButton(
            sidebar_title_frame,
            text="🔄",
            width=28,
            height=24,
            font=("Segoe UI Emoji", 11),
            fg_color="#1E293B",
            hover_color="#334155",
            corner_radius=8,
            command=self._populate_file_tree,
        )
        refresh_btn.pack(side="right")

        self.file_scroll = ctk.CTkScrollableFrame(self.sidebar_frame, fg_color="transparent")
        self.file_scroll.pack(fill="both", expand=True, padx=4, pady=4)
        self._populate_file_tree()

        # Sağ: Sohbet, Diff ve Katlanabilir Terminal Alanı
        self.right_container = ctk.CTkFrame(self.main_body, fg_color="#0D121D", border_color="#1E293B", border_width=1, corner_radius=16)
        self.right_container.pack(side="left", fill="both", expand=True)

        self.chat_box = ctk.CTkTextbox(
            self.right_container,
            state="disabled",
            wrap="word",
            font=("Segoe UI", 13),
            fg_color="transparent",
            text_color="#F8FAFC",
        )
        self.chat_box.pack(fill="both", expand=True, padx=14, pady=(14, 6))

        # Renkli Diff Etiketleri Tanımla (2026 Modern Neon & Card Palette)
        self.chat_box.tag_config("diff_add", foreground="#10B981", background="#064E3B")
        self.chat_box.tag_config("diff_sub", foreground="#F43F5E", background="#4C0519")
        self.chat_box.tag_config("diff_hdr", foreground="#38BDF8")
        self.chat_box.tag_config("sender_user", foreground="#818CF8")
        self.chat_box.tag_config("sender_bot", foreground="#38BDF8")
        self.chat_box.tag_config("divider", foreground="#1E293B")

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
        self.terminal_box.tag_config("term_cmd", foreground="#f0883e")
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
            ("⚡ Spotlight", "_toggle_jarvis_"),
            ("🌅 Günün Brifingi", "bana brifing ver"),
            ("🎙️ Sesli Not", "notlarıma ekle: "),
            ("📂 Masaüstü Düzenle", "masaüstümü düzenle"),
            ("🧠 Ansiklopedi", "hakkında bilgi ver"),
            ("📟 Terminal", "_toggle_terminal_"),
            ("❓ Yardım", "yardım"),
            ("💻 Kodla", "kodla: "),
            ("📊 Değerlendir", "kendini değerlendir:"),
        ]

        for label, cmd in chips:
            btn = ctk.CTkButton(
                chips_frame,
                text=label,
                font=("Segoe UI", 11),
                height=26,
                fg_color="#131B2E",
                hover_color="#1E293B",
                border_color="#1E293B",
                border_width=1,
                corner_radius=12,
                text_color="#94A3B8",
                command=lambda c=cmd: self._insert_chip(c),
            )
            btn.pack(side="left", padx=(0, 6))

        # ── 4. Süzülen Giriş Yuvası (Floating Pill Input Dock) ──────────
        input_panel = ctk.CTkFrame(self, fg_color="#0F1420", border_color="#1E293B", border_width=1.5, corner_radius=20)
        input_panel.pack(fill="x", padx=16, pady=(4, 8))

        self.mic_button = ctk.CTkButton(
            input_panel,
            text="🎙️",
            width=42,
            height=42,
            font=("Segoe UI Emoji", 16),
            fg_color="#0284C7",
            hover_color="#0369A1",
            corner_radius=18,
            command=self._toggle_continuous_voice,
        )
        self.mic_button.pack(side="left", padx=(10, 8), pady=6)

        self.input_box = ctk.CTkEntry(
            input_panel,
            placeholder_text="Börü'ye yazın veya mikrofona konuşun... (Enter: Gönder)",
            font=("Segoe UI", 13),
            height=42,
            fg_color="#131B2E",
            border_color="#1E293B",
            text_color="#F8FAFC",
            placeholder_text_color="#64748B",
            corner_radius=14,
        )
        self.input_box.pack(side="left", fill="x", expand=True, padx=(0, 8), pady=6)
        self.input_box.bind("<Return>", lambda _: self._send_message())

        self.send_button = ctk.CTkButton(
            input_panel,
            text="Gönder ➤",
            width=85,
            height=42,
            font=("Segoe UI", 12, "bold"),
            fg_color="#6366F1",
            hover_color="#4F46E5",
            corner_radius=14,
            command=self._send_message,
        )
        self.send_button.pack(side="left", padx=(0, 10), pady=6)

        # ── 5. Alt Bilgi / Durum Çubuğu ────────────────────────────────
        self.status_label = ctk.CTkLabel(
            self,
            text="🐺 Börü Hazır • Ctrl+Shift+B ile Hızlı Komut",
            font=("Segoe UI", 10),
            text_color="#64748B",
        )
        self.status_label.pack(pady=(0, 6))

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
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | 0x00000008
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(self._project_root),
                startupinfo=startupinfo,
                creationflags=creationflags,
                close_fds=True,
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
                    hover_color="#161F30",
                    text_color="#94A3B8",
                    corner_radius=6,
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
                self._send_message(is_voice=True)

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
            if hasattr(self, "visualizer"):
                self.visualizer.set_mode("thinking")
            self._update_busy_status()
        else:
            self._busy_started_at = None
            if self._status_after_id is not None:
                self.after_cancel(self._status_after_id)
                self._status_after_id = None
            self.live_indicator.configure(text="🟢 Çevrimiçi & Hazır", text_color="#48bb78")
            if hasattr(self, "visualizer"):
                self.visualizer.set_mode("idle")
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

    def _send_message(self, is_voice: bool = False) -> None:
        message = self.input_box.get().strip()
        if not message:
            return

        self.input_box.delete(0, "end")
        sender = "👤 Sen (Sesli)" if is_voice else "👤 Sen"
        self._write_message(sender, message)
        self._set_busy(True)

        threading.Thread(
            target=self._generate_reply,
            args=(message, is_voice),
            daemon=True,
        ).start()

    def _generate_reply(self, message: str, is_voice: bool = False) -> None:
        self.log_terminal(f"❯ [{'SESLE SORU' if is_voice else 'KULLANICI'}]: {message}", "cmd")
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

            # Kural: Sesle sorulduysa VEYA sesli yanıt toggle'ı açıksa SESLENDİR!
            if (is_voice or self._voice_output.enabled) and full_response:
                self._voice_output.speak(full_response, force=is_voice)

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
        """Börü Overlay, Global Hotkey, Sesli Sohbet ve Arka Plan Uyandırma dinleyicisini başlatır."""
        try:
            from boru.hotkey import GlobalHotkeyManager, JarvisOverlayWindow
            from boru.voice import BackgroundWakeWordListener, ContinuousVoiceController

            self._continuous_voice = ContinuousVoiceController(
                voice_input=self._voice_input,
                voice_output=self._voice_output,
                on_user_speech=self._handle_continuous_voice_speech,
                on_status_change=self._on_voice_status_change,
                on_dialogue_ended=self._on_voice_dialogue_ended,
                audio_cues=self._audio_cues,
            )

            self._jarvis_overlay = JarvisOverlayWindow(
                master=self,
                on_submit_command=self._handle_jarvis_command,
                on_voice_requested=self._toggle_continuous_voice,
                on_open_main_ui=self.bring_to_front,
            )
            self._hotkey_mgr = GlobalHotkeyManager()
            # Ctrl+Shift+B -> Börü Spotlight Overlay Aç/Kapat
            self._hotkey_mgr.register("ctrl+shift+b", lambda: self.after(0, self._toggle_jarvis))
            # Ctrl+Shift+J -> Doğrudan Kesintisiz Hands-Free Sesli Sohbeti Başlat/Durdur
            self._hotkey_mgr.register("ctrl+shift+j", lambda: self.after(0, self._toggle_continuous_voice))
            self._hotkey_mgr.start()

            # Arka planda sürekli 'Börü' / 'Hey Börü' sesli uyandırma dinleyicisi
            self._wake_listener = BackgroundWakeWordListener(
                on_wake_word=self._on_background_wake_word,
                recognizer=getattr(self._voice_input, "_recognizer", None),
                microphone=getattr(self._voice_input, "_microphone", None),
            )
            self._wake_listener.start()

            self.log_terminal("✔ Börü (Ctrl+Shift+B, Ctrl+Shift+J) & Sesli Uyandırma ('Börü') aktif.", "success")
        except Exception as e:
            self.log_terminal(f"⚠️ Börü Kısayol veya Uyandırma başlatılamadı: {e}", "info")

    def _toggle_jarvis(self) -> None:
        if getattr(self, "_jarvis_overlay", None):
            self._jarvis_overlay.toggle()

    def _on_background_wake_word(self, remaining_cmd: str) -> None:
        """Kullanıcı arka planda 'Börü' dediğinde tetiklenir."""
        if getattr(self, "_audio_cues", None):
            self._audio_cues.play_wake()
        self.log_terminal(f"🐺 'Börü' uyandırma kelimesi algılandı! Komut: '{remaining_cmd}'", "success")
        self.after(0, self._handle_wake_up_trigger, remaining_cmd)

    def _handle_wake_up_trigger(self, remaining_cmd: str) -> None:
        """Uyandırma gerçekleştiğinde gerekirse overlay'i açar ve sesli diyaloğu başlatır."""
        # Yalnızca ana pencere küçültülmüş veya görünür değilse Spotlight overlay'ini öne çıkar
        if not self.winfo_viewable() and getattr(self, "_jarvis_overlay", None):
            self._jarvis_overlay.show()
            self._jarvis_overlay.set_mic_active(True)

        self.mic_button.configure(fg_color="#e53e3e", text="🛑")

        if not remaining_cmd:
            def _greet_and_listen():
                self._voice_output.speak("Dinliyorum, buyrun!", async_mode=False, force=True)
                if getattr(self, "_continuous_voice", None):
                    self._continuous_voice.start()

            threading.Thread(target=_greet_and_listen, daemon=True).start()
        else:
            def _execute_and_listen():
                reply = self._handle_continuous_voice_speech(remaining_cmd)
                if reply:
                    self._voice_output.speak(reply, async_mode=False, force=True)
                if getattr(self, "_continuous_voice", None):
                    self._continuous_voice.start()

            threading.Thread(target=_execute_and_listen, daemon=True).start()

    def _toggle_continuous_voice(self) -> None:
        """Börü Hands-Free Kesintisiz Sesli Sohbet döngüsünü başlatır veya durdurur."""
        if not getattr(self, "_continuous_voice", None):
            return

        if self._continuous_voice.is_active:
            self._continuous_voice.stop()
            self.mic_button.configure(fg_color="#2b6cb0", text="🎙️")
            if getattr(self, "_jarvis_overlay", None):
                self._jarvis_overlay.set_mic_active(False)
            if getattr(self, "_wake_listener", None):
                self._wake_listener.resume()
            self.log_terminal("🛑 Kesintisiz sesli sohbet sonlandırıldı.", "info")
        else:
            if getattr(self, "_audio_cues", None):
                self._audio_cues.play_wake()
            if getattr(self, "_wake_listener", None):
                self._wake_listener.pause()
            self.mic_button.configure(fg_color="#e53e3e", text="🛑")
            if getattr(self, "_jarvis_overlay", None):
                if not self.winfo_viewable():
                    self._jarvis_overlay.show()
                self._jarvis_overlay.set_mic_active(True)
            self._continuous_voice.start()
            self.log_terminal("🎙️ Kesintisiz Hands-Free sesli sohbet başlatıldı.", "success")

    def _handle_continuous_voice_speech(self, text: str) -> str:
        """Kesintisiz sesli diyalogdan gelen kullanıcı cümlesini çözer ve ekrana/overlay'e basar."""
        self.log_terminal(f"❯ [SESLE SOHBET]: {text}", "cmd")
        self._queue_message("👤 Sen (Sesli)", text)
        if getattr(self, "_jarvis_overlay", None):
            self.after(0, lambda: self._jarvis_overlay.set_input_text(text))

        try:
            reply = self._assistant.reply(text)
            self._queue_message("🐺 Börü", reply)
            if getattr(self, "_jarvis_overlay", None):
                self.after(0, lambda: self._jarvis_overlay.show_result(reply, False))
            return reply
        except Exception as err:
            err_msg = f"Yanıt üretilemedi: {err}"
            self.log_terminal(f"❌ Sesli yanıt hatası: {err}", "error")
            return err_msg

    def _on_voice_status_change(self, text: str, color: str) -> None:
        if getattr(self, "_jarvis_overlay", None):
            self.after(0, lambda: self._jarvis_overlay.set_status(text, color))
        self.after(0, lambda: self.live_indicator.configure(text=text, text_color=color))

        t_low = text.lower()
        if hasattr(self, "visualizer"):
            if "dinliyor" in t_low:
                self.after(0, lambda: self.visualizer.set_mode("listening"))
            elif "konuşuyor" in t_low:
                self.after(0, lambda: self.visualizer.set_mode("speaking"))
            elif "düşünüyor" in t_low or "işleniyor" in t_low:
                self.after(0, lambda: self.visualizer.set_mode("thinking"))
            else:
                self.after(0, lambda: self.visualizer.set_mode("idle"))

    def _on_voice_dialogue_ended(self) -> None:
        self.after(0, lambda: self.mic_button.configure(fg_color="#2b6cb0", text="🎙️"))
        if getattr(self, "_jarvis_overlay", None):
            self.after(0, lambda: self._jarvis_overlay.set_mic_active(False))
            self.after(0, lambda: self._jarvis_overlay.set_status("🟢 Hazır", "#48bb78"))
            # Eğer ana pencere küçültülmüş/gizliyse overlay'i 1.5 sn sonra geri gizle
            if not self.winfo_viewable():
                self.after(1500, self._jarvis_overlay.hide)
        self.after(0, lambda: self.live_indicator.configure(text="🟢 Çevrimiçi & Hazır", text_color="#48bb78"))
        if hasattr(self, "visualizer"):
            self.after(0, lambda: self.visualizer.set_mode("idle"))
        if getattr(self, "_wake_listener", None):
            self._wake_listener.resume()

    def _handle_jarvis_command(self, cmd: str) -> str:
        """Börü Overlay üzerinden klavyeyle gönderilen komutları yürütür."""
        self.log_terminal(f"❯ [BÖRÜ]: {cmd}", "cmd")
        self._queue_message("👤 Sen (Börü)", cmd)
        try:
            reply = self._assistant.reply(cmd)
            self._queue_message("🐺 Börü", reply)
            if self._voice_output.enabled and reply:
                self._voice_output.speak(reply)
            return reply
        except Exception as err:
            self.log_terminal(f"❌ Börü komut hatası: {err}", "error")
            raise err

    def bring_to_front(self) -> None:
        """Ana pencereyi masaüstünde tüm pencerelerin önüne getirir."""
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after(100, lambda: self.attributes("-topmost", False))
        self.focus_force()

    def _setup_system_tray(self) -> None:
        """Sistem tepsisi (System Tray) ikonunu başlatır."""
        try:
            from boru.tray import BoruSystemTray
            self._tray = BoruSystemTray(
                on_open=lambda: self.after(0, self.bring_to_front),
                on_voice=lambda: self.after(0, self._toggle_continuous_voice),
                on_spotlight=lambda: self.after(0, self._toggle_jarvis),
                on_exit=lambda: self.after(0, self._full_exit),
            )
            self._tray.start()
        except Exception as e:
            self.log_terminal(f"⚠️ Sistem tepsisi başlatılamadı: {e}", "info")

    def _on_close(self) -> None:
        """Pencere kapatıldığında arka plana küçülür ve saatin yanında çalışmaya devam eder."""
        if getattr(self, "_tray", None) and self._tray.is_running:
            self.withdraw()
            self._tray.notify(
                "🐺 Börü Arka Planda Aktif",
                "Börü saatin yanında çalışmaya devam ediyor. 'Börü' diyerek veya Ctrl+Shift+B ile açabilirsiniz.",
            )
        else:
            self._full_exit()

    def _full_exit(self) -> None:
        """Uygulamayı ve tüm arka plan dinleyicilerini tamamen sonlandırır."""
        if getattr(self, "_tray", None):
            self._tray.stop()
        if getattr(self, "_continuous_voice", None):
            self._continuous_voice.stop()
        if getattr(self, "_wake_listener", None):
            self._wake_listener.stop()
        if getattr(self, "_hotkey_mgr", None):
            self._hotkey_mgr.stop()
        self.destroy()
        import os
        os._exit(0)

