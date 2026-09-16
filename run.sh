#!/usr/bin/env bash
# Start Ollama (if needed) and the conversation server on the local network.
set -e
cd "$(dirname "$0")"

if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "starting ollama…"
  nohup ollama serve >/tmp/ollama.log 2>&1 &
  for _ in $(seq 1 20); do curl -sf http://localhost:11434/api/tags >/dev/null 2>&1 && break; sleep 1; done
fi

# HTTPS is what lets other devices use their microphone.
[ -f certs/cert.pem ] || ./gen_cert.sh

exec .venv/bin/python server.py
