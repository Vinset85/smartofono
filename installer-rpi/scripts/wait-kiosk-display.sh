#!/bin/bash
# Attende la sessione labwc dell'utente kiosk (non il greeter LightDM).
# Senza questo, Kivy/SDL2 parte su graphical.target e puo' far crashare labwc
# (DRM/GBM busy) -> LightDM mostra la schermata di login.
set -euo pipefail
UID_NUM="${KIOSK_UID:-1000}"
RUNTIME="/run/user/${UID_NUM}"
TIMEOUT="${KIOSK_WAIT_SEC:-60}"

for ((i = 1; i <= TIMEOUT; i++)); do
  if [[ -S "${RUNTIME}/wayland-0" ]] && pgrep -u "${UID_NUM}" -x labwc >/dev/null; then
    sleep 2
    if [[ -S "${RUNTIME}/wayland-0" ]] && pgrep -u "${UID_NUM}" -x labwc >/dev/null; then
      echo "kiosk display ready (${i}s)"
      exit 0
    fi
  fi
  sleep 1
done
echo "timeout ${TIMEOUT}s: labwc utente ${UID_NUM} non pronto" >&2
exit 1
