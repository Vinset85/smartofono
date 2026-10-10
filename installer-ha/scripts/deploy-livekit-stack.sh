#!/usr/bin/env bash
# Deploy lo stack LiveKit + Caddy edge sull'host HA OS (192.168.1.160).
#
# Cosa fa:
#   1. SCP della cartella installer-ha/livekit/ in /tmp/livekit del host HA.
#   2. SSH: install dei config in DUE posizioni (vedi step [2/5] per il perche'):
#      /addons/livekit/ (vista addon SSH) e /mnt/data/supervisor/addons/local/
#      livekit/ (filesystem host, quello che il docker daemon risolve).
#   3. SSH: lancia start.sh (containers livekit-redis, livekit,
#      livekit-egress, livekit-token-issuer, livekit-caddy in network=host).
#   4. SSH: deploy del frontend asset (vc-livekit.js) in /config/www/.
#   5. Verifica health.
#
# Pre-requisiti host:
#   - addon Advanced SSH & Web Terminal attivo, accessibile su 192.168.1.160:22
#   - cert /ssl/fullchain.pem + privkey.pem gia' validi (addon Duck DNS)
#   - port-forward sul router (4 porte SINGOLE - il router casa non supporta
#     range e accetta solo porte <= 8191):
#         WAN 443  tcp -> 192.168.1.160:443    (HTTPS Caddy: HA + LK signaling + token)
#         WAN 80   tcp -> 192.168.1.160:80     (redirect HTTP->HTTPS, opzionale)
#         WAN 8100 udp -> 192.168.1.160:8100   (LiveKit RTP/RTCP single-port mux)
#         WAN 7881 tcp -> 192.168.1.160:7881   (LiveKit ICE/TLS fallback)
#
# Uso:
#   cd installer-ha
#   ./scripts/deploy-livekit-stack.sh
#
# Variabili override:
#   HA_HOST        (default: 192.168.1.160)
#   HA_USER        (default: hassio)
#   HA_PASS        (env var; oppure ssh-key-based)
#   PUBLIC_HOST    (default: casa-esempio.duckdns.org)
set -euo pipefail

HA_HOST="${HA_HOST:-192.168.1.160}"
HA_USER="${HA_USER:-hassio}"
HA_PASS="${HA_PASS:-}"
PUBLIC_HOST="${PUBLIC_HOST:-casa-esempio.duckdns.org}"
# Vuoto = usa il default hardcoded in start.sh (deve combaciare con
# vc_egress_secret in /config/secrets.yaml).
EGRESS_SECRET="${EGRESS_SECRET:-}"
# RPi: host del broker MQTT (mosquitto locale). Usato per pubblicare
# videocitofono/ha_reload dopo il deploy della card, cosi' i tablet
# ricaricano automaticamente la nuova versione (niente refresh manuale).
RPI_HOST="${RPI_HOST:-192.168.1.185}"
RPI_USER="${RPI_USER:-vinset}"
RPI_PASS="${RPI_PASS:-}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIVEKIT_DIR_LOCAL="$REPO_ROOT/livekit"
WWW_DIR_LOCAL="$REPO_ROOT/www"

if [ ! -d "$LIVEKIT_DIR_LOCAL" ]; then
    echo "ERRORE: $LIVEKIT_DIR_LOCAL non trovata" >&2
    exit 1
fi

ssh_cmd() {
    if [ -n "$HA_PASS" ] && command -v sshpass >/dev/null 2>&1; then
        sshpass -p "$HA_PASS" ssh -o StrictHostKeyChecking=no \
            -o UserKnownHostsFile=/dev/null \
            "${HA_USER}@${HA_HOST}" "$@"
    else
        ssh -o StrictHostKeyChecking=no \
            -o UserKnownHostsFile=/dev/null \
            "${HA_USER}@${HA_HOST}" "$@"
    fi
}

# -O: forza il protocollo SCP legacy. Da OpenSSH 9 scp usa SFTP di default, ma
# l'addon Advanced SSH & Web Terminal non espone il subsystem sftp e la
# copia muore con "subsystem request failed on channel 0".
scp_cmd() {
    if [ -n "$HA_PASS" ] && command -v sshpass >/dev/null 2>&1; then
        sshpass -p "$HA_PASS" scp -O -r -o StrictHostKeyChecking=no \
            -o UserKnownHostsFile=/dev/null "$@"
    else
        scp -O -r -o StrictHostKeyChecking=no \
            -o UserKnownHostsFile=/dev/null "$@"
    fi
}

