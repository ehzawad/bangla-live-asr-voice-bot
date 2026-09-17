"""Text generation for conversation replies, via a local Ollama server.

Keeps the whole app offline: Ollama runs on http://localhost:11434 and the
default model is a small instruct model that answers in Bengali.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import urllib.error
import urllib.request
import wave

import httpx

OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MODEL = os.environ.get("CTC_LLM_MODEL", "gemma4:e2b")

SYSTEM = (
    "তুমি একজন সহায়ক বাংলা ভয়েস অ্যাসিস্ট্যান্ট। ব্যবহারকারীর কথা বাংলা স্পিচ-টু-টেক্সট "
    "দিয়ে লেখা হয়েছে, তাই তাতে ছোটখাটো ভুল থাকতে পারে; অর্থ অনুমান করে নাও। "
    "সংক্ষেপে, এক থেকে দুই বাক্যে, কথ্য বাংলায় উত্তর দাও। কোনো markdown ব্যবহার করবে না।"
    "ছবি থাকলে ছবিটি দেখে ব্যবহারকারীর প্রশ্নের উত্তর দাও। যা দেখা যায় না তা বানিয়ে বলবে না।"
)


def available() -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def models() -> list[str]:
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=3) as r:
            return [m["name"] for m in json.load(r).get("models", [])]
    except Exception:
        return []


def reply(history: list[dict], model: str | None = None, timeout: float = 180.0) -> str:
    """history: [{"role": "user"|"assistant", "content": str}, ...]"""
    payload = {
        "model": model or MODEL,
        "stream": False,
        "think": False,
        "options": {"temperature": 0.6, "num_predict": 160},
        "messages": [{"role": "system", "content": SYSTEM}, *history],
    }
    req = urllib.request.Request(
        f"{OLLAMA}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ollama unreachable at {OLLAMA}: {e.reason}") from e
    text = (data.get("message") or {}).get("content", "")
    # Some models emit <think>…</think>; keep only the answer.
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text.strip()


async def reply_async(history: list[dict], model: str | None = None) -> str:
    """Cancellable request: interruption closes the connection to Ollama."""
    payload = {
        "model": model or MODEL, "stream": False, "think": False,
        "options": {"temperature": 0.6, "num_predict": 160},
        "messages": [{"role": "system", "content": SYSTEM}, *history],
    }
    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(f"{OLLAMA}/api/chat", json=payload)
        response.raise_for_status()
        text = (response.json().get("message") or {}).get("content", "")
    return text.split("</think>")[-1].strip()


async def transcribe_audio(blob: bytes) -> str:
    """Transcribe a <=30-second mono 16 kHz PCM16 WAV using Gemma audio input.

    Ollama 0.20.2 transports WAV bytes in the multimodal ``images`` field.
    Gemma returns text, not synthesized speech. Cancellation closes the request.
    """
    if len(blob) > 1_000_000:
        raise ValueError("Audio must be a WAV clip of at most 30 seconds")
    try:
        with wave.open(io.BytesIO(blob), "rb") as wav:
            frames = wav.getnframes()
            if (wav.getnchannels() != 1 or wav.getframerate() != 16000
                    or wav.getsampwidth() != 2 or wav.getcomptype() != "NONE"):
                raise ValueError("Audio must be mono 16 kHz PCM16 WAV")
            if not 0 < frames <= 30 * 16000:
                raise ValueError("Audio must be nonempty and at most 30 seconds")
            if len(wav.readframes(frames)) != frames * 2:
                raise ValueError("Audio WAV data is truncated")
    except (wave.Error, EOFError) as exc:
        raise ValueError("Audio must be a valid PCM16 WAV") from exc

    payload = {
        "model": MODEL, "stream": False, "think": False,
        "options": {"temperature": 0, "num_predict": 256},
        "messages": [{
            "role": "user",
            "content": (
                "Transcribe the following speech segment into Bengali text. "
                "Preserve what was actually spoken, including short greetings "
                "(write a spoken hello as হ্যালো). Do not answer the speaker or "
                "add explanations. Do not invent words. If there is no speech, "
                "output nothing. Only output the transcription, with no newlines."
            ),
            "images": [base64.b64encode(blob).decode("ascii")],
        }],
    }

    async def request() -> str:
        async with httpx.AsyncClient(timeout=55.0) as client:
            response = await client.post(f"{OLLAMA}/api/chat", json=payload)
            response.raise_for_status()
            text = (response.json().get("message") or {}).get("content", "")
        return text.split("</think>")[-1].strip()

    return await asyncio.wait_for(request(), timeout=60.0)


async def reply_stream(history: list[dict], model: str | None = None):
    """Yield only answer text from Ollama; closing the generator closes HTTP."""
    payload = {
        "model": model or MODEL, "stream": True, "think": False,
        "options": {"temperature": 0.6, "num_predict": 160},
        "messages": [{"role": "system", "content": SYSTEM}, *history],
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
        async with client.stream("POST", f"{OLLAMA}/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                event = json.loads(line)
                if event.get("error"):
                    raise RuntimeError(event["error"])
                text = (event.get("message") or {}).get("content", "")
                if text:
                    yield text
                if event.get("done"):
                    return
            raise RuntimeError("Ollama response stream ended before completion")
