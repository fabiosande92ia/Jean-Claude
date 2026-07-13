# ui/app.py
import queue
import tkinter as tk
from tkinter.scrolledtext import ScrolledText

STATE_COLORS = {
    "idle": "#888888",
    "loading": "#6a4bc4",
    "recording": "#cc3333",
    "processing": "#cc9900",
    "speaking": "#1a73e8",
}
STATE_LABELS = {
    "idle": "idle",
    "loading": "a carregar modelos…",
    "recording": "a gravar",
    "processing": "a processar",
    "speaking": "a falar",
}
UNKNOWN_COLOR = "#444444"


class App:
    def __init__(self, root, on_press, on_release, ui_queue, on_close, tts_enabled):
        self.root = root
        self.ui_queue = ui_queue
        self.on_close = on_close
        self.tts_enabled = tts_enabled

        root.title("Jean Claude")
        root.geometry("520x600")

        self.state_label = tk.Label(
            root, text=STATE_LABELS["loading"], bg=STATE_COLORS["loading"], fg="white",
            font=("Segoe UI", 12, "bold"), pady=8,
        )
        self.state_label.pack(fill="x")

        self.button = tk.Button(root, text="Numpad -", font=("Segoe UI", 14), height=2)
        self.button.pack(fill="x", padx=8, pady=8)
        self.button.bind("<ButtonPress-1>", lambda e: on_press())
        self.button.bind("<ButtonRelease-1>", lambda e: on_release())

        self.tts_button = tk.Button(root, font=("Segoe UI", 10), command=self._toggle_tts)
        self.tts_button.pack(fill="x", padx=8)
        self._refresh_tts_button()

        self.chat = ScrolledText(root, state="disabled", wrap="word", width=60, height=24)
        self.chat.pack(fill="both", expand=True, padx=8, pady=8)
        self.chat.tag_config("user", foreground="#1a73e8")
        self.chat.tag_config("assistant", foreground="#188038")
        self.chat.tag_config("error", foreground="#d93025")

        root.protocol("WM_DELETE_WINDOW", self._handle_close)
        self._poll()

    def _handle_close(self):
        self.on_close()
        self.root.destroy()

    def _toggle_tts(self):
        if self.tts_enabled.is_set():
            self.tts_enabled.clear()
        else:
            self.tts_enabled.set()
        self._refresh_tts_button()

    def _refresh_tts_button(self):
        on = self.tts_enabled.is_set()
        self.tts_button.config(
            text="Voz: ligada" if on else "Voz: desligada",
            bg="#188038" if on else "#888888", fg="white",
        )

    def _append(self, prefix, text, tag):
        self.chat.config(state="normal")
        self.chat.insert("end", prefix, tag)
        self.chat.insert("end", text + "\n\n")
        self.chat.see("end")
        self.chat.config(state="disabled")

    def _poll(self):
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "state":
                    # .get() e não [] : um estado desconhecido rebentava o _poll inteiro
                    # dentro do callback do Tk e a UI congelava para sempre.
                    self.state_label.config(
                        text=STATE_LABELS.get(payload, str(payload)),
                        bg=STATE_COLORS.get(payload, UNKNOWN_COLOR),
                    )
                elif kind == "user":
                    self._append("Fábio: ", payload, "user")
                elif kind == "assistant":
                    self._append("Jean Claude: ", payload, "assistant")
                elif kind == "error":
                    self._append("[erro] ", payload, "error")
        except queue.Empty:
            pass
        finally:
            self.root.after(50, self._poll)


def launch(on_press, on_release, ui_queue, on_close, tts_enabled):
    root = tk.Tk()
    App(root, on_press, on_release, ui_queue, on_close, tts_enabled)
    root.mainloop()
