#!/usr/bin/env bash
# Riduce servizi e carico di sistema per RPi in scatola (gestione termica).
# Eseguire con: sudo ./scripts/tune-system-thermal.sh
set -euo pipefail

echo "==> Videocitofono: tune termico sistema"

DISABLE=(
  cups.service
  cups-browsed.service
  mediamtx.service
  glamor-test.service
  rp1-test.service
  ModemManager.service
  triggerhappy.service
  wayvnc-control.service
  hciuart.service
  dphys-swapfile.service
)

for unit in "${DISABLE[@]}"; do
  if systemctl list-unit-files "$unit" &>/dev/null; then
    systemctl disable --now "$unit" 2>/dev/null || true
    echo "    disabilitato: $unit"
  fi
done

# go2rtc: avviato solo durante chiamata (LiveKit); motion usa picamera2.
if systemctl list-unit-files go2rtc.service &>/dev/null; then
  systemctl disable go2rtc.service 2>/dev/null || true
  systemctl stop go2rtc.service 2>/dev/null || true
  echo "    go2rtc.service disabilitato (on-demand via app)"
fi

# Meno swap = meno I/O SD e picchi termici.
SYSCTL=/etc/sysctl.d/99-videocitofono-thermal.conf
cat >"$SYSCTL" <<'EOF'
vm.swappiness=10
EOF
sysctl -p "$SYSCTL" 2>/dev/null || true
echo "    sysctl vm.swappiness=10"

UDEV_NFC="/etc/udev/rules.d/99-videocitofono-nfc-ch340.rules"
if [[ -f "${UDEV_NFC}" ]]; then
  udevadm control --reload-rules 2>/dev/null || true
  udevadm trigger --subsystem-match=usb --attr-match=idVendor=1a86 --attr-match=idProduct=7523 2>/dev/null || true
  echo "    udev CH340 autosuspend off (reload)"
fi
for d in /sys/bus/usb/devices/*; do
  [[ -f "${d}/idVendor" && -f "${d}/idProduct" ]] || continue
  v=$(<"${d}/idVendor")
  p=$(<"${d}/idProduct")
  if [[ "${v}" == "1a86" && "${p}" == "7523" ]]; then
    [[ -w "${d}/power/control" ]] && echo on >"${d}/power/control" 2>/dev/null || true
    [[ -w "${d}/power/autosuspend" ]] && echo -1 >"${d}/power/autosuspend" 2>/dev/null || true
    echo "    CH340 power: on, autosuspend=-1"
    break
  fi
done

GOV=/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
if [ -f "$GOV" ]; then
  echo ondemand >"$GOV" 2>/dev/null || true
  echo "    CPU governor: $(cat "$GOV" 2>/dev/null || echo n/a)"
fi

# Tastiera virtuale on-screen non necessaria in kiosk.
pkill -9 squeekboard 2>/dev/null || true

echo "==> Tune termico completato"
