# Bangla real-time voice bot

An interruptible voice conversation app with typed chat and image attachments.
The microphone remains active while the bot answers. Speak naturally, pause for
an answer, or speak again to interrupt it.

## Models and documented capabilities

- **Gemma 4 E2B (`gemma4:e2b`)** handles speech recognition, conversation, and
  image understanding through local Ollama. The model accepts audio, images,
  and text but **generates text only**; it does not synthesize a voice.
- **Silero VAD** detects speech in the browser. An adaptive timing algorithm
  decides when a conversational turn is finished.
- **Meta MMS Bengali (`facebook/mms-tts-ben`)** converts reply text into speech
  in a dedicated CPU worker. This neural voice replaces the old robotic eSpeak
  fallback. It is a separate model, not “Gemma's voice.”

Primary references: [Google Gemma 4 model card](https://ai.google.dev/gemma/docs/core/model_card_4),
[Google audio guide](https://ai.google.dev/gemma/docs/capabilities/audio),
[Ollama vision API](https://docs.ollama.com/capabilities/vision), and
[MMS Bengali model card](https://huggingface.co/facebook/mms-tts-ben).
The MMS voice weights use **CC-BY-NC-4.0**, including a noncommercial restriction.
Gemma 4 weights use Apache-2.0. Check the model licenses for your intended use.

## Flow

Microphone → VAD → adaptive pause → Gemma audio transcription → streamed Gemma
reply → neural speech, sentence by sentence. Confirmed user speech cancels
pending generation and playback without stopping the microphone.

The default minimum speech duration is 120 ms, with 450 ms pre-roll to retain
word beginnings. Playback interruptions use 250 ms of confirmed speech to
reduce echo/noise triggers; shorter accepted utterances can still interrupt
once transcribed. Natural silence normally waits about 800 ms, about 1200 ms
for short fragments, and up to 1800 ms for trailing connectives such as “কিন্তু”.
The timing adapts to recent pauses and is capped at 2400 ms. These are heuristics,
not a separate semantic end-of-turn model.

Gemma audio input is limited to 30 seconds. Longer VAD segments are divided into
windows of at most 29 seconds, preferring quiet boundaries. In the tested local
Ollama version (0.20.2), the native REST API accepts base64 WAV bytes in the
message's `images` field; [its source routes WAV input to the audio encoder](https://github.com/ollama/ollama/blob/v0.20.2/model/models/gemma4/model.go#L114-L118).
This is not an undocumented `audio` or `audios` field.

## Run

The existing local environment can be used directly:

```bash
./run.sh
```

Open **https://localhost:8443**. For a fresh installation:

```bash
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python -r requirements-web.txt torch
ollama pull gemma4:e2b
./setup_tts.sh
./run.sh
```

Ollama runs on `localhost:11434`. The neural voice downloads once, then stays
loaded on CPU. The bot branch does not load the legacy NeMo ASR model. Browser
VAD assets and fonts are fetched from CDNs, so the initial page load needs internet.

`run.sh` creates a self-signed certificate if none exists. To avoid browser
warnings, use a local CA such as mkcert and install its root in each client
browser's trust store. The server reads `certs/cert.pem` and `certs/key.pem`.
Private certificates and keys are excluded from Git.

## Development controls

- **Show conversation text** toggles transcript and reply visibility. Hidden
  text is still processed, saved, and included in exports; voice continues.
- **Live partial text** is optional and off by default to avoid extra inference
  competing with the bot. When enabled before starting the microphone, rolling
  snapshots provide revisable text previews. This is not native streaming ASR.
- **Speak the reply** toggles speech output independently.
- Speech thresholds, minimum speech duration, pre-roll, and natural pause baseline
  are adjustable. Start/Stop controls the microphone explicitly.

Type in the composer or attach a JPEG, PNG, or WebP image (up to 8 MB /16 million
pixels). Image-only messages are supported. Images are normalized to JPEG, up to
1536 pixels per side, with white transparency backgrounds. The last four images
remain in model context for follow-up voice questions. Resizing can lose fine
OCR detail; do not treat generated descriptions as verified facts.

Conversations are stored under `conversations/<session>/`: WAV recordings,
normalized pictures, and `turns.json`. Export JSON or merged user audio from
the toolbar. Interrupted replies are marked and excluded from future prompts.

## Branches

- `main` and `bot-end-to-end`: the complete Gemma voice/image bot.
- `asr-text-only`: the separate NeMo Bengali transcription application.

Stop the server before switching branches. Recordings, `.venv`, and certificates
are shared ignored local data. No training dataset is required or included;
sample audio files are test fixtures.

## Checks and accuracy

```bash
.venv/bin/python -m unittest discover -s tests -v
node tests/live.test.cjs
node tests/turn-taking.test.cjs
node tests/reply-stream.test.cjs
# Optional browser regression checks; install playwright first, uses local Chrome:
.venv/bin/python tests/browser_duplex.py
.venv/bin/python tests/browser_images.py
# Real audio pipeline, with the server running:
.venv/bin/python test_pipeline.py sample_bn.wav
```

Protocol tests mock inference. Browser regression tests inject VAD events to
verify control flow. A local synthesized “হ্যালো” smoke test was correctly
transcribed by Gemma; this does **not** establish real-microphone accuracy,
WER, VAD precision/recall, or voice naturalness. Those need representative labeled
recordings and listening evaluation. Headphones help prevent speaker feedback
from triggering VAD. Background tabs or mobile OS restrictions can suspend audio.

## Configuration

`CTC_HOST` (default `0.0.0.0`), `CTC_PORT` (8443), `CTC_TLS=0` for HTTP,
`OLLAMA_HOST`, `CTC_LLM_MODEL` (gemma4:e2b), `CTC_TTS_MODEL`
(facebook/mms-tts-ben), `CTC_TTS_THREADS` (4), and `CTC_URL` for CLI tests.

There is no authentication. Anyone with network access can read or delete
sessions, including recordings and images. Use it on a trusted local network.
