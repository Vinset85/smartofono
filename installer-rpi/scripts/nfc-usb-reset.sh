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

# Power-cycle reale della porta USB del CH340 via uhubctl (se disponibile).
# NB: su RPi5 alcuni hub espongono il flag ppps ma NON tagliano davvero VBUS:
# in quel caso questo equivale a una ri-enumerazione (come unbind/bind) e non
# resetta il PN532 — l'unico reset hardware certo resta lo scollegamento fisico.
# Best-effort: mai fatale, e tocca solo la porta del CH340 (non il touch).
uhubctl_power_cycle_ch340() {
  command -v uhubctl >/dev/null 2>&1 || return 1
  local id bus hubpath loc port
  id=$(find_ch340_usb_id) || return 1
  # id es. "1-1" (porta su root hub) oppure "1-1.2" (hub annidato).
  bus="${id%%-*}"
  hubpath="${id#*-}"
  if [[ "${hubpath}" == *.* ]]; then
    port="${hubpath##*.}"
    loc="${bus}-${hubpath%.*}"
  else
    port="${hubpath}"
    loc="${bus}"
  fi
  log "uhubctl power-cycle CH340 (loc=${loc} port=${port})"
  uhubctl -l "${loc}" -p "${port}" -a cycle -d 2 >/dev/null 2>&1 || true
  sleep 2
  return 0
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
  # Non usare libnfc: lascia il PN532 in stato incoerente per nfcpy.
  # Wake solo via sequenza UART (stesso protocollo GetFirmwareVersion).
  log "wake UART PN532 (no libnfc)"
  /opt/videocitofono/venv/bin/python3 - <<'PY' || true
import time
try:
    import serial
except ImportError:
    raise SystemExit(0)
dev = "/dev/ttyUSB0"
if not __import__("os").path.exists(dev):
    raise SystemExit(0)
for _ in range(4):
    try:
        with serial.Serial(dev, baudrate=115200, timeout=0.5) as ser:
            ser.dtr = False
            ser.rts = False
            time.sleep(0.05)
            ser.dtr = True
            time.sleep(0.15)
            ser.reset_input_buffer()
            ser.write(b"\x55" * 10)
            time.sleep(0.05)
            body = bytes([0xD4, 0x02])
            ln = len(body) + 1
            frame = (bytes([0x00, 0x00, 0xFF, ln, (-ln) & 0xFF])
                     + body + bytes([(-sum(body)) & 0xFF, 0x00]))
            ser.write(frame)
            time.sleep(0.25)
            rx = ser.read(32)
            if len(rx) >= 7 and 0xD5 in rx:
                raise SystemExit(0)
    except Exception:
        pass
    time.sleep(0.5)
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
  recover_touch_port || true
  exit 0
fi

usb_reset_ch340 || log "reset CH340 non riuscito (continuo)"

if ! wait_ch340_tty; then
  log "CH340 non tornato — skip wake"
  recover_touch_port || true
  exit 0
fi

# libnfc e nfcpy non devono essere aperti insieme; wake solo a fine script (porta libera).
libnfc_wake
recover_touch_port || true
disable_ch340_autosuspend || true
date -Iseconds | tee /run/videocitofono-nfc-ready >/dev/null 2>&1 || true
log "ok (${MODE})"
exit 0
