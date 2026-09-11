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
            return data
        except Exception:
            pass

        # Windows ctypes yerel API fallback (psutil gerektirmeden tam çalışır)
        try:
            import ctypes
            from ctypes import wintypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", wintypes.DWORD),
                    ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_uint64),
                    ("ullAvailPhys", ctypes.c_uint64),
                    ("ullTotalPageFile", ctypes.c_uint64),
                    ("ullAvailPageFile", ctypes.c_uint64),
                    ("ullTotalVirtual", ctypes.c_uint64),
                    ("ullAvailVirtual", ctypes.c_uint64),
                    ("ullAvailExtendedVirtual", ctypes.c_uint64),
                ]

            mem_info = MEMORYSTATUSEX()
            mem_info.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem_info)):
                data["ram_percent"] = int(mem_info.dwMemoryLoad)
                data["ram_total_gb"] = round(mem_info.ullTotalPhys / (1024**3), 1)
                data["ram_used_gb"] = round((mem_info.ullTotalPhys - mem_info.ullAvailPhys) / (1024**3), 1)

            class SYSTEM_POWER_STATUS(ctypes.Structure):
                _fields_ = [
                    ("ACLineStatus", wintypes.BYTE),
                    ("BatteryFlag", wintypes.BYTE),
                    ("BatteryLifePercent", wintypes.BYTE),
                    ("SystemStatusFlag", wintypes.BYTE),
                    ("BatteryLifeTime", wintypes.DWORD),
                    ("BatteryFullLifeTime", wintypes.DWORD),
                ]

            pwr = SYSTEM_POWER_STATUS()
            if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(pwr)):
                if pwr.BatteryLifePercent != 255:
                    data["battery_percent"] = int(pwr.BatteryLifePercent)
                data["battery_plugged"] = (pwr.ACLineStatus == 1)
        except Exception as e:
            logger.debug(f"Yerel donanım metrikleri okuma hatası: {e}")

        return data

    def hide_window(self) -> dict[str, str]:
        if self._window:
            try:
                self._window.hide()
                return {"status": "hidden"}
            except Exception as e:
                return {"status": "error", "message": str(e)}
        return {"status": "no_window"}

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
    .mic-btn-circle.active {
      background: #EF4444 !important;
      box-shadow: 0 0 16px rgba(239, 68, 68, 0.8), 0 0 32px rgba(239, 68, 68, 0.4) !important;
      animation: micPulse 1.2s infinite ease-in-out !important;
    }
    @keyframes micPulse {
      0%, 100% { transform: scale(1); box-shadow: 0 0 12px rgba(239, 68, 68, 0.6); }
      50% { transform: scale(1.08); box-shadow: 0 0 24px rgba(239, 68, 68, 0.95); }
    }

    .voice-status-pill {
      display: none;
      align-items: center;
      gap: 6px;
      padding: 3px 12px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 700;
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid rgba(239, 68, 68, 0.4);
      color: #EF4444;
      letter-spacing: 0.3px;
      animation: micPulse 1.2s infinite ease-in-out;
    }

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
        <div class="voice-status-pill" id="voice-status-pill">🎙️ Dinliyor (Konuşun)...</div>
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

    // Modern pencere içi küresel klavye kısayolları
    document.addEventListener('keydown', function(e) {
      // Ctrl+Shift+J veya Alt+J -> Kesintisiz Sesli Sohbeti Aç/Kapat
      if (((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'J' || e.key === 'j')) || (e.altKey && (e.key === 'J' || e.key === 'j'))) {
        e.preventDefault();
        toggleVoice();
        return;
      }
      // Ctrl+Shift+B veya Alt+B -> Eylemler (Spotlight) Sekmesine Odaklan
      if (((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'B' || e.key === 'b')) || (e.altKey && (e.key === 'B' || e.key === 'b'))) {
        e.preventDefault();
        switchTab('tools');
        return;
      }
      // Escape -> Pencereyi sistem tepsisine gizle
      if (e.key === 'Escape') {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.hide_window) {
          window.pywebview.api.hide_window();
        }
      }
    });

    function switchTab(tabId) {
      if (tabId === 'actions') tabId = 'tools';
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
    }

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

    function updateVoiceStatus(text, color) {
      const pill = document.getElementById('voice-status-pill');
      if (!pill) return;
      if (!text || text.includes('Hazır') || text.includes('Çevrimiçi')) {
        pill.style.display = 'none';
        updateMicState(false);
      } else {
        pill.style.display = 'inline-flex';
        pill.innerText = text;
        pill.style.color = color || '#EF4444';
        pill.style.borderColor = color || '#EF4444';
        if (text.includes('Dinliyor')) {
          updateMicState(true);
        }
      }
    }

    function appendSpeechExchange(userText, botReply) {
      const hero = document.getElementById('welcome-hero');
      if (hero) hero.style.display = 'none';
      appendBubble('user', userText);
      appendBubble('bot', botReply);
      const scrollArea = document.getElementById('chat-scroll');
      if (scrollArea) scrollArea.scrollTop = scrollArea.scrollHeight;
    }

    async function toggleVoice() {
      const res = await window.pywebview.api.toggle_voice();
      if (res && res.active !== undefined) {
        updateMicState(res.active);
      }
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


# ---------------------------------------------------------------------------
# Yüzen Sesli Diyalog Overlay'i — Başlangıç HTML Şablonu
# ---------------------------------------------------------------------------
VOICE_OVERLAY_HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Börü Sesli Diyalog</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #07090E;
      border: 1.5px solid #38BDF8;
      border-radius: 18px;
      overflow: hidden;
      height: 100vh;
      display: flex;
      flex-direction: column;
      color: #E2E8F0;
      user-select: none;
    }
    /* ─── Header ─── */
    .header {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 14px;
      background: rgba(14, 20, 38, 0.85);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid rgba(56, 189, 248, 0.18);
      flex-shrink: 0;
      -webkit-app-region: drag;
    }
    .wolf-icon { font-size: 17px; }
    .app-title {
      font-size: 11px;
      font-weight: 700;
      color: #94A3B8;
      letter-spacing: 0.8px;
      text-transform: uppercase;
      flex: 1;
    }
    .status-pill {
      display: flex;
      align-items: center;
      gap: 5px;
      padding: 3px 10px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 700;
      background: rgba(16, 185, 129, 0.1);
      border: 1px solid rgba(16, 185, 129, 0.3);
      color: #10B981;
      transition: all 0.3s;
      white-space: nowrap;
    }
    .status-pill.active {
      background: rgba(239, 68, 68, 0.15);
      border-color: rgba(239, 68, 68, 0.4);
      color: #EF4444;
      animation: statusPulse 1.2s infinite ease-in-out;
    }
    .status-pill.thinking {
      background: rgba(245, 158, 11, 0.12);
      border-color: rgba(245, 158, 11, 0.35);
      color: #F59E0B;
    }
    @keyframes statusPulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.65; }
    }
    .hdr-btn {
      padding: 4px 10px;
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.08);
      color: #94A3B8;
      font-size: 11px;
      cursor: pointer;
      transition: all 0.15s;
      -webkit-app-region: no-drag;
    }
    .hdr-btn:hover { background: rgba(255, 255, 255, 0.1); color: #E2E8F0; }
    .hdr-btn.close { color: #F87171; border-color: rgba(248, 113, 113, 0.3); }
    .hdr-btn.close:hover { background: rgba(239, 68, 68, 0.15); }

    /* ─── Raycast Command Bar ─── */
    .cmd-bar {
      padding: 8px 14px;
      background: rgba(10, 14, 26, 0.95);
      border-bottom: 1px solid rgba(56, 189, 248, 0.15);
      display: flex;
      align-items: center;
      gap: 8px;
      flex-shrink: 0;
    }
    .cmd-icon { font-size: 14px; color: #38BDF8; opacity: 0.8; }
    .cmd-input {
      flex: 1;
      background: transparent;
      border: none;
      outline: none;
      color: #F1F5F9;
      font-size: 13px;
      font-family: inherit;
    }
    .cmd-input::placeholder { color: #475569; }
    .cmd-run-btn {
      padding: 3px 8px;
      border-radius: 6px;
      background: #0284C7;
      border: none;
      color: white;
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.15s;
    }
    .cmd-run-btn:hover { background: #0369A1; }

    /* ─── Quick Chips ─── */
    .chips {
      display: flex;
      gap: 6px;
      padding: 4px 14px 6px;
      background: rgba(10, 14, 26, 0.95);
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
      overflow-x: auto;
      flex-shrink: 0;
    }
    .chips::-webkit-scrollbar { display: none; }
    .chip {
      padding: 2px 7px;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.08);
      color: #94A3B8;
      font-size: 10px;
      cursor: pointer;
      white-space: nowrap;
      transition: all 0.15s;
    }
    .chip:hover {
      background: rgba(56, 189, 248, 0.12);
      border-color: rgba(56, 189, 248, 0.3);
      color: #38BDF8;
    }

    /* ─── Quick Result Alert ─── */
    .quick-result {
      display: none;
      margin: 8px 14px 0;
      padding: 8px 12px;
      background: rgba(14, 165, 233, 0.08);
      border: 1px solid rgba(56, 189, 248, 0.3);
      border-radius: 8px;
      font-size: 12px;
      line-height: 1.4;
      color: #E0F2FE;
    }

    /* ─── Conversation area ─── */
    .conv {
      flex: 1;
      overflow-y: auto;
      padding: 8px 14px;
      display: flex;
      flex-direction: column;
      gap: 7px;
      scroll-behavior: smooth;
    }
    .conv::-webkit-scrollbar { width: 3px; }
    .conv::-webkit-scrollbar-track { background: transparent; }
    .conv::-webkit-scrollbar-thumb { background: #1E293B; border-radius: 2px; }
    .empty {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 4px;
      height: 100%;
      color: #334155;
      font-size: 11px;
      text-align: center;
    }
    .empty-icon { font-size: 22px; opacity: 0.35; }
    .empty-hint { font-size: 10px; opacity: 0.5; margin-top: 2px; }

    /* ─── Message bubbles ─── */
    .row { display: flex; }
    .row.u { justify-content: flex-end; }
    .row.b { justify-content: flex-start; }
    .bubble {
      max-width: 88%;
      padding: 7px 11px;
      border-radius: 12px;
      font-size: 12px;
      line-height: 1.55;
    }
    .row.u .bubble {
      background: #1A2847;
      border: 1px solid #2D4170;
      color: #C7D7F0;
      border-bottom-right-radius: 3px;
    }
    .row.b .bubble {
      background: #0D1525;
      border: 1px solid #1B2539;
      color: #B8C8DC;
      border-bottom-left-radius: 3px;
    }
    .lbl { font-size: 10px; font-weight: 700; margin-bottom: 3px; }
    .row.u .lbl { color: #818CF8; }
    .row.b .lbl { color: #38BDF8; }

    /* ─── Footer ─── */
    .footer {
      padding: 5px 14px;
      background: rgba(7, 9, 14, 0.7);
      border-top: 1px solid rgba(56, 189, 248, 0.08);
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-shrink: 0;
    }
    .ft-hint { font-size: 10px; color: #1E2D3D; }
    .ft-brand { font-size: 10px; font-weight: 700; letter-spacing: 0.6px; color: #162030; }
  </style>
</head>
<body>
  <div class="header" id="hdr">
    <span class="wolf-icon">🐺</span>
    <span class="app-title">Börü Sesli Diyalog & Raycast</span>
    <div class="status-pill" id="spill">🟢 Hazır</div>
    <button class="hdr-btn" onclick="openMain()">🖥️ Ana</button>
    <button class="hdr-btn close" onclick="doClose()">✕</button>
  </div>

  <div class="cmd-bar">
    <span class="cmd-icon">⚡</span>
    <input type="text" id="cmd-input" class="cmd-input" placeholder="Hızlı komut yazın (örn: =14*5, ara: dolar kuru, ses aç)..." onkeydown="handleCmdKeyDown(event)">
    <button class="cmd-run-btn" onclick="runQuickAction()">Çalıştır</button>
  </div>

  <div class="chips">
    <span class="chip" onclick="applyChip('= 450 * 1.2')">🧮 Hesap</span>
    <span class="chip" onclick="applyChip('ara: güncel haberler')">🌐 Haberler</span>
    <span class="chip" onclick="applyChip('sesi artır')">🔊 Ses Aç</span>
    <span class="chip" onclick="applyChip('not defterini aç')">📝 Not Defteri</span>
    <span class="chip" onclick="applyChip('ram durumu')">📊 RAM</span>
    <span class="chip" onclick="applyChip('masaüstünü göster')">🖥️ Masaüstü</span>
  </div>

  <div id="quick-res" class="quick-result"></div>

  <div class="conv" id="conv">
    <div class="empty" id="empty">
      <div class="empty-icon">🎙️</div>
      <div>Konuşmaya başlayın veya yukarıya hızlı komut yazın</div>
      <div class="empty-hint">Ctrl+Shift+J aç/kapat &nbsp;•&nbsp; Esc kapat &nbsp;•&nbsp; ↵ Çalıştır</div>
    </div>
  </div>

  <div class="footer">
    <span class="ft-hint">Esc kapat &nbsp;•&nbsp; Ctrl+Shift+J toggle &nbsp;•&nbsp; [=] Hesap &nbsp;•&nbsp; [ara:] Web</span>
    <span class="ft-brand">BÖRÜ PRO</span>
  </div>

  <script>
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') { doClose(); return; }
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'J' || e.key === 'j')) {
        e.preventDefault();
        if (window.pywebview && window.pywebview.api) window.pywebview.api.toggle_voice_from_overlay();
      }
    });

    function handleCmdKeyDown(e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        runQuickAction();
      }
    }

    function applyChip(text) {
      const inp = document.getElementById('cmd-input');
      if (inp) {
        inp.value = text;
        inp.focus();
        runQuickAction();
      }
    }

    function runQuickAction() {
      const inp = document.getElementById('cmd-input');
      const val = inp ? inp.value.trim() : '';
      if (!val) return;

      const resBox = document.getElementById('quick-res');
      if (resBox) {
        resBox.style.display = 'block';
        resBox.innerText = '⚡ İşleniyor...';
      }

      if (window.pywebview && window.pywebview.api && window.pywebview.api.execute_quick_action) {
        window.pywebview.api.execute_quick_action(val).then(res => {
          if (resBox) {
            resBox.style.display = 'block';
            resBox.innerText = res.reply || 'Tamamlandı.';
            if (res.status === 'error') {
              resBox.style.borderColor = '#EF4444';
              resBox.style.color = '#FCA5A5';
            } else {
              resBox.style.borderColor = 'rgba(56, 189, 248, 0.4)';
              resBox.style.color = '#E0F2FE';
            }
          }
          addExchange('⚡ ' + val, res.reply || 'Tamamlandı.');
        }).catch(err => {
          if (resBox) {
            resBox.style.display = 'block';
            resBox.innerText = 'Hata: ' + err;
          }
        });
      }
    }

    function updateStatus(text, color) {
      const p = document.getElementById('spill');
      if (!p) return;
      p.innerText = text;
      p.style.setProperty('color', color, '');
      const lower = text.toLowerCase();
      if (lower.includes('hazır') || lower.includes('çevrimiçi')) {
        p.className = 'status-pill';
      } else if (lower.includes('işleniyor') || lower.includes('düşünüyor') || lower.includes('cevap')) {
        p.className = 'status-pill thinking';
      } else {
        p.className = 'status-pill active';
      }
    }

    function addExchange(userText, botReply) {
      const conv = document.getElementById('conv');
      const empty = document.getElementById('empty');
      if (empty) empty.remove();

      const userRow = document.createElement('div');
      userRow.className = 'row u';
      userRow.innerHTML = `<div class="bubble"><div class="lbl">👤 Siz</div>${esc(userText)}</div>`;
      conv.appendChild(userRow);

      if (botReply && botReply.trim()) {
        const botRow = document.createElement('div');
        botRow.className = 'row b';
        botRow.innerHTML = `<div class="bubble"><div class="lbl">🐺 Börü</div>${esc(botReply)}</div>`;
        conv.appendChild(botRow);
      }

      // Keep last 12 bubbles (6 exchanges)
      const rows = conv.querySelectorAll('.row');
      if (rows.length > 12) {
        for (let i = 0; i < rows.length - 12; i++) rows[i].remove();
      }
      conv.scrollTop = conv.scrollHeight;
    }

    function clearConv() {
      const conv = document.getElementById('conv');
      conv.innerHTML = '<div class="empty" id="empty"><div class="empty-icon">🎙️</div><div>Konuşmaya başlayın</div><div class="empty-hint">Ctrl+Shift+J aç/kapat &nbsp;•&nbsp; Esc kapat</div></div>';
    }

    function esc(s) {
      return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g,'<br>');
    }

    function doClose() {
      if (window.pywebview && window.pywebview.api) window.pywebview.api.close_overlay();
    }

    function openMain() {
      if (window.pywebview && window.pywebview.api) window.pywebview.api.open_main_window();
    }
  </script>
</body>
</html>
"""


class VoiceOverlayApi:
    """Yüzen sesli diyalog ve Raycast hızlı eylemler overlay penceresi için Python-JS köprüsü."""

    def __init__(
        self,
        on_toggle_voice: Optional[Callable[[], None]] = None,
        on_open_main: Optional[Callable[[], None]] = None,
        on_close: Optional[Callable[[], None]] = None,
        on_execute_command: Optional[Callable[[str], str]] = None,
    ):
        self._on_toggle_voice = on_toggle_voice
        self._on_open_main = on_open_main
        self._on_close = on_close
        self._on_execute_command = on_execute_command
        self._window: Optional[webview.Window] = None

    def set_window(self, window: webview.Window) -> None:
        self._window = window

    def close_overlay(self) -> None:
        """Overlay penceresini gizler (sesi durdurmaz)."""
        if self._on_close:
            self._on_close()

    def open_main_window(self) -> None:
        """Ana pencereyi öne getirir ve overlay'i gizler."""
        if self._on_open_main:
            self._on_open_main()

    def toggle_voice_from_overlay(self) -> None:
        """Overlay içinden Ctrl+Shift+J kısayolu: sesi toggle eder."""
        if self._on_toggle_voice:
            self._on_toggle_voice()

    def execute_quick_action(self, cmd: str) -> dict[str, Any]:
        """Raycast komut çubuğundan gelen hızlı hesaplama veya sistem komutunu yürütür."""
        text = cmd.strip()
        if not text:
            return {"status": "error", "reply": "Lütfen bir komut girin."}

        # 1. Hızlı Hesaplama: "calc: 15 * 4" veya "= 15 * 4"
        if text.startswith(("=", "calc:", "hesap:")):
            expr = re.sub(r"^(?:=|calc:|hesap:)\s*", "", text).strip()
            try:
                from boru.tools.builtins.calculator import CalculatorTool
                calc = CalculatorTool()
                res = calc.execute({"expression": expr})
                return {"status": "success", "reply": f"= {res.output}"}
            except Exception as e:
                return {"status": "error", "reply": f"Hesaplama hatası: {e}"}

        # 2. Canlı Web Araması: "web: dolar kuru" veya "ara: haberler"
        if text.startswith(("web:", "ara:", "google:")):
            query = re.sub(r"^(?:web:|ara:|google:)\s*", "", text).strip()
            try:
                from boru.tools.web_search import search_web_live
                ok, web_res = search_web_live(query)
                return {"status": "success" if ok else "error", "reply": web_res}
            except Exception as e:
                return {"status": "error", "reply": f"Web arama hatası: {e}"}

        # 3. Sistem & OS Araçları (System Tools / OS Agent)
        try:
            from boru.tools.system_tools import execute_system_command
            sys_res = execute_system_command(text)
            if sys_res:
                return {"status": "success", "reply": sys_res}
        except Exception as e:
            logger.debug(f"Hızlı sistem eylemi hatası: {e}")

        # 4. Asistan Yapay Zeka Yanıtı (Custom Callback)
        if self._on_execute_command:
            try:
                reply = self._on_execute_command(text)
                return {"status": "success", "reply": reply}
            except Exception as err:
                return {"status": "error", "reply": f"Hata: {err}"}

        return {"status": "success", "reply": f"Komut işlendi: {text}"}


def run_modern_app(
    assistant: Any,
    title: str = "Börü Yerel Yapay Zekâ",
    project_root: Path | None = None,
    on_voice_toggle: Optional[Callable[[], bool]] = None,
    on_open_spotlight: Optional[Callable[[], None]] = None,
    on_window_created: Optional[Callable[[webview.Window], None]] = None,
    on_closing: Optional[Callable[[], bool]] = None,
    on_overlay_window_created: Optional[Callable[[webview.Window, "VoiceOverlayApi"], None]] = None,
    hidden: bool = False,
) -> None:
    """Next-Gen WebView2 Börü masaüstü uygulamasını başlatır.

    İsteğe bağlı olarak yüzen sesli diyalog overlay'i de oluşturur.
    on_overlay_window_created(overlay_window, overlay_api) callback'i
    ile dış kod overlay'e JS çağrısı yapabilir, göster/gizle kontrolü sağlar.
    hidden=True olduğunda ana pencere açılışta gizli (tepsi modu) başlar.
    """
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
        hidden=hidden,
    )
    api.set_window(window)
    if on_closing:
        window.events.closing += on_closing
    if on_window_created:
        on_window_created(window)

    # ── Yüzen sesli overlay (opsiyonel) ────────────────────────────────────
    if on_overlay_window_created is not None:
        try:
            import ctypes as _ctypes
            _sw = _ctypes.windll.user32.GetSystemMetrics(0)
        except Exception:
            _sw = 1920
        _ow = 720
        _ox = max(0, (_sw - _ow) // 2)
        _oy = 68

        overlay_api = VoiceOverlayApi()  # callbacks wired by caller via on_overlay_window_created
        overlay_win = webview.create_window(
            title="Börü Sesli Diyalog & Raycast",
            html=VOICE_OVERLAY_HTML,
            js_api=overlay_api,
            width=_ow,
            height=340,
            x=_ox,
            y=_oy,
            frameless=True,
            on_top=True,
            hidden=True,
            easy_drag=True,
            shadow=True,
            resizable=False,
            background_color="#07090E",
        )
        overlay_api.set_window(overlay_win)
        on_overlay_window_created(overlay_win, overlay_api)

    webview.start(debug=False)
