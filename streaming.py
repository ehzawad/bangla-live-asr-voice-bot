"""Bounded rolling-window ASR previews; final turns use the upload API."""
import io
import tempfile
import wave
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

import asr

router = APIRouter()
MAX_AUDIO_BYTES = 16000 * 2 * 20 + 4096


def decode_preview(blob: bytes) -> str:
    if len(blob) > MAX_AUDIO_BYTES:
        raise ValueError("Preview exceeds 20 seconds")
    with wave.open(io.BytesIO(blob), "rb") as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (16000, 1, 2):
            raise ValueError("Expected 16 kHz mono PCM16 WAV")
        if not 0 < wav.getnframes() <= 320000:
            raise ValueError("Preview must contain at most 20 seconds of audio")
        if len(wav.readframes(wav.getnframes())) != wav.getnframes() * 2:
            raise ValueError("Truncated WAV")
    with tempfile.TemporaryDirectory(prefix="ctc-preview-") as directory:
        path = Path(directory) / "preview.wav"
        path.write_bytes(blob)
        return asr.transcribe(path, timeout=1)


@router.websocket("/api/transcribe/live")
async def live_transcription(socket: WebSocket):
    await socket.accept()
    try:
        while True:
            blob = await socket.receive_bytes()
            if len(blob) > MAX_AUDIO_BYTES:
                await socket.close(code=1009, reason="Preview too large")
                return
            if not asr.status()["loaded"]:
                await socket.send_json({"type": "error", "error": "ASR is not ready"})
                continue
            try:
                text = await run_in_threadpool(decode_preview, blob)
                await socket.send_json({"type": "partial", "text": text})
            except Exception as exc:
                await socket.send_json({"type": "error", "error": str(exc)})
    except WebSocketDisconnect:
        pass
