#!/usr/bin/env bash
# Imposta IP statico 192.168.1.185 su eth0 (NetworkManager). Eseguire SUL Pi.
set -euo pipefail

CONN="${NM_CONN_NAME:-Connessione via cavo 1}"
ADDR="${STATIC_IP:-192.168.1.185/24}"
GW="${STATIC_GW:-192.168.1.254}"
DNS="${STATIC_DNS:-192.168.1.254 1.1.1.1}"

want_ip="${ADDR%%/*}"
cur_ip="$(ip -4 -br addr show eth0 2>/dev/null | awk '{print $3}' | cut -d/ -f1 || true)"
if [[ "${FORCE_STATIC_IP:-0}" != "1" && "$cur_ip" == "$want_ip" ]]; then
  echo "IP già ${ADDR} su eth0, skip nmcli con up"
  exit 0
fi

echo "==> Static IP ${ADDR} gateway ${GW} su '${CONN}'"
sudo nmcli con mod "$CONN" \
  ipv4.method manual \
  ipv4.addresses "$ADDR" \
  ipv4.gateway "$GW" \
  ipv4.dns "$DNS" \
  ipv4.ignore-auto-dns false
sudo nmcli con up "$CONN"
ip -br a show eth0
ip route | head -3
echo "==> OK"
