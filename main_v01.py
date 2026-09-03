import queue
import threading

import customtkinter as ctk

from boru.assistant import AssistantService
from boru.config import AppSettings
from boru.conversation import ConversationHistory
from boru.ollama_model import OllamaChatModel
from boru.prompts import SystemPromptFactory


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class AppUI(ctk.CTk):
    """V0.1 için yalnızca metin sohbetinden sorumlu kullanıcı arayüzü."""

    def __init__(self, assistant: AssistantService):
        super().__init__()
        self._assistant = assistant
        self._ui_events: queue.Queue[tuple[str, tuple]] = queue.Queue()

        self.title("Börü V0.1")
        self.geometry("700x800")

        self._build_ui()
        self._process_ui_events()
        self._write_message(
            "SİSTEM",
            "Börü V0.1 hazır. Bu sürüm yalnızca metin sohbeti kullanır.",
        )

    def _build_ui(self) -> None:
        self.chat_box = ctk.CTkTextbox(
            self,
            state="disabled",
            wrap="word",
            font=("Arial", 14),
        )
        self.chat_box.pack(pady=20, padx=20, fill="both", expand=True)

        input_panel = ctk.CTkFrame(self, fg_color="transparent")
        input_panel.pack(pady=10, padx=20, fill="x")

        self.input_box = ctk.CTkEntry(
            input_panel,
            placeholder_text="Mesajınızı yazın...",
        )
        self.input_box.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.input_box.bind("<Return>", lambda _: self._send_message())

        self.send_button = ctk.CTkButton(
            input_panel,
            text="Gönder",
            width=90,
            command=self._send_message,
        )
        self.send_button.pack(side="left")

        self.reset_button = ctk.CTkButton(
            self,
            text="Konuşmayı Sıfırla",
            width=140,
            command=self._reset_conversation,
        )
        self.reset_button.pack(pady=(0, 15))

    def _process_ui_events(self) -> None:
        while True:
            try:
                event_name, args = self._ui_events.get_nowait()
            except queue.Empty:
                break

            if event_name == "write":
                self._write_message(*args)
            elif event_name == "busy":
                self._set_busy(*args)

        self.after(40, self._process_ui_events)

    def _write_message(self, sender: str, message: str) -> None:
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", f"{sender}: {message}\n\n")
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def _queue_message(self, sender: str, message: str) -> None:
        self._ui_events.put(("write", (sender, message)))

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.send_button.configure(state=state)
        self.reset_button.configure(state=state)
        self.input_box.configure(state=state)

        if not busy:
            self.input_box.focus_set()

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
            answer = self._assistant.reply(message)
            self._queue_message("🗣️ Börü", answer)
        except Exception as error:
            self._queue_message("HATA", f"Yanıt üretilemedi: {error}")
        finally:
            self._queue_busy(False)

    def _reset_conversation(self) -> None:
        self._assistant.reset_conversation()
        self._write_message(
            "SİSTEM",
            "Kısa süreli konuşma geçmişi temizlendi.",
        )


def build_application() -> AppUI:
    settings = AppSettings.from_env()

    chat_model = OllamaChatModel(settings.model_name)

    history = ConversationHistory(
        max_turns=settings.history_turns,
    )

    prompt_factory = SystemPromptFactory(
        settings.assistant_name,
    )

    assistant = AssistantService(
        chat_model=chat_model,
        conversation_history=history,
        prompt_factory=prompt_factory,
    )

    return AppUI(assistant)


if __name__ == "__main__":
    application = build_application()
    application.mainloop()