#!/usr/bin/env bash
# Imposta IP statico 192.168.1.185 su eth0 (NetworkManager). Eseguire SUL Pi.
set -euo pipefail

CONN="${NM_CONN_NAME:-Connessione via cavo 1}"
ADDR="${STATIC_IP:-192.168.1.185/24}"
GW="${STATIC_GW:-192.168.1.254}"
DNS="${STATIC_DNS:-192.168.1.254 1.1.1.1}"

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
