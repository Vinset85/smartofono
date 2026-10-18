#!/usr/bin/env bash
# Reset software del CH340 (PN532 USB) — solo il lettore NFC, non il touch.
# Il touch (1a86:e5e3 su usb 3-1) condivede alimentazione/hub interno: un
# unbind della porta USB padre del CH340 può far fallire l'enumerazione touch.
set -euo pipefail

MODE="${1:-recover}"
BOOT_DELAY_SEC="${BOOT_DELAY_SEC:-20}"
CH341_SLEEP="${CH341_SLEEP:-2}"
WAIT_TTY_SEC="${WAIT_TTY_SEC:-50}"

log() { echo "[nfc-usb-reset] $*"; }

wait_ch340_tty() {
  local i
  for ((i = 1; i <= WAIT_TTY_SEC; i++)); do
    if lsusb -d 1a86:7523 >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

find_ch340_usb_id() {
  local d v p
  for d in /sys/bus/usb/devices/*; do
    [[ -f "${d}/idVendor" && -f "${d}/idProduct" ]] || continue
    v=$(<"${d}/idVendor")
    p=$(<"${d}/idProduct")
    if [[ "${v}" == "1a86" && "${p}" == "7523" ]]; then
      basename "${d}"
      return 0
    fi
  done
  return 1
}

touch_present() {
  lsusb -d 1a86:e5e3 >/dev/null 2>&1
}

recover_touch_port() {
  if touch_present; then
    return 0
  fi
  log "touch assente (1a86:e5e3), ripristino porta usb 3-1"
  if [[ ! -w /sys/bus/usb/drivers/usb/unbind ]]; then
    return 1
  fi
  if [[ -d /sys/bus/usb/devices/3-1 ]]; then
    echo "3-1" > /sys/bus/usb/drivers/usb/unbind 2>/dev/null || true
    sleep 3
    echo "3-1" > /sys/bus/usb/drivers/usb/bind 2>/dev/null || true
    sleep 4
  fi
  if touch_present; then
    log "touch ripristinato"
    return 0
  fi
  log "touch ancora assente"
  return 1
}

find_ch340_dwc3() {
  local id path base
  id=$(find_ch340_usb_id) || return 1
  path=$(readlink -f "/sys/bus/usb/devices/${id}") || return 1
  while [[ -n "${path}" && "${path}" != "/" ]]; do
    base=$(basename "${path}")
    if [[ "${base}" == *.usb ]]; then
      echo "${base}"
      return 0
    fi
    path=$(dirname "${path}")
  done
  return 1
}

dwc3_has_touch() {
  local dev="$1" d v p
  [[ -n "${dev}" && -d "/sys/bus/platform/drivers/dwc3/${dev}" ]] || return 1
  while IFS= read -r d; do
    [[ -f "${d}/idVendor" && -f "${d}/idProduct" ]] || continue
    v=$(<"${d}/idVendor")
    p=$(<"${d}/idProduct")
    if [[ "${v}" == "1a86" && "${p}" == "e5e3" ]]; then
      return 0
    fi
  done < <(find "/sys/bus/platform/drivers/dwc3/${dev}" -maxdepth 6 -type d 2>/dev/null)
  return 1
}

# Reset DWC3 del solo controller del CH340 (1f00200000.usb).
# Equivalente software dello stacco USB: il PN532 perde HSU appeso.
# Non tocca 1f00300000.usb (touch).
dwc3_reset_ch340_controller() {
  local dev i
  dev=$(find_ch340_dwc3) || {
    if [[ -d /sys/bus/platform/drivers/dwc3/1f00200000.usb ]]; then
      dev="1f00200000.usb"
    else
      return 1
    fi
  }
  if [[ "${dev}" == "1f00300000.usb" ]] || dwc3_has_touch "${dev}"; then
    log "dwc3 ${dev} ha il touch — skip"
    return 1
  fi
  if [[ ! -w /sys/bus/platform/drivers/dwc3/unbind ]]; then
    return 1
  fi
  log "dwc3 unbind/bind ${dev} (controller CH340)"
  echo "${dev}" > /sys/bus/platform/drivers/dwc3/unbind 2>/dev/null || true
  sleep 2
  echo "${dev}" > /sys/bus/platform/drivers/dwc3/bind 2>/dev/null || true
  for ((i = 1; i <= 8; i++)); do
    if [[ -e /sys/bus/platform/drivers/dwc3/${dev} ]] && lsusb -d 1a86:7523 >/dev/null 2>&1; then
      sleep 1
      return 0
    fi
    if [[ ! -e /sys/bus/platform/drivers/dwc3/${dev} ]]; then
      echo "${dev}" > /sys/bus/platform/drivers/dwc3/bind 2>/dev/null || true
    fi
    sleep 1
  done
  [[ -e /sys/bus/platform/drivers/dwc3/${dev} ]] || \
    echo "${dev}" > /sys/bus/platform/drivers/dwc3/bind 2>/dev/null || true
  lsusb -d 1a86:7523 >/dev/null 2>&1
}

# Compat: hard/power usano dwc3 (non xhci-hcd, il bind a volte fallisce).
xhci_reset_ch340_controller() {
  dwc3_reset_ch340_controller
}

# GPIO42 USB_VBUS_EN e' condiviso con il touch: non usarlo.
vbus_power_cycle() {
  log "skip VBUS GPIO42 (spegnerebbe il touch)"
  return 1
}

# Power-cycle reale della porta USB del CH340 via uhubctl (se disponibile).
# NB: su RPi5 uhubctl NON taglia VBUS. Usiamo xhci + GPIO VBUS_EN.
uhubctl_power_cycle_ch340() {
  return 1
}

# Reset leggero: solo CH340 (mai unbind della porta USB padre del device).
usb_reset_ch340() {
  local id devpath
  id=$(find_ch340_usb_id) || return 1
  log "reset CH340 (${id})"

  # Tentativo piu' forte per primo: power-cycle porta via uhubctl (best-effort).
  if uhubctl_power_cycle_ch340; then
    wait_ch340_tty || true
    id=$(find_ch340_usb_id) || return 1
  fi

  if command -v usbreset >/dev/null 2>&1; then
    devpath=$(lsusb -d 1a86:7523 | awk '{printf "/dev/bus/usb/%s/%s", $2, $4}' | tr -d ':')
    if [[ -n "${devpath}" && -e "${devpath}" ]]; then
      log "usbreset ${devpath}"
      usbreset "${devpath}" 2>/dev/null || true
      sleep 2
    fi
  fi

  if [[ -w /sys/bus/usb/drivers/ch341/unbind && -d /sys/bus/usb/devices/${id}:1.0 ]]; then
    log "ch341 unbind/bind ${id}:1.0"
    echo "${id}:1.0" > /sys/bus/usb/drivers/ch341/unbind 2>/dev/null || true
    sleep "${CH341_SLEEP}"
    echo "${id}:1.0" > /sys/bus/usb/drivers/ch341/bind 2>/dev/null || true
    sleep 3
  fi

  # CH340 e' su bus USB separato dal touch (3-1): unbind completo solo a cold boot.
  if [[ "${MODE}" == "boot" && -w /sys/bus/usb/drivers/usb/unbind ]]; then
    log "usb unbind/bind ${id}"
    echo "${id}" > /sys/bus/usb/drivers/usb/unbind 2>/dev/null || true
    sleep 3
    echo "${id}" > /sys/bus/usb/drivers/usb/bind 2>/dev/null || true
    sleep 4
  fi
  return 0
}

libnfc_wake() {
  # Non usare libnfc (stato incoerente per nfcpy). Wake HSU: DTR/RTS +
  # preamble + GetFirmwareVersion, poi nfcpy apre la seriale.
  log "wake UART PN532 (DTR/RTS, no libnfc)"
  /opt/videocitofono/venv/bin/python3 - <<'PY' || true
import time, os
try:
    import serial
except ImportError:
    raise SystemExit(0)
dev = "/dev/ttyUSB0"
if not os.path.exists(dev):
    raise SystemExit(0)
body = bytes([0xD4, 0x02])
ln = len(body) + 1
frame = (bytes([0x00, 0x00, 0xFF, ln, (-ln) & 0xFF])
         + body + bytes([(-sum(body)) & 0xFF, 0x00]))
pols = ((False, False, True, True), (True, True, False, False),
        (False, True, True, False), (True, False, False, True))
for dtr0, rts0, dtr1, rts1 in pols:
    try:
        with serial.Serial(dev, baudrate=115200, timeout=0.4) as ser:
            ser.dtr = dtr0
            ser.rts = rts0
            time.sleep(0.25)
            ser.dtr = dtr1
            ser.rts = rts1
            time.sleep(0.2)
            try:
                ser.send_break(duration=0.08)
            except Exception:
                pass
            ser.reset_input_buffer()
            ser.write(b"\x55" * 32)
            time.sleep(0.08)
            ser.reset_input_buffer()
            ser.write(frame)
            time.sleep(0.25)
            rx = ser.read(64)
            if len(rx) >= 7 and 0xD5 in rx:
                raise SystemExit(0)
    except SystemExit:
        raise
    except Exception:
        pass
    time.sleep(0.3)
PY
}

disable_ch340_autosuspend() {
  local d v p ctrl auto
  for d in /sys/bus/usb/devices/*; do
    [[ -f "${d}/idVendor" && -f "${d}/idProduct" ]] || continue
    v=$(<"${d}/idVendor")
    p=$(<"${d}/idProduct")
    if [[ "${v}" == "1a86" && "${p}" == "7523" ]]; then
      ctrl="${d}/power/control"
      auto="${d}/power/autosuspend"
      if [[ -w "${ctrl}" ]]; then
        echo on >"${ctrl}" 2>/dev/null || true
      fi
      if [[ -w "${auto}" ]]; then
        echo -1 >"${auto}" 2>/dev/null || true
      fi
      log "autosuspend CH340 disabilitato ($(basename "${d}"))"
      return 0
    fi
  done
  return 1
}

if [[ "${MODE}" == "boot" ]]; then
  log "attesa ${BOOT_DELAY_SEC}s (enumerazione touch prima del reset NFC)"
  sleep "${BOOT_DELAY_SEC}"
fi

if ! wait_ch340_tty; then
  log "CH340 assente — skip reset NFC"
  exit 0
fi

case "${MODE}" in
  power|hard)
    # Mai VBUS: GPIO42 e' condiviso col touch. Solo DWC3 del bus CH340.
    dwc3_reset_ch340_controller || usb_reset_ch340 || true
    ;;
  *)
    usb_reset_ch340 || log "reset CH340 non riuscito (continuo)"
    ;;
esac

if ! wait_ch340_tty; then
  log "CH340 non tornato — skip wake"
  exit 0
fi

# Non toccare il touch e non pulse DTR (tiene il PN532 in reset).
disable_ch340_autosuspend || true
date -Iseconds | tee /run/videocitofono-nfc-ready >/dev/null 2>&1 || true
log "ok (${MODE})"
exit 0
