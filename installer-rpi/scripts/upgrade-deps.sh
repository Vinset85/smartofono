#!/usr/bin/env bash
# Aggiorna pip e librerie Python del venv videocitofono.
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/videocitofono}"
VENV="${APP_ROOT}/venv"
PIP="${VENV}/bin/pip"
APP="${APP_ROOT}/app"

if [[ ! -x "${PIP}" ]]; then
  echo "venv mancante: eseguire install.sh prima" >&2
  exit 1
fi

echo "==> Upgrade pip tooling"
"${PIP}" install --upgrade pip wheel setuptools

echo "==> Upgrade requirements core"
"${PIP}" install --upgrade -r "${APP}/requirements.txt"

if [[ -f "${APP}/requirements-face.txt" ]]; then
  echo "==> Upgrade requirements face (best-effort)"
  "${PIP}" install --upgrade -r "${APP}/requirements-face.txt" || \
    echo "WARN: upgrade face deps fallito (arch/dlib?)"
fi

echo "==> Outdated residui (upgrade venv-only, uno per uno)"
while IFS= read -r pkg; do
  [[ -z "${pkg}" ]] && continue
  loc="$("${PIP}" show "${pkg}" 2>/dev/null | awk -F': ' '/^Location:/ {print $2}')"
  if [[ "${loc}" != *"${VENV}/"* ]]; then
    continue
  fi
  if [[ "${pkg}" == "bcrypt" || "${pkg}" == "numpy" || "${pkg}" == "scipy" || "${pkg}" == "pydantic-core" ]]; then
    continue
  fi
  # Catena InsightFace/ArcFace: versioni piu' nuove rompono l'import
  # (albumentations<->albucore, pydantic<->pydantic-core). NON aggiornare.
  if [[ "${pkg}" == "albumentations" || "${pkg}" == "albucore" || "${pkg}" == "pydantic" ]]; then
    continue
  fi
  if [[ "${pkg}" == opencv-python || "${pkg}" == opencv-python-headless ]]; then
    continue
  fi
  echo "    upgrade ${pkg}"
  "${PIP}" install --upgrade "${pkg}" || echo "WARN: skip ${pkg}"
done < <("${PIP}" list --outdated 2>/dev/null | awk 'NR>2 && NF>=4 {print $1}')

echo "==> Outdated finali"
"${PIP}" list --outdated || true

echo "==> Ripristino pin numpy 1.x + opencv compatibile (picamera2/simplejpeg apt)"
"${PIP}" install --upgrade --force-reinstall \
  "numpy>=1.24.2,<1.27" \
  "opencv-python-headless>=4.10.0,<4.14" \
  "opencv-python>=4.10.0,<4.14"

echo "==> Fatto. Riavviare: sudo systemctl restart videocitofono.service"
