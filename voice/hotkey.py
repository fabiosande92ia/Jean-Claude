import queue
import numpy as np
import sounddevice as sd
import soundfile as sf
from pynput import keyboard
from core import config


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


def record_between_keys(out_path: str, samplerate: int = 16000) -> str:
    """
    Records audio from the microphone while the space key is held down.
    Stops recording when the key is released.

    Args:
        out_path: output WAV file path
        samplerate: sample rate in Hz (default 16000)

    Returns:
        The output file path
    """
    q: "queue.Queue" = queue.Queue()
    recording = {"active": False, "done": False}

    def audio_cb(indata, frames, time, status):
        """Audio stream callback."""
        if recording["active"]:
            q.put(indata.copy())

    def on_press(key):
        """Key press event handler."""
        if key == keyboard.Key.space:
            recording["active"] = True

    def on_release(key):
        """Key release event handler."""
        if key == keyboard.Key.space and recording["active"]:
            recording["active"] = False
            recording["done"] = True
            return False  # stop the listener

    frames = []
    with sd.InputStream(samplerate=samplerate, channels=1, dtype="float32", callback=audio_cb):
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()
            while not q.empty():
                frames.append(q.get())

    if not frames:
        frames = [np.zeros((1, 1), dtype="float32")]
    return save_wav(frames, samplerate, out_path)
