#!/bin/sh
# Avvia/riavvia lo stack LiveKit (server + token-issuer + caddy edge) sull'host
# HA OS senza docker-compose (non disponibile sull'host: solo docker engine).
# Idempotente: rimuove i container esistenti prima di ricrearli.
#
# Uso (sull'host HA, da utente con accesso a docker):
#   ./start.sh
#
# Pre-requisiti host HA OS:
#   - Cert TLS in /mnt/data/supervisor/ssl/{fullchain,privkey}.pem
#     (gestiti dall'addon Duck DNS oppure manualmente). Se non li hai,
#     decommenta la sezione "TLS-MANAGED-BY-CADDY" nel Caddyfile e rimuovi
#     il bind-mount /ssl da questo script.
#   - Port-forward sul router. Il router casa NON supporta intervalli di porte
#     e accetta solo porte <= 8191. Configurazione LiveKit single-port-mux:
#     regole singole (1 porta ciascuna), nessun range:
#         WAN 443  tcp -> 192.168.1.160:443    (HTTPS / Caddy: HA + signaling LK + token)
#         WAN 80   tcp -> 192.168.1.160:80     (redirect HTTP->HTTPS, opzionale)
#         WAN 8100 udp -> 192.168.1.160:8100   (LiveKit RTP/RTCP, single-port mux)
#         WAN 7881 tcp -> 192.168.1.160:7881   (LiveKit ICE/TLS fallback per reti senza UDP)
#         WAN 3478 udp -> 192.168.1.160:3478   (TURN UDP, client 4G/hotel)
#         WAN 5349 tcp -> 192.168.1.160:5349   (TURN TLS)
#   - DNS pubblico casa-esempio.duckdns.org -> IP WAN del router (gia' attivo).
#   - Hairpin NAT abilitato sul router (i tablet in LAN risolvono il dominio
#     pubblico e il router rimanda al miniPC HA).
set -eu

# LIVEKIT_DIR e' il path che il docker DAEMON (host HA OS) usera' per i bind
# mount. Sull'host HA OS i file dell'addon "local" vivono in
# /mnt/data/supervisor/addons/local/livekit. Se invece lanciamo lo script da
# DENTRO l'addon SSH, lo stesso path e' visibile come /addons/livekit.
LIVEKIT_DIR="${LIVEKIT_DIR:-/mnt/data/supervisor/addons/local/livekit}"
# LIVEKIT_DIR_LOCAL serve solo per il sanity check del file di config; e' il
# path con cui lo script vede i file localmente (in addon SSH = /addons/livekit).
LIVEKIT_DIR_LOCAL="${LIVEKIT_DIR_LOCAL:-$LIVEKIT_DIR}"
if [ ! -f "$LIVEKIT_DIR_LOCAL/livekit.yaml" ] && [ -f "/addons/livekit/livekit.yaml" ]; then
    LIVEKIT_DIR_LOCAL="/addons/livekit"
fi
LIVEKIT_IMAGE="livekit/livekit-server:v1.13.10"
ISSUER_IMAGE="videocitofono-token-issuer:1"
CADDY_IMAGE="caddy:2.11-alpine"
REDIS_IMAGE="redis:7-alpine"
EGRESS_IMAGE="livekit/egress:v1.15.0"

# Segreti: env, poi file non versionato `.secrets` (KEY=value).
# Mai committare valori veri: vedi .secrets.example.
for _sec in \
    "${LIVEKIT_DIR_LOCAL}/.secrets" \
    "/addons/livekit/.secrets"; do
    if [ -f "$_sec" ]; then
        # shellcheck disable=SC1090
        set -a
        . "$_sec"
        set +a
        echo "==> secrets da $_sec"
        break
    fi
done

LIVEKIT_API_KEY="${LIVEKIT_API_KEY:-videocitofono}"
LIVEKIT_API_SECRET="${LIVEKIT_API_SECRET:-}"
# Secret richiesto (header X-VC-Egress) sugli endpoint /egress/* del token
# issuer. Serve perche' l'issuer e' esposto pubblicamente da Caddy sotto
# /livekit-token/*: senza secret chiunque da Internet potrebbe avviare
# registrazioni. Il Caddyfile blocca comunque /livekit-token/egress/* dalla
# WAN; questo e' il secondo strato. Deve combaciare con il rest_command HA
# (installer-ha/packages/configuration.yaml.fixed).
EGRESS_SECRET="${EGRESS_SECRET:-}"
if [ -z "$LIVEKIT_API_SECRET" ] || [ -z "$EGRESS_SECRET" ]; then
    echo "ERRORE: LIVEKIT_API_SECRET e EGRESS_SECRET vanno in env o in .secrets" >&2
    echo "        (copia .secrets.example -> .secrets e riempilo)." >&2
    exit 1
