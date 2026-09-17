# Bengali voice bot — `bot-end-to-end`

Microphone → browser Silero VAD → live Bengali ASR previews → final transcript
at each pause → local Ollama reply → optional browser speech playback.

This branch includes the complete conversation bot. Switch to `asr-text-only`
for transcription without Ollama, generated replies, or speech playback.
Stop the server before switching branches, then restart it with `./run.sh`.

## Live text

The microphone sends a rolling audio snapshot over `/api/transcribe/live`
roughly once per second, with one request in flight. The existing pretrained
FastConformer-CTC model decodes each snapshot; it is not a native streaming
model. Previews may change and show at most the latest 20 seconds. At a pause,
the full speech segment is transcribed and saved as the final turn. Stopping
the microphone submits the current speech segment too. Previews are temporary
and are not saved as conversation turns.

Replies currently arrive as complete text after each finalized turn. Spoken
playback uses an installed browser voice; Bengali voice availability depends
on the device. Frontend libraries and fonts load from CDNs, and the ASR model
needs an initial download. No training dataset is needed.

## Developer checks

```bash
.venv/bin/python -m unittest discover -s tests -v
node tests/live.test.cjs
```

The automated checks use mocked ASR for repeatable protocol and storage tests.
For real model inference, start the app and run `test_pipeline.py` below.
Recordings, certificates, and `.venv` are excluded from Git.

---

# Bangla Voice Conversation (VAD → ASR → reply)

Upload an audio file or talk into the microphone. Silero VAD cuts speech into
turns in the browser, each turn is transcribed by a Bengali FastConformer-CTC
model, and a local LLM writes a reply. Everything runs on this machine.

| stage | what runs | where |
|---|---|---|
| voice activity detection | Silero VAD via `@ricky0123/vad-web` (ONNX runtime, WASM) | browser |
| speech to text | [`ehzawad/stt_bn_fastconformer_ctc`](https://huggingface.co/ehzawad/stt_bn_fastconformer_ctc) (NeMo, 115 M params) | server, GPU if free |
| text generation | Ollama chat model, default `gemma4:e2b` | localhost:11434 |
| speech out (optional) | browser `speechSynthesis`, `bn-BD` voice if installed | browser |

## Setup

The environment is built with [uv](https://docs.astral.sh/uv/) on Python 3.14,
the newest release NeMo runs on here:

```bash
uv venv --python 3.14 .venv
uv pip install --index-strategy unsafe-best-match \
  --extra-index-url https://download.pytorch.org/whl/cu128 \
  "torch==2.9.0+cu128" "nemo_toolkit[asr]==2.7.3" fastapi uvicorn "websockets>=14,<17" python-multipart soundfile
```

Text generation needs Ollama with a chat model:

```bash
ollama serve &          # if not already running
ollama pull gemma4:e2b   # or set CTC_LLM_MODEL to any model you have
```

## Run

```bash
./run.sh
```

It starts Ollama if needed, creates the certificate on first run, and prints
the addresses plus a QR code you can scan with a phone:

```
  open on this machine : https://localhost:8443
  share on the network : https://172.16.213.77:8443
```

Anyone on the same network opens that address. The ASR checkpoint (463 MB)
downloads on first start and the header pill turns green when it is ready.

### Why HTTPS

Browsers only allow microphone access in a "secure context": HTTPS, or plain
HTTP on localhost. Over `http://<your-ip>:8000` other devices could upload
files but never record, so the server serves HTTPS on port 8443 with a
certificate that `gen_cert.sh` issues for this machine's addresses.

The certificate is self-signed, so each device shows a warning the first time:

| browser | what to tap |
|---|---|
| Chrome, Edge, Android | Advanced, then Proceed to … |
| Safari, iPhone, iPad | Show Details, then visit this website |
| Firefox | Advanced, then Accept the Risk and Continue |

Run `./gen_cert.sh --force` if this machine's IP address changes. For warning-free
access install [mkcert](https://github.com/FiloSottile/mkcert) on each device instead.

Settings: `CTC_PORT` changes the port, `CTC_HOST` the bind address,
`CTC_TLS=0` serves plain HTTP (localhost microphone only).

## Use

1. **Upload** an audio file. Each detected speech segment becomes a turn with a
   waveform, a player and its Bengali transcript. Clicking a highlighted region
   on the timeline plays that turn.
2. **Start listening** to continue by voice. Speak, pause, and the turn is
   transcribed and answered. Turning on *Speak the reply* reads it back and
   pauses the microphone while it talks, so the assistant does not hear itself.
3. **Export** the transcript as JSON or the speech as one merged WAV.

On a phone the conversation fills the screen, the settings fold away into two
panels, and the listen button docks to the bottom above the home indicator. The
screen is kept awake while the microphone is running.

Each browser gets its own session, and several people can use it at once.
Transcription runs one clip at a time on the GPU, so simultaneous turns queue
rather than compete for memory.

Turns are written to `conversations/<session>/` as 16 kHz WAV files plus
`turns.json` with timings and text.

## Check it without a browser

```bash
.venv/bin/python test_pipeline.py sample_bn.wav
```

`sample_bn.wav` is 9.4 s of Bengali built from four Wikimedia Commons
pronunciation recordings separated by silence; `sample_bn_words.json` lists the
words spoken, in order. `sample.wav` is an English clip for VAD-only testing.

## Settings

| control | effect |
|---|---|
| speech / silence threshold | how loud-and-voiced a frame must be to count as speech |
| end-of-turn silence | pause length that closes a turn, raise it if you are cut off mid-sentence |
| min speech | drops blips shorter than this |
| pre-speech pad | audio kept before the trigger, so turns do not start clipped |

Environment variables: `CTC_LLM_MODEL` picks the Ollama model, `OLLAMA_HOST`
points at a different Ollama server.

## Measured on this machine

RTX 2050 (4 GB), Bengali test clip, greedy CTC decoding:

| step | time |
|---|---|
| ASR per speech turn (0.5–2 s of audio) | 29–79 ms |
| ASR for the whole 9.4 s file in one call | 240 ms |
| reply from `gemma3:4b` | 1.1–4.5 s |
| ASR model load at startup | ~30 s |

## Notes

**cuDNN.** The cuDNN build that ships with this torch wheel cannot run
convolutions on this GPU: the first one raises "unable to find an engine to
execute this computation". `asr.py` probes for that at startup and turns cuDNN
off, which falls back to a native CUDA kernel that works. If you move to
another machine the probe just passes and cuDNN stays on.

**Anyone on the network can use it, and there is no login.** The API also
lets any of them list sessions and download another session's audio, so treat
it as an open tool on a network you trust, not something to expose to the
internet.

**Quiet recordings.** Speech more than about 25 dB below the rest of a file may
fall under the VAD threshold and produce no turn. Lower the speech threshold,
or normalise the file first.

The ASR model expects 16 kHz mono, which is exactly what the VAD emits, and
returns normalised Bengali without punctuation. It reports 17.12 % WER on the
FLEURS Bengali test split with greedy decoding and no language model, so
expect transcription errors on noisy or accented input. The reply prompt tells
the model to read through minor ASR mistakes.
