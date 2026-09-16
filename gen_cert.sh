#!/usr/bin/env bash
# Create a self-signed certificate covering this machine's LAN addresses.
#
# Browsers only allow microphone access in a "secure context": HTTPS, or plain
# HTTP on localhost. So anyone opening the app from another device on the
# network needs TLS, and a certificate that lists the IP they typed.
set -e
cd "$(dirname "$0")"
mkdir -p certs

HOSTNAME_SHORT=$(hostname -s)
IPS=$(ip -4 -o addr show scope global | awk '{print $4}' | cut -d/ -f1 | sort -u)

SAN="DNS:localhost,DNS:${HOSTNAME_SHORT},DNS:${HOSTNAME_SHORT}.local,IP:127.0.0.1"
for ip in $IPS; do SAN="${SAN},IP:${ip}"; done

if [ -f certs/cert.pem ] && [ "$1" != "--force" ]; then
  echo "certs/cert.pem exists; covers:"
  openssl x509 -in certs/cert.pem -noout -ext subjectAltName | tail -1
  echo "re-run with --force to regenerate (do this if your IP changed)"
  exit 0
fi

openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
  -keyout certs/key.pem -out certs/cert.pem \
  -subj "/CN=${HOSTNAME_SHORT} voice conversation" \
  -addext "subjectAltName=${SAN}" \
  -addext "basicConstraints=critical,CA:FALSE" \
  -addext "keyUsage=digitalSignature,keyEncipherment" \
  -addext "extendedKeyUsage=serverAuth" 2>/dev/null

chmod 600 certs/key.pem
echo "wrote certs/cert.pem and certs/key.pem"
echo "covers: ${SAN}"
