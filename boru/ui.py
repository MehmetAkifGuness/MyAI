import queue
import threading
import time

import customtkinter as ctk

from boru.contracts import (
    AssistantPort,
)


ctk.set_appearance_mode(
    "dark"
)

ctk.set_default_color_theme(
    "blue"
)


class ChatAppUI(
    ctk.CTk
):
    """
    Metin tabanlı Börü masaüstü arayüzü.
    """

    def __init__(
        self,
        assistant: AssistantPort,
        title: str,
        startup_message: str,
    ):
        super().__init__()

        self._assistant = assistant

        self._ui_events: queue.Queue[
            tuple[str, tuple]
        ] = queue.Queue()
        self._busy_started_at: float | None = None
        self._status_after_id: str | None = None

        self.title(
            title
        )

        self.geometry(
            "700x800"
        )

        self._build_ui()

        self._process_ui_events()

        self._write_message(
            "SİSTEM",
            startup_message,
        )

    def _build_ui(
        self,
    ) -> None:
        self.chat_box = (
            ctk.CTkTextbox(
                self,
                state="disabled",
                wrap="word",
                font=(
                    "Arial",
                    14,
                ),
            )
        )

        self.chat_box.pack(
            pady=20,
            padx=20,
            fill="both",
            expand=True,
        )

        input_panel = (
            ctk.CTkFrame(
                self,
                fg_color="transparent",
            )
        )

        input_panel.pack(
            pady=10,
            padx=20,
            fill="x",
        )

        self.input_box = (
            ctk.CTkEntry(
                input_panel,
                placeholder_text=(
                    "Mesajınızı yazın..."
                ),
            )
        )

        self.input_box.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 10),
        )

        self.input_box.bind(
            "<Return>",
            lambda _: (
                self._send_message()
            ),
        )

        self.send_button = (
            ctk.CTkButton(
                input_panel,
                text="Gönder",
                width=90,
                command=(
                    self._send_message
                ),
            )
        )

        self.send_button.pack(
            side="left"
        )

        self.status_label = (
            ctk.CTkLabel(
                self,
                text="Hazır",
                text_color="gray70",
            )
        )

        self.status_label.pack(
            pady=(0, 5)
        )

        self.reset_button = (
            ctk.CTkButton(
                self,
                text=(
                    "Konuşmayı Sıfırla"
                ),
                width=140,
                command=(
                    self
                    ._reset_conversation
                ),
            )
        )

        self.reset_button.pack(
            pady=(0, 15)
        )

    def _process_ui_events(
        self,
    ) -> None:
        while True:
            try:
                (
                    event_name,
                    args,
                ) = (
                    self._ui_events
                    .get_nowait()
                )

            except queue.Empty:
                break

            if event_name == "write":
                self._write_message(
                    *args
                )

            elif event_name == "stream_start":
                self._stream_start(
                    *args
                )

            elif event_name == "stream_chunk":
                self._stream_chunk(
                    *args
                )

            elif event_name == "stream_end":
                self._stream_end()

            elif event_name == "busy":
                self._set_busy(
                    *args
                )

        self.after(
            40,
            self._process_ui_events,
        )

    def _stream_start(
        self,
        sender: str,
    ) -> None:
        self.chat_box.configure(
            state="normal"
        )
        self.chat_box.insert(
            "end",
            f"{sender}: "
        )
        self.chat_box.see(
            "end"
        )
        self.chat_box.configure(
            state="disabled"
        )

    def _stream_chunk(
        self,
        chunk: str,
    ) -> None:
        self.chat_box.configure(
            state="normal"
        )
        self.chat_box.insert(
            "end",
            chunk
        )
        self.chat_box.see(
            "end"
        )
        self.chat_box.configure(
            state="disabled"
        )

    def _stream_end(
        self,
    ) -> None:
        self.chat_box.configure(
            state="normal"
        )
        self.chat_box.insert(
            "end",
            "\n\n"
        )
        self.chat_box.see(
            "end"
        )
        self.chat_box.configure(
            state="disabled"
        )

    def _write_message(
        self,
        sender: str,
        message: str,
    ) -> None:
        self.chat_box.configure(
            state="normal"
        )

        self.chat_box.insert(
            "end",
            (
                f"{sender}: "
                f"{message}\n\n"
            ),
        )

        self.chat_box.see(
            "end"
        )

        self.chat_box.configure(
            state="disabled"
        )

    def _queue_message(
        self,
        sender: str,
        message: str,
    ) -> None:
        self._ui_events.put(
            (
                "write",
                (
                    sender,
                    message,
                ),
            )
        )

    def _set_busy(
        self,
        busy: bool,
    ) -> None:
        state = (
            "disabled"
            if busy
            else "normal"
        )

        self.send_button.configure(
            state=state
        )

        self.reset_button.configure(
            state=state
        )

        self.input_box.configure(
            state=state
        )

        if busy:
            self._busy_started_at = time.monotonic()
            self._update_busy_status()
        else:
            self._busy_started_at = None
            if self._status_after_id is not None:
                self.after_cancel(self._status_after_id)
                self._status_after_id = None
            self.status_label.configure(text="Hazır")

        if not busy:
            self.input_box.focus_set()

    def _update_busy_status(self) -> None:
        if self._busy_started_at is None:
            return
        elapsed = time.monotonic() - self._busy_started_at
        self.status_label.configure(
            text=f"İşleniyor... {elapsed:.1f} sn"
        )
        self._status_after_id = self.after(
            250,
            self._update_busy_status,
        )

    def _queue_busy(
        self,
        busy: bool,
    ) -> None:
        self._ui_events.put(
            (
                "busy",
                (busy,),
            )
        )

    def _send_message(
        self,
    ) -> None:
        message = (
            self.input_box
            .get()
            .strip()
        )

        if not message:
            return

        self.input_box.delete(
            0,
            "end",
        )

        self._write_message(
            "👤 Sen",
            message,
        )

        self._set_busy(
            True
        )

        threading.Thread(
            target=(
                self._generate_reply
            ),
            args=(message,),
            daemon=True,
        ).start()

    def _generate_reply(
        self,
        message: str,
    ) -> None:
        try:
            stream_func = getattr(self._assistant, "reply_stream", None)
            if callable(stream_func):
                self._ui_events.put(("stream_start", ("🗣️ Börü",)))
                for chunk in stream_func(message):
                    self._ui_events.put(("stream_chunk", (chunk,)))
                self._ui_events.put(("stream_end", ()))
            else:
                answer = (
                    self._assistant.reply(
                        message
                    )
                )

                self._queue_message(
                    "🗣️ Börü",
                    answer,
                )

        except Exception as error:
            self._queue_message(
                "HATA",
                (
                    "Yanıt üretilemedi: "
                    f"{error}"
                ),
            )

        finally:
            self._queue_busy(
                False
            )

    def _reset_conversation(
        self,
    ) -> None:
        self._assistant.reset_conversation()

        self._write_message(
            "SİSTEM",
            (
                "Kısa süreli konuşma "
                "geçmişi temizlendi. "
                "Kalıcı profil korunuyor."
            ),
        )
