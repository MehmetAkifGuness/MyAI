"""Next-Generation 2026 Modern Desktop UI for Börü.

Built with Microsoft Edge WebView2, glassmorphism, multi-tab navigation,
interactive quick action gallery, file and code workspace, live hardware monitor,
and a seamless Python-to-JavaScript bridge.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

import webview

logger = logging.getLogger(__name__)


class BoruModernApi:
    """Python-to-JavaScript köprüsü.

    Frontend'den çağrılan tüm komutlar, asistan yanıtları, donanım metrikleri,
    dosya okuma ve terminal operasyonları bu sınıf üzerinden yürütülür.
    """

    def __init__(
        self,
        assistant: Any,
        project_root: Path | None = None,
        on_voice_toggle: Optional[Callable[[], bool]] = None,
        on_open_spotlight: Optional[Callable[[], None]] = None,
    ):
        self._assistant = assistant
        self._project_root = (project_root or Path(".")).resolve()
        self._on_voice_toggle = on_voice_toggle
        self._on_open_spotlight = on_open_spotlight
        self._window: Optional[webview.Window] = None

    def set_window(self, window: webview.Window) -> None:
        self._window = window

    def send_message(self, message: str) -> dict[str, Any]:
        """Kullanıcının gönderdiği metni asistana iletir ve yanıtı döner."""
        msg = message.strip()
        if not msg:
            return {"status": "error", "reply": "Boş mesaj gönderilemez."}

        try:
            reply = self._assistant.reply(msg)
            return {"status": "success", "reply": reply}
        except Exception as e:
            logger.error(f"Mesaj işleme hatası: {e}")
            return {"status": "error", "reply": f"Hata oluştu: {e}"}

    def reset_conversation(self) -> dict[str, str]:
        try:
            self._assistant.reset_conversation()
            return {"status": "success", "message": "Konuşma geçmişi temizlendi."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_system_metrics(self) -> dict[str, Any]:
        """RAM, CPU ve Pil durumunu canlı döndürür."""
        data: dict[str, Any] = {
            "ram_percent": 0,
            "ram_used_gb": 0.0,
            "ram_total_gb": 0.0,
            "battery_percent": None,
            "battery_plugged": True,
            "uptime_str": "Aktif",
        }
        try:
            import psutil
            mem = psutil.virtual_memory()
            data["ram_percent"] = round(mem.percent, 1)
            data["ram_used_gb"] = round(mem.used / (1024**3), 1)
            data["ram_total_gb"] = round(mem.total / (1024**3), 1)

            batt = psutil.sensors_battery()
            if batt:
                data["battery_percent"] = int(batt.percent)
                data["battery_plugged"] = bool(batt.power_plugged)
        except Exception:
            pass
        return data

    def get_project_files(self) -> list[dict[str, str]]:
        """Proje kökündeki dosyaları listeler."""
        files_list = []
        try:
            for root, dirs, files in os.walk(self._project_root):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__" and d != "repositories"]
                rel_dir = os.path.relpath(root, self._project_root)
                for f in files:
                    if f.endswith((".py", ".json", ".md", ".txt", ".toml", ".yaml", ".yml", ".html", ".css", ".js")):
                        rel_path = f if rel_dir == "." else os.path.join(rel_dir, f).replace("\\", "/")
                        files_list.append({"path": rel_path, "name": f})
            files_list.sort(key=lambda x: x["path"])
        except Exception as e:
            logger.error(f"Dosya listeleme hatası: {e}")
        return files_list[:120]

    def read_file_content(self, rel_path: str) -> dict[str, Any]:
        """Seçilen dosyanın içeriğini okur."""
        try:
            safe_path = (self._project_root / rel_path).resolve()
            if not str(safe_path).startswith(str(self._project_root)):
                return {"status": "error", "content": "Güvenlik hatası: Yetkisiz erişim."}
            if not safe_path.exists():
                return {"status": "error", "content": "Dosya bulunamadı."}

            text = safe_path.read_text(encoding="utf-8", errors="replace")
            return {"status": "success", "content": text, "path": rel_path}
        except Exception as e:
            return {"status": "error", "content": f"Dosya okunamadı: {e}"}

    def run_terminal_command(self, cmd: str) -> dict[str, Any]:
        """Kullanıcının terminal sekmesinden verdiği komutu çalıştırır."""
        c = cmd.strip()
        if not c:
            return {"status": "error", "output": "Boş komut."}

        try:
            proc = subprocess.run(
                c,
                shell=True,
                cwd=str(self._project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=30,
            )
            return {
                "status": "success" if proc.returncode == 0 else "failed",
                "returncode": proc.returncode,
                "output": proc.stdout or "(Çıktı üretilmedi)",
            }
        except subprocess.TimeoutExpired:
            return {"status": "error", "returncode": -1, "output": "Komut 30 saniye içinde zaman aşımına uğradı."}
        except Exception as e:
            return {"status": "error", "returncode": -1, "output": f"Komut hatası: {e}"}

    def trigger_spotlight(self) -> dict[str, str]:
        if self._on_open_spotlight:
            self._on_open_spotlight()
            return {"status": "success"}
        return {"status": "not_available"}

    def toggle_voice(self) -> dict[str, Any]:
        if self._on_voice_toggle:
            active = self._on_voice_toggle()
            return {"status": "success", "active": active}
        return {"status": "not_available", "active": False}


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="tr" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Börü AI — Ultra-Modern Desktop</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
    
    :root {
      --bg-base: #07090E;
      --bg-sidebar: #0B0E17;
      --bg-surface: #101422;
      --bg-surface-hover: #161C30;
      --bg-card: #13182A;
      --border-subtle: #1E253A;
      --border-accent: #38BDF8;
      --accent-cyan: #38BDF8;
      --accent-indigo: #6366F1;
      --accent-emerald: #10B981;
      --accent-rose: #F43F5E;
      --accent-amber: #F59E0B;
      --text-main: #F8FAFC;
      --text-muted: #94A3B8;
      --text-dim: #64748B;
    }

    body {
      background-color: var(--bg-base);
      color: var(--text-main);
      display: flex;
      height: 100vh;
      overflow: hidden;
      user-select: none;
    }

    #sidebar-dock {
      width: 72px;
      background: var(--bg-sidebar);
      border-right: 1px solid var(--border-subtle);
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 16px 0;
      gap: 14px;
      flex-shrink: 0;
      z-index: 20;
    }

    .brand-logo {
      width: 46px;
      height: 46px;
      border-radius: 14px;
      background: linear-gradient(135deg, #1E1B4B 0%, #312E81 100%);
      border: 1px solid #4F46E5;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 24px;
      box-shadow: 0 0 16px rgba(99, 102, 241, 0.35);
      cursor: pointer;
      margin-bottom: 8px;
    }

    .nav-btn {
      width: 48px;
      height: 48px;
      border-radius: 14px;
      background: transparent;
      border: none;
      color: var(--text-dim);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 3px;
      cursor: pointer;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
      position: relative;
    }

    .nav-btn svg { width: 22px; height: 22px; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
    .nav-btn span { font-size: 9px; font-weight: 600; letter-spacing: 0.2px; }

    .nav-btn:hover {
      background: var(--bg-surface-hover);
      color: var(--accent-cyan);
      transform: translateY(-1px);
    }

    .nav-btn.active {
      background: #1E2540;
      color: var(--accent-cyan);
      box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.4);
    }

    .nav-btn.active::before {
      content: "";
      position: absolute;
      left: -12px;
      width: 4px;
      height: 24px;
      border-radius: 0 4px 4px 0;
      background: var(--accent-cyan);
      box-shadow: 0 0 8px var(--accent-cyan);
    }

    .dock-spacer { flex: 1; }

    .user-profile-badge {
      width: 42px;
      height: 42px;
      border-radius: 50%;
      background: #1E293B;
      border: 1.5px solid #334155;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 18px;
      position: relative;
      cursor: pointer;
    }

    .online-pulse {
      position: absolute;
      bottom: 0;
      right: 0;
      width: 11px;
      height: 11px;
      border-radius: 50%;
      background: #10B981;
      border: 2px solid var(--bg-sidebar);
    }

    #main-viewport {
      flex: 1;
      display: flex;
      flex-direction: column;
      position: relative;
      overflow: hidden;
      background: radial-gradient(circle at 50% 0%, #0F1626 0%, #07090E 75%);
    }

    #top-bar {
      height: 56px;
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 24px;
      background: rgba(11, 14, 23, 0.7);
      backdrop-filter: blur(12px);
      flex-shrink: 0;
    }

    .top-left { display: flex; align-items: center; gap: 12px; }
    .top-title { font-size: 15px; font-weight: 700; letter-spacing: 0.5px; }
    .top-badge {
      font-size: 11px;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 6px;
      background: rgba(16, 185, 129, 0.15);
      color: var(--accent-emerald);
      border: 1px solid rgba(16, 185, 129, 0.3);
    }

    .top-right { display: flex; align-items: center; gap: 10px; }
    .action-btn {
      padding: 6px 14px;
      border-radius: 10px;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      color: var(--text-muted);
      font-size: 12px;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 6px;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .action-btn:hover {
      background: var(--bg-surface-hover);
      color: var(--text-main);
      border-color: #334155;
    }

    .tab-page {
      flex: 1;
      display: none;
      flex-direction: column;
      overflow: hidden;
      position: relative;
    }
    .tab-page.active { display: flex; }

    #chat-scroll {
      flex: 1;
      overflow-y: auto;
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 16px;
      scroll-behavior: smooth;
    }

    #welcome-hero {
      max-width: 680px;
      margin: 30px auto 10px auto;
      text-align: center;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 16px;
    }
    .hero-wolf { font-size: 48px; filter: drop-shadow(0 0 20px rgba(56, 189, 248, 0.4)); }
    .hero-title { font-size: 26px; font-weight: 800; letter-spacing: -0.5px; }
    .hero-sub { font-size: 14px; color: var(--text-muted); max-width: 480px; line-height: 1.5; }

    .hero-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 12px;
      width: 100%;
      margin-top: 14px;
    }
    .hero-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 14px;
      padding: 14px 16px;
      text-align: left;
      cursor: pointer;
      transition: all 0.2s ease;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .hero-card:hover {
      background: var(--bg-surface-hover);
      border-color: var(--accent-cyan);
      transform: translateY(-2px);
      box-shadow: 0 8px 20px rgba(0,0,0,0.3);
    }
    .hero-card h4 { font-size: 13px; font-weight: 700; color: var(--text-main); display: flex; align-items: center; gap: 6px; }
    .hero-card p { font-size: 11px; color: var(--text-dim); }

    .msg-row { display: flex; width: 100%; }
    .msg-row.user { justify-content: flex-end; }
    .msg-row.bot { justify-content: flex-start; }

    .msg-bubble {
      max-width: 78%;
      border-radius: 18px;
      padding: 14px 18px;
      font-size: 14px;
      line-height: 1.6;
      user-select: text;
      position: relative;
    }

    .msg-row.user .msg-bubble {
      background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
      border: 1px solid #334155;
      color: #F8FAFC;
      border-bottom-right-radius: 4px;
    }

    .msg-row.bot .msg-bubble {
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      color: #F1F5F9;
      border-bottom-left-radius: 4px;
      box-shadow: 0 4px 16px rgba(0,0,0,0.2);
    }

    .msg-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 6px;
      font-size: 11px;
      font-weight: 700;
    }
    .msg-row.user .msg-header { color: #818CF8; }
    .msg-row.bot .msg-header { color: var(--accent-cyan); }

    .copy-msg-btn {
      background: transparent;
      border: 1px solid #334155;
      color: var(--text-dim);
      font-size: 10px;
      padding: 2px 8px;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.15s;
    }
    .copy-msg-btn:hover { background: #1E293B; color: #fff; }

    .code-block {
      background: #06090F;
      border: 1px solid #1E253A;
      border-radius: 10px;
      padding: 12px;
      margin-top: 8px;
      font-family: "Consolas", monospace;
      font-size: 12px;
      overflow-x: auto;
      white-space: pre-wrap;
    }
    .diff-add { color: #10B981; background: rgba(16, 185, 129, 0.1); display: block; }
    .diff-sub { color: #F43F5E; background: rgba(244, 63, 94, 0.1); display: block; }
    .diff-hdr { color: #38BDF8; display: block; font-weight: bold; }

    #input-dock-container {
      padding: 0 24px 20px 24px;
      flex-shrink: 0;
    }

    .floating-dock {
      background: rgba(16, 20, 34, 0.85);
      backdrop-filter: blur(16px);
      border: 1.5px solid var(--border-subtle);
      border-radius: 20px;
      padding: 8px 12px 8px 16px;
      display: flex;
      align-items: center;
      gap: 12px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
      transition: border-color 0.2s;
    }
    .floating-dock:focus-within {
      border-color: var(--accent-cyan);
      box-shadow: 0 10px 30px rgba(56, 189, 248, 0.15);
    }

    .mic-btn-circle {
      width: 40px;
      height: 40px;
      border-radius: 50%;
      background: #0284C7;
      border: none;
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.2s;
      flex-shrink: 0;
    }
    .mic-btn-circle:hover { background: #0369A1; transform: scale(1.05); }
    .mic-btn-circle.active { background: #EF4444; }

    #chat-input {
      flex: 1;
      background: transparent;
      border: none;
      outline: none;
      color: #fff;
      font-size: 14px;
    }
    #chat-input::placeholder { color: var(--text-dim); }

    .send-btn-pill {
      background: linear-gradient(135deg, #6366F1 0%, #4F46E5 100%);
      border: none;
      border-radius: 12px;
      padding: 10px 18px;
      color: #fff;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s;
      flex-shrink: 0;
    }
    .send-btn-pill:hover { opacity: 0.9; transform: translateY(-1px); }

    .tools-gallery {
      padding: 30px;
      overflow-y: auto;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 16px;
    }
    .tool-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 16px;
      padding: 20px;
      cursor: pointer;
      transition: all 0.2s ease;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .tool-card:hover {
      background: var(--bg-surface-hover);
      border-color: var(--accent-indigo);
      transform: translateY(-3px);
      box-shadow: 0 12px 28px rgba(0,0,0,0.3);
    }
    .tool-icon { font-size: 28px; margin-bottom: 4px; }
    .tool-name { font-size: 15px; font-weight: 700; }
    .tool-desc { font-size: 12px; color: var(--text-muted); line-height: 1.5; }

    #explorer-view {
      display: flex;
      flex: 1;
      height: 100%;
      overflow: hidden;
    }
    #file-sidebar {
      width: 260px;
      background: var(--bg-sidebar);
      border-right: 1px solid var(--border-subtle);
      display: flex;
      flex-direction: column;
    }
    .file-search-bar { padding: 12px; border-bottom: 1px solid var(--border-subtle); }
    .file-search-bar input {
      width: 100%;
      background: #111827;
      border: 1px solid #1E293B;
      padding: 8px 12px;
      border-radius: 8px;
      color: #fff;
      font-size: 12px;
      outline: none;
    }
    #file-list { flex: 1; overflow-y: auto; padding: 6px; }
    .file-item {
      padding: 8px 12px;
      border-radius: 8px;
      font-size: 12px;
      font-family: monospace;
      color: var(--text-muted);
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      transition: all 0.15s;
    }
    .file-item:hover { background: var(--bg-surface-hover); color: var(--text-main); }
    .file-item.active { background: #1E2540; color: var(--accent-cyan); font-weight: bold; }

    #code-viewer {
      flex: 1;
      background: #090D16;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .code-viewer-header {
      padding: 10px 16px;
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 12px;
      font-family: monospace;
      color: var(--text-dim);
    }
    #code-pre {
      flex: 1;
      margin: 0;
      padding: 16px;
      overflow: auto;
      font-family: "Consolas", monospace;
      font-size: 13px;
      line-height: 1.6;
      color: #E2E8F0;
    }

    .sentinel-view {
      padding: 30px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 24px;
      max-width: 800px;
      margin: 0 auto;
      width: 100%;
    }
    .metrics-row {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 16px;
    }
    .metric-gauge-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 18px;
      padding: 20px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .metric-gauge-card h3 { font-size: 14px; font-weight: 700; color: var(--text-muted); }
    .gauge-val { font-size: 32px; font-weight: 800; color: var(--accent-cyan); }
    .gauge-sub { font-size: 12px; color: var(--text-dim); }

    .sentinel-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 18px;
      padding: 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .sentinel-info h4 { font-size: 15px; font-weight: 700; margin-bottom: 4px; }
    .sentinel-info p { font-size: 12px; color: var(--text-muted); }

    .terminal-view {
      flex: 1;
      display: flex;
      flex-direction: column;
      background: #06090F;
      padding: 16px;
      font-family: "Consolas", monospace;
    }
    #term-logs {
      flex: 1;
      overflow-y: auto;
      white-space: pre-wrap;
      font-size: 12px;
      line-height: 1.5;
      color: #94A3B8;
    }
    .term-input-row {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 10px;
      border-top: 1px solid #1E253A;
      padding-top: 10px;
    }
    .term-prompt { color: var(--accent-cyan); font-weight: bold; }
    #term-input {
      flex: 1;
      background: transparent;
      border: none;
      outline: none;
      color: #fff;
      font-family: inherit;
      font-size: 13px;
    }
  </style>
</head>
<body>

  <div id="sidebar-dock">
    <div class="brand-logo" title="Börü AI" onclick="switchTab('chat')">🐺</div>

    <button class="nav-btn active" id="btn-chat" onclick="switchTab('chat')">
      <svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
      <span>Sohbet</span>
    </button>

    <button class="nav-btn" id="btn-tools" onclick="switchTab('tools')">
      <svg viewBox="0 0 24 24"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>
      <span>Eylemler</span>
    </button>

    <button class="nav-btn" id="btn-explorer" onclick="switchTab('explorer')">
      <svg viewBox="0 0 24 24"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
      <span>Gezgin</span>
    </button>

    <button class="nav-btn" id="btn-sentinel" onclick="switchTab('sentinel')">
      <svg viewBox="0 0 24 24"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
      <span>Bekçi</span>
    </button>

    <button class="nav-btn" id="btn-terminal" onclick="switchTab('terminal')">
      <svg viewBox="0 0 24 24"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg>
      <span>Terminal</span>
    </button>

    <div class="dock-spacer"></div>

    <div class="user-profile-badge" title="Mehmet Akif (Çevrimiçi)">
      <span>👤</span>
      <div class="online-pulse"></div>
    </div>
  </div>

  <div id="main-viewport">
    
    <div id="top-bar">
      <div class="top-left">
        <span class="top-title">BÖRÜ AI DESKTOP</span>
        <span class="top-badge">V14.0 PRO</span>
      </div>
      <div class="top-right">
        <button class="action-btn" onclick="openSpotlight()">⚡ Spotlight (Ctrl+Shift+B)</button>
        <button class="action-btn" onclick="resetChat()">🧹 Sohbeti Temizle</button>
      </div>
    </div>

    <div class="tab-page active" id="tab-chat">
      <div id="chat-scroll">
        <div id="welcome-hero">
          <div class="hero-wolf">🐺</div>
          <h1 class="hero-title">Börü Yerel Yapay Zekâ</h1>
          <p class="hero-sub">Yerel modellerle çalışan, otonom dosya yönetimi, web araştırması ve proaktif bekçi özelliklerine sahip kişisel asistanınız.</p>
          
          <div class="hero-grid">
            <div class="hero-card" onclick="runPrompt('bana brifing ver')">
              <h4>🌅 Günün Brifingi</h4>
              <p>Bugünkü hava durumu, sistem yükü ve özet bilgileri seslendir.</p>
            </div>
            <div class="hero-card" onclick="runPrompt('masaüstümü düzenle')">
              <h4>📂 Masaüstünü Toparla</h4>
              <p>Masaüstündeki belgeleri, medyaları ve arşivleri klasörlere ayır.</p>
            </div>
            <div class="hero-card" onclick="runPrompt('Atatürk hakkında bilgi ver')">
              <h4>🧠 Canlı Bilgi & Ansiklopedi</h4>
              <p>Vikipedi ve webden anında doğrulanmış hap özetler getir.</p>
            </div>
            <div class="hero-card" onclick="runPrompt('sistem durumunu raporla')">
              <h4>🔋 Donanım & Pil Raporu</h4>
              <p>RAM, batarya durumu ve arka plan bekçisinin raporunu ver.</p>
            </div>
          </div>
        </div>
      </div>

      <div id="input-dock-container">
        <div class="floating-dock">
          <button class="mic-btn-circle" id="mic-btn" onclick="toggleVoice()" title="Sesli Sohbet (Ctrl+Shift+J)">
            <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" fill="none" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="23"></line><line x1="8" y1="23" x2="16" y2="23"></line></svg>
          </button>

          <input type="text" id="chat-input" placeholder="Börü'ye bir soru sorun veya komut verin... (Enter: Gönder)" onkeydown="if(event.key==='Enter') sendMessage()">

          <button class="send-btn-pill" onclick="sendMessage()">
            <span>Gönder</span>
            <span>➤</span>
          </button>
        </div>
      </div>
    </div>

    <div class="tab-page" id="tab-tools">
      <div class="tools-gallery">
        <div class="tool-card" onclick="runPrompt('bana brifing ver')">
          <div class="tool-icon">🌅</div>
          <div class="tool-name">Sabah Brifingi</div>
          <div class="tool-desc">Tarih, saat, batarya, hava durumu ve sistem durumunun tam brifingi.</div>
        </div>
        <div class="tool-card" onclick="runPrompt('masaüstümü düzenle')">
          <div class="tool-icon">📂</div>
          <div class="tool-name">Masaüstünü Düzenle</div>
          <div class="tool-desc">Masaüstündeki gevşek PDF, görsel ve ZIP dosyalarını kategorilere taşır.</div>
        </div>
        <div class="tool-card" onclick="runPrompt('indirilenler boyutu')">
          <div class="tool-icon">📥</div>
          <div class="tool-name">İndirilenler Analizi</div>
          <div class="tool-desc">Downloads klasöründeki toplam alanı ve en büyük 3 dosyayı özetler.</div>
        </div>
        <div class="tool-card" onclick="runPrompt('Albert Einstein kimdir?')">
          <div class="tool-icon">🧠</div>
          <div class="tool-name">Ansiklopedi Sorgusu</div>
          <div class="tool-desc">Tarayıcı açmadan Vikipedi ve DuckDuckGo üzerinden canlı bilgi çeker.</div>
        </div>
        <div class="tool-card" onclick="runPrompt('proaktif uyarıları aç')">
          <div class="tool-icon">🛡️</div>
          <div class="tool-name">Sentinel Bekçi</div>
          <div class="tool-desc">Arka planda düşük pil, aşırı RAM ve mola hatırlatıcılarını yönetir.</div>
        </div>
        <div class="tool-card" onclick="runPrompt('notlarıma ekle: ')">
          <div class="tool-icon">🎙️</div>
          <div class="tool-name">Sesli Not Defteri</div>
          <div class="tool-desc">Anlık sesli notları kaydeder ve dilediğinizde okur.</div>
        </div>
      </div>
    </div>

    <div class="tab-page" id="tab-explorer">
      <div id="explorer-view">
        <div id="file-sidebar">
          <div class="file-search-bar">
            <input type="text" placeholder="Dosyalarda ara..." onkeyup="filterFiles(this.value)">
          </div>
          <div id="file-list"></div>
        </div>
        <div id="code-viewer">
          <div class="code-viewer-header">
            <span id="code-file-name">Bir dosya seçin...</span>
            <button class="action-btn" onclick="copyCurrentCode()">📋 Kopyala</button>
          </div>
          <pre id="code-pre">Sol panelden bir dosyaya tıklayarak içeriğini görüntüleyin.</pre>
        </div>
      </div>
    </div>

    <div class="tab-page" id="tab-sentinel">
      <div class="sentinel-view">
        <div class="metrics-row">
          <div class="metric-gauge-card">
            <h3>BELLEK (RAM) KULLANIMI</h3>
            <div class="gauge-val" id="ram-val">--%</div>
            <div class="gauge-sub" id="ram-sub">Hesaplanıyor...</div>
          </div>
          <div class="metric-gauge-card">
            <h3>PİL SEVİYESİ</h3>
            <div class="gauge-val" id="batt-val">--%</div>
            <div class="gauge-sub" id="batt-sub">Kontrol ediliyor...</div>
          </div>
        </div>

        <div class="sentinel-card">
          <div class="sentinel-info">
            <h4>Kritik Pil Nöbetçisi (<=15%)</h4>
            <p>Pil kritik seviyeye düştüğünde sizi sesli olarak nazikçe uyarır (Spam korumalı).</p>
          </div>
          <span class="top-badge">AKTİF</span>
        </div>

        <div class="sentinel-card">
          <div class="sentinel-info">
            <h4>Aşırı RAM Tüketim Bekçisi (>=92%)</h4>
            <p>Bellek dolduğunda en çok RAM tüketen programı tespit edip sesli ikaz verir.</p>
          </div>
          <span class="top-badge">AKTİF</span>
        </div>

        <div class="sentinel-card">
          <div class="sentinel-info">
            <h4>Ergonomi & Mola Hatırlatıcısı</h4>
            <p>90 dakika aralıksız çalışma sonrasında su molası önerir.</p>
          </div>
          <span class="top-badge">HAZIR</span>
        </div>
      </div>
    </div>

    <div class="tab-page" id="tab-terminal">
      <div class="terminal-view">
        <div id="term-logs">🐺 Börü Terminal & Canlı Konsol Hazır.
Komut çalıştırmak için aşağıya yazıp Enter'a basın (örn: pytest, git status, dir).
</div>
        <div class="term-input-row">
          <span class="term-prompt">❯</span>
          <input type="text" id="term-input" placeholder="Komut yaz..." onkeydown="if(event.key==='Enter') executeTerminal()">
        </div>
      </div>
    </div>

  </div>

  <script>
    let allFiles = [];

    function switchTab(tabId) {
      document.querySelectorAll('.tab-page').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'));

      const targetPage = document.getElementById('tab-' + tabId);
      const targetBtn = document.getElementById('btn-' + tabId);
      if (targetPage) targetPage.classList.add('active');
      if (targetBtn) targetBtn.classList.add('active');

      if (tabId === 'explorer' && allFiles.length === 0) {
        loadFiles();
      } else if (tabId === 'sentinel') {
        updateMetrics();
      }
    }

    function runPrompt(text) {
      switchTab('chat');
      document.getElementById('chat-input').value = text;
      sendMessage();
    }

    async function sendMessage() {
      const input = document.getElementById('chat-input');
      const text = input.value.trim();
      if (!text) return;
      input.value = '';

      const hero = document.getElementById('welcome-hero');
      if (hero) hero.style.display = 'none';

      appendBubble('user', text);
      const scrollArea = document.getElementById('chat-scroll');
      scrollArea.scrollTop = scrollArea.scrollHeight;

      const loadingId = 'loading-' + Date.now();
      appendBubble('bot', '⚡ Börü yanıt hazırlıyor...', loadingId);

      try {
        const res = await window.pywebview.api.send_message(text);
        const loadEl = document.getElementById(loadingId);
        if (loadEl) loadEl.remove();
        appendBubble('bot', res.reply);
      } catch (err) {
        const loadEl = document.getElementById(loadingId);
        if (loadEl) loadEl.remove();
        appendBubble('bot', 'Hata: ' + err);
      }
      scrollArea.scrollTop = scrollArea.scrollHeight;
    }

    function appendBubble(sender, content, customId = null) {
      const scroll = document.getElementById('chat-scroll');
      const row = document.createElement('div');
      row.className = 'msg-row ' + (sender === 'user' ? 'user' : 'bot');
      if (customId) row.id = customId;

      const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const senderLabel = sender === 'user' ? '👤 Siz' : '🐺 Börü';

      let bodyHtml = '';
      if (content.includes('---') && content.includes('+++') && content.includes('@@')) {
        const lines = content.split('\\n');
        let diffHtml = '<div class="code-block">';
        lines.forEach(l => {
          if (l.startsWith('+') && !l.startsWith('+++')) diffHtml += `<span class="diff-add">${escapeHtml(l)}</span>`;
          else if (l.startsWith('-') && !l.startsWith('---')) diffHtml += `<span class="diff-sub">${escapeHtml(l)}</span>`;
          else if (l.startsWith('@@')) diffHtml += `<span class="diff-hdr">${escapeHtml(l)}</span>`;
          else diffHtml += `<span>${escapeHtml(l)}\\n</span>`;
        });
        diffHtml += '</div>';
        bodyHtml = diffHtml;
      } else {
        bodyHtml = escapeHtml(content).replace(/\\n/g, '<br>');
      }

      row.innerHTML = `
        <div class="msg-bubble">
          <div class="msg-header">
            <span>${senderLabel}</span>
            <div style="display:flex;align-items:center;gap:8px;">
              <span>${now}</span>
              ${sender === 'bot' ? '<button class="copy-msg-btn" onclick="copyText(this)">📋 Kopyala</button>' : ''}
            </div>
          </div>
          <div>${bodyHtml}</div>
        </div>
      `;
      scroll.appendChild(row);
      scroll.scrollTop = scroll.scrollHeight;
    }

    function escapeHtml(str) {
      return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function copyText(btn) {
      const bubble = btn.closest('.msg-bubble');
      const text = bubble.querySelector('div:last-child').innerText;
      navigator.clipboard.writeText(text);
      btn.innerText = '✓ Kopyalandı';
      setTimeout(() => btn.innerText = '📋 Kopyala', 2000);
    }

    async function resetChat() {
      await window.pywebview.api.reset_conversation();
      const scroll = document.getElementById('chat-scroll');
      scroll.innerHTML = '';
      const hero = document.getElementById('welcome-hero');
      if (hero) hero.style.display = 'flex';
    function updateMicState(active) {
      const btn = document.getElementById('mic-btn');
      if (btn) {
        if (active) {
          btn.classList.add('active');
        } else {
          btn.classList.remove('active');
        }
      }
    }

    async function toggleVoice() {
      const res = await window.pywebview.api.toggle_voice();
      updateMicState(res.active);
    }

    function openSpotlight() {
      window.pywebview.api.trigger_spotlight();
    }

    async function loadFiles() {
      const files = await window.pywebview.api.get_project_files();
      allFiles = files;
      renderFiles(files);
    }

    function renderFiles(files) {
      const list = document.getElementById('file-list');
      list.innerHTML = '';
      files.forEach(f => {
        const item = document.createElement('div');
        item.className = 'file-item';
        let icon = '📄';
        if (f.path.endsWith('.py')) icon = '🐍';
        else if (f.path.endsWith('.md')) icon = '📝';
        else if (f.path.endsWith('.json')) icon = '⚙️';
        item.innerHTML = `<span>${icon}</span> <span>${f.path}</span>`;
        item.onclick = () => viewFile(f.path, item);
        list.appendChild(item);
      });
    }

    function filterFiles(q) {
      const filtered = allFiles.filter(f => f.path.toLowerCase().includes(q.toLowerCase()));
      renderFiles(filtered);
    }

    async function viewFile(path, el) {
      document.querySelectorAll('.file-item').forEach(i => i.classList.remove('active'));
      if (el) el.classList.add('active');
      document.getElementById('code-file-name').innerText = path;
      const res = await window.pywebview.api.read_file_content(path);
      document.getElementById('code-pre').innerText = res.content || 'Boş dosya.';
    }

    function copyCurrentCode() {
      const text = document.getElementById('code-pre').innerText;
      navigator.clipboard.writeText(text);
      alert('Dosya içeriği panoya kopyalandı!');
    }

    async function updateMetrics() {
      const data = await window.pywebview.api.get_system_metrics();
      document.getElementById('ram-val').innerText = '%' + data.ram_percent;
      document.getElementById('ram-sub').innerText = data.ram_used_gb + ' GB / ' + data.ram_total_gb + ' GB';
      if (data.battery_percent !== null) {
        document.getElementById('batt-val').innerText = '%' + data.battery_percent;
        document.getElementById('batt-sub').innerText = data.battery_plugged ? '⚡ Şarj Oluyor' : '🔋 Pilde Çalışıyor';
      } else {
        document.getElementById('batt-val').innerText = 'AC Güç';
        document.getElementById('batt-sub').innerText = '⚡ Masaüstü / Doğrudan Bağlı';
      }
    }

    async function executeTerminal() {
      const inp = document.getElementById('term-input');
      const cmd = inp.value.trim();
      if (!cmd) return;
      inp.value = '';

      const logs = document.getElementById('term-logs');
      logs.innerText += `\\n❯ ${cmd}\\n`;

      const res = await window.pywebview.api.run_terminal_command(cmd);
      logs.innerText += res.output + '\\n';
      logs.scrollTop = logs.scrollHeight;
    }

    setInterval(updateMetrics, 5000);
  </script>
</body>
</html>
"""


def run_modern_app(
    assistant: Any,
    title: str = "Börü Yerel Yapay Zekâ",
    project_root: Path | None = None,
    on_voice_toggle: Optional[Callable[[], bool]] = None,
    on_open_spotlight: Optional[Callable[[], None]] = None,
    on_window_created: Optional[Callable[[webview.Window], None]] = None,
) -> None:
    """Next-Gen WebView2 Börü masaüstü uygulamasını başlatır."""
    api = BoruModernApi(
        assistant=assistant,
        project_root=project_root,
        on_voice_toggle=on_voice_toggle,
        on_open_spotlight=on_open_spotlight,
    )

    window = webview.create_window(
        title=title,
        html=HTML_TEMPLATE,
        js_api=api,
        width=1120,
        height=780,
        min_size=(900, 640),
        background_color="#07090E",
    )
    api.set_window(window)
    if on_window_created:
        on_window_created(window)
    webview.start(debug=False)
