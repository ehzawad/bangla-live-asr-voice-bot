# Bengali speech to text — `asr-text-only`

Speak into a microphone or upload an audio file and get Bengali text from the
pretrained `ehzawad/stt_bn_fastconformer_ctc` model. No LLM, generated replies,
speech synthesis, or training dataset is required on this branch.

## Run

```bash
./run.sh
```

Open `https://localhost:8443`, accept the local self-signed certificate, and
click **Start listening**. The script also prints an address for other devices
on your network. Microphone access on those devices requires HTTPS.

The existing `.venv` can be reused. To set up a fresh environment:

```bash
uv venv --python 3.14 .venv
uv pip install --index-strategy unsafe-best-match \
  --extra-index-url https://download.pytorch.org/whl/cu128 \
  "torch==2.9.0+cu128" "nemo_toolkit[asr]==2.7.3" \
  fastapi 'uvicorn[standard]' python-multipart soundfile httpx
```

The ASR checkpoint downloads on first use. Inference runs on a usable GPU,
otherwise CPU. The browser loads VAD libraries and fonts from CDNs.

## How live transcription works

Silero VAD detects speech in the browser. While you speak, the browser sends
16 kHz mono WAV snapshots to `/api/transcribe/live` roughly once per second.
Only one preview request is in flight. The server uses the existing CTC model
to decode each snapshot and returns provisional Bengali text.

This is rolling-window decoding, not native streaming ASR. Words can change
as context arrives, and previews show at most the latest 20 seconds. At each
pause, the whole speech segment is transcribed and saved as a final turn.
Stopping the microphone also submits the current speech segment. Temporary
previews are not saved. Latency depends on inference speed and other sessions.

Upload, waveform playback, adjustable VAD, JSON transcript export, and merged
WAV export are also available. Completed recordings and transcripts are saved
under `conversations/<session>/`; there is no database.

## Branches

- `asr-text-only`: VAD → Bengali ASR → text.
- `bot-end-to-end`: VAD → Bengali ASR → local Ollama reply → optional spoken playback.

Stop the server before switching, then restart:

```bash
git switch bot-end-to-end
./run.sh
```

Both branches use the same ignored local virtual environment, certificates,
and conversation directory. Existing recordings are preserved.

## Files

- `server.py`: FastAPI server, session storage, and final transcription API.
- `streaming.py`: bounded WebSocket preview endpoint.
- `asr.py`: pretrained NeMo model loading and serialized inference.
- `static/index.html`: upload, microphone, transcript, and export interface.
- `static/live.js`: live preview buffering and stale-response handling.
- `run.sh`, `gen_cert.sh`: startup and local HTTPS setup.
- `test_pipeline.py`, `tests/`: real-model smoke check and automated checks.
- `sample_bn.wav`, `sample_bn_words.json`, `sample.wav`: test fixtures.

## Checks

```bash
.venv/bin/python -m unittest discover -s tests -v
node tests/live.test.cjs
# With the server running:
.venv/bin/python test_pipeline.py sample_bn.wav
```

Automated protocol tests mock inference; `test_pipeline.py` uses the real model.

Settings: `CTC_HOST` (default `0.0.0.0`), `CTC_PORT` (default `8443`),
`CTC_TLS=0` for plain HTTP, and `CTC_URL` for the pipeline test. Regenerate the
certificate with `./gen_cert.sh --force` after the machine's address changes.

There is no authentication. Other users with network access can list sessions,
read transcripts, download recordings, and delete sessions. This app is intended
for a trusted local network. Recordings, certificates, and `.venv` are excluded
from Git.
