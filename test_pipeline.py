"""End-to-end check of the server pipeline without a browser.

Posts a WAV as a conversation turn, prints the Bengali transcript, and verifies the saved turn.

    .venv/bin/python test_pipeline.py [audio.wav]

Set CTC_URL to point at a different server.
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.request
import uuid
from pathlib import Path

BASE = os.environ.get("CTC_URL", "https://127.0.0.1:8443")
# the server uses a self-signed certificate on the LAN
CTX = ssl._create_unverified_context() if BASE.startswith("https") else None


def post(path: str, data: bytes, ctype: str) -> dict:
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=900, context=CTX) as r:
        return json.load(r)


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=60, context=CTX) as r:
        return json.load(r)


def multipart(fields: dict, fname: str, blob: bytes) -> tuple[bytes, str]:
    b = "----" + uuid.uuid4().hex
    out = bytearray()
    for k, v in fields.items():
        out += f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    out += (f"--{b}\r\nContent-Disposition: form-data; name=\"audio\"; filename=\"{fname}\"\r\n"
            f"Content-Type: audio/wav\r\n\r\n").encode()
    out += blob + f"\r\n--{b}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={b}"


def main() -> int:
    wav = Path(sys.argv[1] if len(sys.argv) > 1 else "sample_bn.wav")
    if not wav.exists():
        print(f"missing {wav}")
        return 1

    print("waiting for the ASR model to load…")
    for _ in range(240):
        h = get("/api/health")
        if h["asr"]["loaded"] or h["asr"]["error"]:
            break
        time.sleep(5)
    h = get("/api/health")
    print("  asr:", h["asr"])
    if h["asr"]["error"]:
        return 1

    sid = post("/api/sessions", b"", "application/json")["session_id"]
    print("session:", sid)

    body, ctype = multipart(
        {"source": "file", "start_ms": "0", "end_ms": "0", "origin": wav.name, "transcribe": "true"},
        wav.name, wav.read_bytes())
    t0 = time.perf_counter()
    turn = post(f"/api/sessions/{sid}/turns", body, ctype)
    print(f"\ntranscript ({turn['asr_ms']} ms): {turn['text']!r}")
    if turn["asr_error"]:
        print("asr error:", turn["asr_error"])
        return 1

    ref = Path("sample_bn_words.json")
    if ref.exists() and wav.name == "sample_bn.wav":
        print("reference words:", " ".join(json.loads(ref.read_text())))

    saved = get(f"/api/sessions/{sid}")["turns"]
    assert saved and saved[-1]["text"] == turn["text"]
    print(f"\ntotal {time.perf_counter() - t0:.1f}s · saved in conversations/{sid}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
