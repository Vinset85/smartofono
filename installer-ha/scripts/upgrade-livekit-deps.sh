#!/usr/bin/env bash
# Aggiorna dipendenze Python token-issuer LiveKit (container o host).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REQ="${ROOT}/livekit/token_issuer/requirements.txt"

if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx livekit-token-issuer; then
  echo "==> Recreate token-issuer container (pip install on start)"
  cd "${ROOT}/livekit"
  docker compose up -d --force-recreate token-issuer
else
  echo "==> pip install locale (dev)"
  python3 -m pip install --upgrade -r "${REQ}"
fi

echo "==> Fatto"
