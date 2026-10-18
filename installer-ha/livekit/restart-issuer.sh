#!/bin/sh
# Ricostruisce SOLO livekit-token-issuer (niente stop di livekit/caddy/redis).
# Uso sull'host HA / addon SSH: /addons/livekit/restart-issuer.sh
set -eu
LIVEKIT_DIR_LOCAL="${LIVEKIT_DIR_LOCAL:-/addons/livekit}"
if [ ! -f "$LIVEKIT_DIR_LOCAL/token_issuer/issuer.py" ]; then
    echo "ERRORE: manca $LIVEKIT_DIR_LOCAL/token_issuer/issuer.py" >&2
    exit 1
fi
for _sec in "${LIVEKIT_DIR_LOCAL}/.secrets" "/addons/livekit/.secrets"; do
    if [ -f "$_sec" ]; then
        set -a
        # shellcheck disable=SC1090
        . "$_sec"
        set +a
        break
    fi
done
LIVEKIT_API_KEY="${LIVEKIT_API_KEY:-videocitofono}"
LIVEKIT_API_SECRET="${LIVEKIT_API_SECRET:-}"
EGRESS_SECRET="${EGRESS_SECRET:-}"
TOKEN_ISSUER_SECRET="${TOKEN_ISSUER_SECRET:-}"
PUBLIC_HOST="${PUBLIC_HOST:-casa-esempio.duckdns.org}"
if [ -z "$LIVEKIT_API_SECRET" ] || [ -z "$EGRESS_SECRET" ] || [ -z "$TOKEN_ISSUER_SECRET" ]; then
    echo "ERRORE: LIVEKIT_API_SECRET, EGRESS_SECRET, TOKEN_ISSUER_SECRET in .secrets" >&2
    exit 1
fi
ISSUER_IMAGE="videocitofono-token-issuer:1"
echo "==> build token-issuer"
tar -C "$LIVEKIT_DIR_LOCAL/token_issuer" -cf - Dockerfile requirements.txt issuer.py \
  | docker build -t "$ISSUER_IMAGE" -
echo "==> replace livekit-token-issuer"
docker rm -f livekit-token-issuer 2>/dev/null || true
docker run -d \
  --name livekit-token-issuer \
  --restart unless-stopped \
  --network host \
  -e LIVEKIT_API_KEY="$LIVEKIT_API_KEY" \
  -e LIVEKIT_API_SECRET="$LIVEKIT_API_SECRET" \
  -e LIVEKIT_HOST="wss://${PUBLIC_HOST}/livekit" \
  -e LIVEKIT_HOST_LAN="ws://192.168.1.160:7880" \
  -e TOKEN_ISSUER_PORT=8081 \
  -e TOKEN_ISSUER_SECRET="$TOKEN_ISSUER_SECRET" \
  -e EGRESS_SECRET="$EGRESS_SECRET" \
  -e LIVEKIT_API_URL="http://127.0.0.1:7880" \
  -e EGRESS_OUTPUT_DIR="/out" \
  "$ISSUER_IMAGE"
echo "==> issuer sostituito (health: curl -sS http://127.0.0.1:8081/health)"
