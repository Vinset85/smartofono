#!/usr/bin/env bash
# Diagnostica PN532 / nfcpy sul videocitofono (eseguire sul Pi).
set -euo pipefail

echo "=== Nota ==="
echo "Se il modulo funzionava prima senza modifiche ai ponti SET1/SET2, non saldare nulla."
echo "Fermare videocitofono.service, scollegare USB 10 s, poi eseguire questo script."
echo

echo "=== USB ==="
lsusb 2>/dev/null || true
echo
echo "=== Serial ==="
ls -la /dev/ttyUSB* 2>/dev/null || echo "(nessun ttyUSB)"
echo
echo "=== I2C (bus 1 e 10) ==="
for b in 1 10; do
  if [[ -e "/dev/i2c-${b}" ]]; then
    echo "--- i2c-${b} ---"
    i2cdetect -y "$b" 2>/dev/null || true
  fi
done
echo
echo "=== libnfc ==="
if command -v nfc-list >/dev/null 2>&1; then
  nfc-list 2>&1 || true
else
  echo "nfc-list non installato"
fi
echo
echo "=== Attesa stabilizzazione USB (3 s) ==="
sleep 3

echo "=== nfcpy probe (venv app) ==="
PYBIN=/opt/videocitofono/venv/bin/python3
if [[ -x "${PYBIN}" ]]; then
  "${PYBIN}" - <<'PY'
import sys
sys.path.insert(0, "/opt/videocitofono/app")
from modules.nfc_reader import (
    DEFAULT_DEVICE_CANDIDATES, probe_nfc_device, uart_pn532_responds)

for p in DEFAULT_DEVICE_CANDIDATES:
    if p.startswith("tty:"):
        ok = uart_pn532_responds(p)
        print(f"uart_pn532_responds({p}): {ok}")
found = probe_nfc_device(DEFAULT_DEVICE_CANDIDATES)
print("probe_nfc_device:", found or "(nessuno)")
PY
else
  echo "venv non trovato: ${PYBIN}"
fi