echo "==> [1/5] copia installer-ha/livekit -> ${HA_HOST}:/tmp/livekit"
# tar via ssh invece di scp -r: il protocollo SCP legacy (l'unico disponibile,
# vedi scp_cmd) rifiuta la sintassi "dir/." con "unexpected filename".
# COPYFILE_DISABLE: evita gli AppleDouble ._* aggiunti da bsdtar su macOS.
ssh_cmd "rm -rf /tmp/livekit && mkdir -p /tmp/livekit"
COPYFILE_DISABLE=1 tar -C "$LIVEKIT_DIR_LOCAL" -czf - . \
  | ssh_cmd "tar -xzf - -C /tmp/livekit && ls /tmp/livekit"

echo "==> [2/5] install config: vista addon SSH + filesystem host"
# Servono DUE destinazioni, perche' l'addon SSH e' un container e non vede il
# filesystem dell'host:
#
#   /addons/livekit/                          -> vista dall'addon SSH. start.sh
#       gira qui dentro e la usa per il sanity check e per il tar di
#       token_issuer/ verso il volume docker.
#   /mnt/data/supervisor/addons/local/livekit -> filesystem HOST. E' il path che
#       il docker daemon risolve per i bind mount di livekit.yaml e Caddyfile.
#
# Un `cp` verso il path host eseguito via ssh_cmd NON funziona: /mnt/data non
# esiste dentro l'addon SSH, quindi mkdir -p creerebbe la cartella nel
# container e i file non arriverebbero mai all'host. Al successivo start i bind
# mount troverebbero sorgenti inesistenti e docker le creerebbe come DIRECTORY
# vuote: mount di una dir su un file -> container in exit 127 ("not a
# directory"). E' esattamente il guasto che ha tenuto giu' lo stack dal
# 2026-06-28. Per scrivere davvero sull'host serve un container con bind mount
# rw sulla cartella di destinazione.
COPY_IMAGE="${COPY_IMAGE:-alpine}"
HOST_ADDON_DIR="/mnt/data/supervisor/addons/local/livekit"

ssh_cmd 'sudo mkdir -p /addons/livekit && sudo cp -r /tmp/livekit/. /addons/livekit/ && sudo chmod +x /addons/livekit/start.sh'
echo "  installato /addons/livekit (vista addon SSH)"

