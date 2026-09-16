#!/usr/bin/env bash
# Start the Bengali transcription server; no Ollama required.
set -e
cd "$(dirname "$0")"

# HTTPS is what lets other devices use their microphone.
[ -f certs/cert.pem ] || ./gen_cert.sh

exec .venv/bin/python server.py
