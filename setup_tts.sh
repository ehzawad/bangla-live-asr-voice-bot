#!/usr/bin/env bash
# Install and cache the local neural Bengali voice (MMS weights: CC-BY-NC-4.0).
set -euo pipefail
cd "$(dirname "$0")"
uv pip install --python .venv/bin/python 'transformers>=4.57,<5' 'uroman>=1.3,<2' torch soundfile
.venv/bin/python - <<'PY'
import os
from transformers import AutoTokenizer, VitsModel
model = os.environ.get('CTC_TTS_MODEL', 'facebook/mms-tts-ben')
VitsModel.from_pretrained(model, use_safetensors=True)
AutoTokenizer.from_pretrained(model)
print('Neural voice cached:', model)
PY