ssh_cmd "sudo docker pull -q ${COPY_IMAGE} >/dev/null 2>&1 || true"
# COPYFILE_DISABLE: su macOS bsdtar aggiunge gli AppleDouble ._* che finirebbero
# nella cartella dei config sull'host.
COPYFILE_DISABLE=1 tar -C "$LIVEKIT_DIR_LOCAL" -czf - livekit.yaml Caddyfile egress.yaml \
  | ssh_cmd "sudo docker run --rm -i -v ${HOST_ADDON_DIR}:/t ${COPY_IMAGE} sh -c '
        rm -rf /t/livekit.yaml /t/Caddyfile /t/egress.yaml
        tar -xzf - -C /t
        rm -f /t/._*
        chown 0:0 /t/livekit.yaml /t/Caddyfile /t/egress.yaml
        chmod 644 /t/livekit.yaml /t/Caddyfile /t/egress.yaml
        test -f /t/livekit.yaml || { echo \"ERRORE: livekit.yaml non e un file regolare sull host\" >&2; exit 1; }
        test -f /t/Caddyfile   || { echo \"ERRORE: Caddyfile non e un file regolare sull host\" >&2; exit 1; }
        test -f /t/egress.yaml || { echo \"ERRORE: egress.yaml non e un file regolare sull host\" >&2; exit 1; }
    '"
echo "  installato ${HOST_ADDON_DIR} (filesystem host, per i bind mount)"

echo "==> [3/5] start containers (redis + livekit + egress + token-issuer + caddy edge)"
# start.sh viene eseguito dalla vista addon SSH: legge i file da /addons/livekit
# e passa a docker i path host via LIVEKIT_DIR (default corretto nello script).
# EGRESS_SECRET: se esportato, sovrascrive il default nello start.sh; deve
# combaciare con vc_egress_secret in /config/secrets.yaml (rest_command HA).
ssh_cmd "sudo PUBLIC_HOST=${PUBLIC_HOST} ${EGRESS_SECRET:+EGRESS_SECRET=$EGRESS_SECRET} /addons/livekit/start.sh"

echo "==> [4/5] deploy frontend asset vc-livekit.js + vc-livekit-call.js -> /config/www/"
# vc-livekit-call.js e' il file canonico della card (UN solo file/risorsa:
# il vecchio duplicato vc-livekit-call-v3.js e' stato rimosso perche'
# poteva vincere la registrazione di customElements e servire codice stale).
for ASSET in vc-livekit.js vc-livekit-call.js; do
    if [ -f "$WWW_DIR_LOCAL/$ASSET" ]; then
        scp_cmd "$WWW_DIR_LOCAL/$ASSET" "${HA_USER}@${HA_HOST}:/tmp/$ASSET"
        ssh_cmd "sudo install -m 644 -o root -g root /tmp/$ASSET /config/www/$ASSET"
        echo "  installato /config/www/$ASSET"
    else
        echo "  (skip: $WWW_DIR_LOCAL/$ASSET non trovato)"
    fi
done

# Registra vc-livekit-call.js come Lovelace resource module (idempotente).
# Necessario perche' la view "Conversazione" usa custom:vc-livekit-call,
# che senza registrazione resource non viene definito a livello globale.
echo "==> [4b/5] registra /local/vc-livekit-call.js come Lovelace resource"
ssh_cmd 'sudo python3 -c "
import json, time, uuid
p = \"/config/.storage/lovelace_resources\"
with open(p) as f: data = json.load(f)
items = data[\"data\"][\"items\"]
items = [i for i in items if \"vc-livekit-call.js\" not in i.get(\"url\",\"\")]
ts = int(time.time())
items.append({
  \"id\": uuid.uuid4().hex,
  \"url\": f\"/local/vc-livekit-call.js?v={ts}\",
  \"type\": \"module\"
})
data[\"data\"][\"items\"] = items
with open(p, \"w\") as f: json.dump(data, f, indent=2)
print(\"OK lovelace_resources items=\", len(items))
"'

echo "==> [4c/5] upsert view Lovelace 'Conversazione' (path=conversazione)"
ssh_cmd 'sudo python3 -c "
import json
p = \"/config/.storage/lovelace.lovelace\"
with open(p) as f: data = json.load(f)
views = data[\"data\"][\"config\"][\"views\"]
new_view = {
  \"title\": \"Conversazione\",
  \"path\": \"conversazione\",
  \"subview\": True,
  \"icon\": \"mdi:phone-in-talk\",
  \"theme\": None,
  \"panel\": True,
  \"cards\": [
    {\"type\": \"custom:vc-livekit-call\", \"audio_only\": False, \"room\": \"videocitofono\", \"identity_prefix\": \"ha\", \"open_door_script\": \"script.videocitofono_apri_porta\", \"hangup_script\": \"script.videocitofono_chiudi\"}
  ]
}
existing = [i for i,v in enumerate(views) if v.get(\"path\")==\"conversazione\"]
if existing:
  for i in existing: views[i] = new_view
  print(\"REPLACED conversazione views idx\", existing)
else:
  views.append(new_view)
  print(\"APPENDED conversazione, total=\", len(views))
with open(p, \"w\") as f: json.dump(data, f, indent=2, ensure_ascii=False)
"'

echo "==> [4d/5] auto-reload tablet: publish videocitofono/ha_reload (RPi broker)"
# Dopo aggiornamento card: pubblica ha_reload cosi' i frontend (tablet/PC)
# eseguono caches.delete + location.reload(true) e prendono la nuova ?v.
# Evita il bug ricorrente della card vecchia rimasta in cache.
if [ -n "$RPI_PASS" ] && command -v sshpass >/dev/null 2>&1; then
    sshpass -p "$RPI_PASS" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        "${RPI_USER}@${RPI_HOST}" 'mosquitto_pub -h localhost -p 1883 -t videocitofono/ha_reload -m reload' \
        && echo "  ha_reload pubblicato (via RPi ${RPI_HOST})" || echo "  WARN: publish ha_reload fallito"
elif command -v mosquitto_pub >/dev/null 2>&1; then
    mosquitto_pub -h "$RPI_HOST" -p 1883 -t videocitofono/ha_reload -m reload \
        && echo "  ha_reload pubblicato (diretto ${RPI_HOST})" || echo "  WARN: publish ha_reload fallito"
else
    echo "  (skip ha_reload: imposta RPI_PASS+sshpass oppure installa mosquitto_pub)"
fi

echo "==> [5/5] verifiche health"
echo "--- LAN (no TLS) ---"
ssh_cmd 'curl -sS http://127.0.0.1:8081/health || true'
echo ""
ssh_cmd 'curl -sS http://127.0.0.1:7880/ -o /dev/null -w "livekit-server status=%{http_code}\n" || true'
echo ""
echo "--- Edge Caddy (TLS) ---"
ssh_cmd "curl -sS -k https://127.0.0.1/livekit-token/health || true"
echo ""
echo "--- WAN (atteso: stessi risultati se port-forward 443 ok) ---"
echo "    (eseguire dal Mac:  curl https://${PUBLIC_HOST}/livekit-token/health)"
echo ""
echo "==> done."
echo ""
echo "    Tablet di casa: cambia URL HA in https://${PUBLIC_HOST}"
echo "    Telefono fuori casa: stessa URL via app HA Companion."
echo ""
echo "    Diagnostica frontend: apri https://${PUBLIC_HOST}, console:"
echo "      vcLK.diagnostics()  -> { secure: true, hasGUM: true, ... }"