fi
# Cartella host dove l'egress scrive gli MP4. Corrisponde a
# /config/www/videocitofono lato HA, servita come /local/videocitofono/<file>.
RECORDINGS_DIR="${RECORDINGS_DIR:-/mnt/data/supervisor/homeassistant/www/videocitofono}"
PUBLIC_HOST="${PUBLIC_HOST:-casa-esempio.duckdns.org}"
## NB: senza `/rtc` finale. Il client SDK livekit-client appende `/rtc` da
## solo (es. ${host}/rtc?access_token=...). Caddy fa handle_path /livekit/*
## che strippa /livekit, quindi /livekit/rtc?... -> upstream /rtc?...
## (signaling endpoint corretto del livekit-server).
LIVEKIT_HOST_PUBLIC="wss://${PUBLIC_HOST}/livekit"
LIVEKIT_HOST_LAN="ws://192.168.1.160:7880"

echo "==> LIVEKIT_DIR        : $LIVEKIT_DIR (path host per docker mount)"
echo "==> LIVEKIT_DIR_LOCAL  : $LIVEKIT_DIR_LOCAL (path locale per sanity check)"
echo "==> PUBLIC_HOST         : $PUBLIC_HOST"
echo "==> LIVEKIT_HOST        : $LIVEKIT_HOST_PUBLIC"

if [ ! -f "$LIVEKIT_DIR_LOCAL/livekit.yaml" ]; then
    echo "ERRORE: $LIVEKIT_DIR_LOCAL/livekit.yaml mancante. Hai eseguito deploy-livekit-stack.sh?" >&2
    exit 1
fi
if [ ! -f "$LIVEKIT_DIR_LOCAL/egress.yaml" ]; then
    echo "ERRORE: $LIVEKIT_DIR_LOCAL/egress.yaml mancante. Hai eseguito deploy-livekit-stack.sh?" >&2
    exit 1
fi

echo "==> stop containers vecchi (se esistono)"
docker rm -f livekit 2>/dev/null || true
docker rm -f livekit-token-issuer 2>/dev/null || true
docker rm -f livekit-caddy 2>/dev/null || true
docker rm -f livekit-egress 2>/dev/null || true
docker rm -f livekit-redis 2>/dev/null || true

echo "==> pull immagini"
docker pull "$LIVEKIT_IMAGE"
docker pull "$CADDY_IMAGE"
docker pull "$REDIS_IMAGE"
docker pull "$EGRESS_IMAGE"

echo "==> build token-issuer (pip pinato nell'immagine, niente install a ogni avvio)"
if [ ! -f "$LIVEKIT_DIR_LOCAL/token_issuer/Dockerfile" ]; then
    echo "ERRORE: $LIVEKIT_DIR_LOCAL/token_issuer/Dockerfile mancante" >&2
    exit 1
fi
tar -C "$LIVEKIT_DIR_LOCAL/token_issuer" -cf - Dockerfile requirements.txt issuer.py \
  | docker build -t "$ISSUER_IMAGE" -

# Redis PRIMA di livekit-server: con `redis:` in livekit.yaml il server esce
# all'avvio se la coda non risponde. bind 127.0.0.1 -> non esposto in LAN;
# niente persistenza (--save "" --appendonly no) perche' contiene solo job
# egress e stato room effimero, ricostruito alla riconnessione dei client.
echo "==> start redis (coda job egress)"
docker run -d \
  --name livekit-redis \
  --restart unless-stopped \
  --network host \
  "$REDIS_IMAGE" \
  redis-server --bind 127.0.0.1 --port 6379 --save '' --appendonly no

printf "==> attendo redis"
i=0
while [ "$i" -lt 30 ]; do
    if docker exec livekit-redis redis-cli -h 127.0.0.1 ping 2>/dev/null | grep -q PONG; then
        echo " -> PONG"
        break
    fi
    printf "."
    i=$((i + 1))
    sleep 1
done
if [ "$i" -ge 30 ]; then
    echo ""
    echo "ERRORE: redis non risponde, livekit-server non partirebbe. Log:" >&2
    docker logs --tail 30 livekit-redis >&2
    exit 1
