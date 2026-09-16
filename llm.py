"""Text generation for conversation replies, via a local Ollama server.

Keeps the whole app offline: Ollama runs on http://localhost:11434 and the
default model is a small instruct model that answers in Bengali.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MODEL = os.environ.get("CTC_LLM_MODEL", "gemma3:4b")

SYSTEM = (
    "তুমি একজন সহায়ক বাংলা ভয়েস অ্যাসিস্ট্যান্ট। ব্যবহারকারীর কথা বাংলা স্পিচ-টু-টেক্সট "
    "দিয়ে লেখা হয়েছে, তাই তাতে ছোটখাটো ভুল থাকতে পারে; অর্থ অনুমান করে নাও। "
    "সংক্ষেপে, এক থেকে দুই বাক্যে, কথ্য বাংলায় উত্তর দাও। কোনো markdown ব্যবহার করবে না।"
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
