# voice/stt.py
import ctypes
import glob
import os
import sys

# O torch (dep do XTTS em voice/tts.py) traz o SEU cudnn 9 em torch/lib. O whisper
# usa o cudnn 9 do pip nvidia-cudnn-cu12. São cópias diferentes. Se o preload do
# nvidia (abaixo) correr primeiro, o torch depois liga o cudnn_cnn64_9.dll às DLLs
# irmãs erradas já em memória e rebenta com WinError 127 ao importar. Importar o
# torch AQUI, antes do preload, deixa-o resolver o cudnn dele primeiro; o preload
# do whisper fica aditivo. Guardado: ambientes sem torch continuam a funcionar.
try:
    import torch  # noqa: F401
except Exception:
    pass

# Os pacotes pip nvidia-cublas-cu12 / nvidia-cuda-nvrtc-cu12 / nvidia-cudnn-cu12 /
# nvidia-nvjitlink-cu12 trazem as DLLs necessárias para o ctranslate2 correr em GPU,
# mas não as colocam no PATH/DLL search path nem garantem que fiquem carregadas antes
# do ctranslate2 tentar resolvê-las. Sem isto, WhisperModel(device="cuda") constrói
# sem erro mas falha de forma intermitente mais tarde (dentro de transcribe(), fora
# do try/except abaixo) com "Library cublas64_12.dll is not found or cannot be
# loaded". Registar as pastas com os.add_dll_directory() e pré-carregar as DLLs com
# ctypes antes de importar faster_whisper elimina essa falha intermitente.
if sys.platform == "win32":
    # SEM_FAILCRITICALERRORS | SEM_NOOPENFILEERRORBOX: sem isto, um WinDLL() com
    # símbolo em falta (DLLs de versões diferentes do torch vs. nvidia-*-cu12 —
    # ex.: cublas64_12.dll a pedir cublasLtGetEnvironmentMode, ou cudnn_cnn64_9.dll
    # com um símbolo C++ em falta) não levanta OSError: o Windows mostra um popup
    # modal "Ponto de entrada não encontrado" e a app fica trancada à espera de OK
    # — um por cada DLL incompatível no glob abaixo. Isto faz o LoadLibrary falhar
    # em silêncio, como o except OSError já esperava.
    try:
        ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x8000)
    except Exception:
        pass
    try:
        import nvidia.cublas
        import nvidia.cuda_nvrtc
        import nvidia.cudnn
        import nvidia.nvjitlink

        for _pkg in (nvidia.cublas, nvidia.cuda_nvrtc, nvidia.cudnn, nvidia.nvjitlink):
            _pkg_dir = next(iter(_pkg.__path__), None)
            _bin_dir = os.path.join(_pkg_dir, "bin") if _pkg_dir else None
            if _bin_dir and os.path.isdir(_bin_dir):
                os.add_dll_directory(_bin_dir)
                for _dll_path in glob.glob(os.path.join(_bin_dir, "*.dll")):
                    try:
                        ctypes.WinDLL(_dll_path)
                    except OSError:
                        pass
    except Exception:
        pass

from faster_whisper import WhisperModel
from core import config

_model = None


def _load_model(device: str, compute_type: str) -> WhisperModel:
    # Se o modelo já estiver em cache local, usa-o offline: evita bater na
    # Hugging Face Hub a cada arranque (observado: rede instável nalguns
    # ambientes derruba a verificação online mesmo com o modelo já em cache).
    try:
        return WhisperModel(
            config.WHISPER_MODEL, device=device, compute_type=compute_type, local_files_only=True
        )
    except Exception:
        return WhisperModel(config.WHISPER_MODEL, device=device, compute_type=compute_type)


def get_model() -> WhisperModel:
    global _model
    if _model is None:
        # tenta GPU (float16); cai para CPU se CUDA indisponível
        try:
            _model = _load_model("cuda", "float16")
        except Exception:
            import sys
            print("[STT: CUDA indisponível, a usar CPU (mais lento)]", file=sys.stderr)
            _model = _load_model("cpu", "int8")
    return _model


def transcribe_file(path: str) -> str:
    model = get_model()
    segments, _ = model.transcribe(path, language="pt", beam_size=5)
    return " ".join(seg.text for seg in segments).strip()