fi

echo "==> start livekit-server"
docker run -d \
  --name livekit \
  --restart unless-stopped \
  --network host \
  -v "$LIVEKIT_DIR/livekit.yaml:/etc/livekit.yaml:ro" \
  -v /mnt/data/supervisor/ssl:/ssl:ro \
  "$LIVEKIT_IMAGE" \
  --config /etc/livekit.yaml

# Egress: registrazione MP4 del visitatore (participant egress su identity
# `rpi`). Scrive in /out, bind-mount della cartella www del videocitofono, cosi'
# i file sono immediatamente serviti come /local/videocitofono/<file>.mp4.
# --cap-add SYS_ADMIN e' richiesto dall'immagine (sandbox Chrome); il nostro
# tipo di egress non avvia Chrome, ma senza la cap il servizio logga errori.
echo "==> start livekit-egress"
# La cartella delle registrazioni va preparata SULL'HOST: /mnt/data non e'
# visibile da dentro l'addon SSH, quindi un mkdir diretto qui creerebbe una
# cartella nel container e il bind mount resterebbe vuoto.
#
# chmod g+w e non chown: il processo dentro il container egress e' uid 1001
# (egress) ma gid 0 (root), mentre la cartella e' root:root 755 -> senza il
# bit di scrittura per il gruppo l'egress fallisce a fine registrazione con
# "Local upload failed: open /out/<file>.mp4: permission denied", dopo aver
# comunque registrato tutto. Con g+w l'egress scrive e HA (root) mantiene
# pieno controllo su lettura e cancellazione dei file.
docker run --rm -v "$(dirname "$RECORDINGS_DIR"):/parent" alpine sh -c "
    mkdir -p '/parent/$(basename "$RECORDINGS_DIR")'
    chmod 775 '/parent/$(basename "$RECORDINGS_DIR")'
"
docker run -d \
  --name livekit-egress \
  --restart unless-stopped \
  --network host \
  --cap-add SYS_ADMIN \
  -e EGRESS_CONFIG_FILE=/etc/egress.yaml \
  -v "$LIVEKIT_DIR/egress.yaml:/etc/egress.yaml:ro" \
  -v "$RECORDINGS_DIR:/out" \
  "$EGRESS_IMAGE"

echo "==> start livekit-token-issuer"
docker run -d \
  --name livekit-token-issuer \
  --restart unless-stopped \
  --network host \
  -e LIVEKIT_API_KEY="$LIVEKIT_API_KEY" \
  -e LIVEKIT_API_SECRET="$LIVEKIT_API_SECRET" \
  -e LIVEKIT_HOST="$LIVEKIT_HOST_PUBLIC" \
  -e LIVEKIT_HOST_LAN="$LIVEKIT_HOST_LAN" \
  -e TOKEN_ISSUER_PORT=8081 \
  -e EGRESS_SECRET="$EGRESS_SECRET" \
  -e LIVEKIT_API_URL="http://127.0.0.1:7880" \
  -e EGRESS_OUTPUT_DIR="/out" \
  "$ISSUER_IMAGE"

echo "==> start caddy edge"
docker run -d \
  --name livekit-caddy \
  --restart unless-stopped \
  --network host \
  --cap-add NET_BIND_SERVICE \
  -v "$LIVEKIT_DIR/Caddyfile:/etc/caddy/Caddyfile:ro" \
  -v /mnt/data/supervisor/ssl:/ssl:ro \
  -v livekit_caddy_data:/data \
  -v livekit_caddy_config:/config \
  "$CADDY_IMAGE"

echo ""
echo "==> stato"
docker ps --filter name=livekit --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

echo ""
echo "==> verifiche"
echo "  health token issuer (LAN): curl http://192.168.1.160:8081/health"
echo "  health LiveKit       (LAN): curl http://192.168.1.160:7880/"
echo "  egress pronto             : docker logs livekit-egress | grep -i 'egress ready'"
echo "  registrazioni             : ls -lh $RECORDINGS_DIR"
echo "  health Caddy         (LAN): curl -k https://192.168.1.160/livekit-token/health"
echo "  health Caddy         (WAN): curl     https://${PUBLIC_HOST}/livekit-token/health"
echo ""
echo "==> tablet di casa: configurare URL HA come https://${PUBLIC_HOST}"
echo "    (richiede hairpin NAT abilitato sul router)"
