#!/bin/bash
# Se LightDM e' caduto sul greeter (login), ritenta l'autologin.
# Non tocca una sessione labwc utente gia' attiva.
# Pensato per girare da timer (ogni ~45s): se il kiosk e' ok esce subito.
set -euo pipefail
STAMP=/run/videocitofono-kiosk-guard
MAX="${KIOSK_GREETER_RETRY:-3}"
n=0
if [[ -f "${STAMP}" ]]; then
  n=$(cat "${STAMP}" 2>/dev/null || echo 0)
fi

if pgrep -u 1000 -x labwc >/dev/null && [[ -S /run/user/1000/wayland-0 ]]; then
  rm -f "${STAMP}"
  echo "sessione kiosk ok"
  exit 0
fi

if pgrep -f 'labwc-greeter|pi-greeter' >/dev/null; then
  n=$((n + 1))
  echo "${n}" >"${STAMP}"
  if [[ "${n}" -gt "${MAX}" ]]; then
    echo "troppi retry greeter (${n}/${MAX})" >&2
    exit 1
  fi
  echo "greeter rilevato: restart lightdm (${n}/${MAX})"
  systemctl restart lightdm.service
  exit 0
fi

echo "nessuna sessione labwc ne greeter; attendo il prossimo timer"
exit 0
