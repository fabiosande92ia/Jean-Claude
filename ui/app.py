# ui/app.py
import queue
import tkinter as tk
from tkinter.scrolledtext import ScrolledText

STATE_COLORS = {"idle": "#888888", "recording": "#cc3333", "processing": "#cc9900"}
STATE_LABELS = {"idle": "idle", "recording": "a gravar", "processing": "a processar"}


class App:
    def __init__(self, root, on_press, on_release, ui_queue, on_close):
        self.root = root
        self.ui_queue = ui_queue
        self.on_close = on_close

        root.title("Jean Claude")
        root.geometry("520x600")

        self.state_label = tk.Label(
            root, text=STATE_LABELS["idle"], bg=STATE_COLORS["idle"], fg="white",
            font=("Segoe UI", 12, "bold"), pady=8,
        )
        self.state_label.pack(fill="x")

        self.button = tk.Button(root, text="Numpad -", font=("Segoe UI", 14), height=2)
        self.button.pack(fill="x", padx=8, pady=8)
        self.button.bind("<ButtonPress-1>", lambda e: on_press())
        self.button.bind("<ButtonRelease-1>", lambda e: on_release())

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
                    self.state_label.config(text=STATE_LABELS[payload], bg=STATE_COLORS[payload])
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


def launch(on_press, on_release, ui_queue, on_close):
    root = tk.Tk()
    App(root, on_press, on_release, ui_queue, on_close)
    root.mainloop()
