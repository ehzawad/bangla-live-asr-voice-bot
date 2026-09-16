"""Bengali speech-to-text using ehzawad/stt_bn_fastconformer_ctc (NeMo FastConformer-CTC).

The model is loaded once in a background thread so the web server starts
immediately; transcription calls block until the model is ready.

Input must be 16 kHz mono audio, which is exactly what the browser VAD emits.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("NEMO_TESTING", "0")

log = logging.getLogger("asr")

MODEL_ID = "ehzawad/stt_bn_fastconformer_ctc"
MODEL_FILE = "stt_bn_fastconformer_ctc.nemo"

_model = None
_error: str | None = None
_lock = threading.Lock()          # NeMo transcribe() is not thread-safe
_ready = threading.Event()


def status() -> dict:
    return {
        "model": MODEL_ID,
        "loaded": _model is not None,
        "error": _error,
        "device": getattr(getattr(_model, "device", None), "type", None),
    }


def _usable_cuda() -> bool:
    """True if this GPU can actually run the convolutions the model needs.

    Some driver/cuDNN pairings load fine but raise "unable to find an engine to
    execute this computation" on the first conv. When that happens, turning
    cuDNN off falls back to a native CUDA kernel that works.
    """
    import torch

    if not torch.cuda.is_available():
        return False
    x = torch.randn(1, 80, 400, device="cuda")
    conv = torch.nn.Conv1d(80, 256, 3, padding=1).cuda()
    for disable_cudnn in (False, True):
        if disable_cudnn:
            torch.backends.cudnn.enabled = False
        try:
            with torch.no_grad():
                conv(x)
            if disable_cudnn:
                log.warning("cuDNN cannot run convolutions here; disabled it")
            return True
        except Exception as e:
            log.warning("CUDA conv failed (cudnn=%s): %s", not disable_cudnn, str(e)[:100])
    torch.backends.cudnn.enabled = True
    return False


def _load() -> None:
    global _model, _error
    try:
        import torch
        from huggingface_hub import hf_hub_download
        import nemo.collections.asr as nemo_asr

        path = hf_hub_download(MODEL_ID, MODEL_FILE)
        log.info("loading %s", path)
        model = nemo_asr.models.ASRModel.restore_from(path, map_location="cpu")
        model.eval()
        if _usable_cuda():
            try:
                model = model.to("cuda")
            except Exception as e:                      # e.g. out of VRAM
                log.warning("staying on CPU: %s", e)
        else:
            log.info("no usable GPU, running on CPU")
        _model = model
        log.info("ASR ready on %s", model.device)
    except Exception as e:                              # pragma: no cover
        _error = f"{type(e).__name__}: {e}"
        log.exception("ASR failed to load")
    finally:
        _ready.set()


def start_loading() -> None:
    """Kick off model loading in the background (called once at startup)."""
    threading.Thread(target=_load, name="asr-load", daemon=True).start()


def transcribe(wav_path: str | Path, timeout: float = 600.0) -> str:
    """Return Bengali text for a 16 kHz mono WAV file."""
    if not _ready.wait(timeout):
        raise RuntimeError("ASR model still loading")
    if _model is None:
        raise RuntimeError(_error or "ASR model unavailable")
    with _lock:
        out = _model.transcribe([str(wav_path)], batch_size=1, verbose=False)
    if not out:
        return ""
    first = out[0]
    text = getattr(first, "text", first)               # NeMo >=2 returns Hypothesis
    return (text or "").strip()
