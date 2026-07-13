import queue
import numpy as np
import sounddevice as sd
import soundfile as sf
from pynput import keyboard
from core import config

NUMPAD_MINUS = keyboard.KeyCode.from_vk(0x6D)


def save_wav(frames, samplerate: int, out_path: str) -> str:
    """
    Helper function that writes audio frames to a WAV file.

    Args:
        frames: numpy array or list of arrays (audio samples)
        samplerate: sample rate in Hz
        out_path: output file path

    Returns:
        The output file path
    """
    data = np.concatenate(frames) if isinstance(frames, list) else frames
    sf.write(out_path, data, samplerate)
    return out_path


class Recorder:
    """Gravação de áudio não-bloqueante, controlada por start()/stop() explícitos."""

    def __init__(self, samplerate: int = 16000):
        self.samplerate = samplerate
        self.active = False
        self._q: "queue.Queue" = queue.Queue()
        self._stream = None

    def _audio_cb(self, indata, frames, time, status):
        if self.active:
            self._q.put(indata.copy())

    def start(self) -> None:
        """Começa a gravar. No-op se já estiver a gravar."""
        if self.active:
            return
        self.active = True
        self._q = queue.Queue()
        self._stream = sd.InputStream(
            samplerate=self.samplerate, channels=1, dtype="float32", callback=self._audio_cb
        )
        self._stream.start()

    def stop(self, out_path: str) -> str | None:
        """Para a gravação e escreve o wav. Devolve None se não estava a gravar."""
        if not self.active:
            return None
        self.active = False
        self._stream.stop()
        self._stream.close()
        self._stream = None

        frames = []
        while not self._q.empty():
            frames.append(self._q.get())
        if not frames:
            frames = [np.zeros((1, 1), dtype="float32")]
        return save_wav(frames, self.samplerate, out_path)


class GlobalHotkey:
    """Escuta uma tecla globalmente (sem precisar de foco na janela) via pynput."""

    def __init__(self, key, on_press_cb, on_release_cb):
        self.key = key
        self.on_press_cb = on_press_cb
        self.on_release_cb = on_release_cb
        self._listener = None

    def _on_press(self, key):
        if key == self.key:
            self.on_press_cb()

    def _on_release(self, key):
        if key == self.key:
            self.on_release_cb()

    def start(self) -> None:
        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None
