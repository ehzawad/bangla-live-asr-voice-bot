#!/usr/bin/env bash
# Install the offline Bengali speech fallback for this user on Ubuntu/Debian amd64.
set -euo pipefail
if [ "$(dpkg --print-architecture)" != amd64 ]; then
  echo 'Use your package manager to install espeak-ng on this architecture.' >&2
  exit 1
fi
target="$HOME/.local/lib/ctc-speech-tools"
mkdir -p "$target"
cd "$target"
apt-get download espeak-ng espeak-ng-data libespeak-ng1 libpcaudio0
for package in ./*.deb; do dpkg-deb -x "$package" .; done
LD_LIBRARY_PATH="$target/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}" "$target/usr/bin/espeak-ng" --path="$target/usr/lib/x86_64-linux-gnu" --voices=bn
