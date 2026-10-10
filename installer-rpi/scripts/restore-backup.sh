#!/usr/bin/env bash
# Restore selettivo da backup vc-backup-*.tar.gz
# Uso: sudo ./scripts/restore-backup.sh /opt/videocitofono/backups/vc-backup-YYYYMMDD-HHMMSS.tar.gz
set -euo pipefail

ARCHIVE="${1:-}"
ROOT="${APP_ROOT:-/opt/videocitofono}"

if [[ -z "${ARCHIVE}" || ! -f "${ARCHIVE}" ]]; then
  echo "Uso: $0 /path/vc-backup-....tar.gz" >&2
  exit 1
fi

echo "==> Restore da ${ARCHIVE} -> ${ROOT}"
tar -tzf "${ARCHIVE}" | head -20
read -r -p "Confermi restore? [y/N] " ans
[[ "${ans}" == "y" || "${ans}" == "Y" ]] || exit 0

TMP="$(mktemp -d)"
tar -xzf "${ARCHIVE}" -C "${TMP}"
rsync -a "${TMP}/" "${ROOT}/"
rm -rf "${TMP}"
echo "==> Restore completato. Riavviare videocitofono.service"
