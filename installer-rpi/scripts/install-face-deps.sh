#!/usr/bin/env bash
# Dipendenze riconoscimento facciale (ArcFace + liveness dlib).
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/videocitofono}"
VENV="${APP_ROOT}/venv/bin/pip"
DATA="${APP_ROOT}/data"
PRED="${DATA}/shape_predictor_68_face_landmarks.dat"
PRED_URL="https://github.com/davisking/dlib-models/raw/master/shape_predictor_68_face_landmarks.dat.bz2"

echo "==> Face deps"
if [[ "${SKIP_APT:-0}" != "1" ]]; then
  apt-get install -y --no-install-recommends \
    libopenblas-dev liblapack-dev cmake libjpeg-dev zlib1g-dev \
    libatlas-base-dev libdlib-dev 2>/dev/null || true
fi

if [[ "${FACE_UPGRADE:-0}" == "1" ]]; then
  "${VENV}" install --upgrade pip wheel setuptools
  "${VENV}" install --upgrade -r "${APP_ROOT}/app/requirements-face.txt" || {
    echo "WARN: insightface/onnxruntime non installati (arch non supportata?)"
  }
else
  "${VENV}" install -r "${APP_ROOT}/app/requirements-face.txt" || {
    echo "WARN: insightface/onnxruntime non installati (arch non supportata?)"
  }
fi

if [[ ! -f "${PRED}" ]]; then
  mkdir -p "${DATA}"
  tmp="$(mktemp)"
  curl -fsSL "${PRED_URL}" -o "${tmp}.bz2"
  bunzip2 -f "${tmp}.bz2"
  mv "${tmp}" "${PRED}"
  echo "    shape_predictor_68 scaricato"
fi

# Pre-cache modelli ArcFace (buffalo_sc) al primo import
"${APP_ROOT}/venv/bin/python3" <<'PY' || true
import os
os.environ.setdefault("INSIGHTFACE_HOME", "/opt/videocitofono/data/insightface")
try:
    from insightface.app import FaceAnalysis
    app = FaceAnalysis(name="buffalo_sc", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=0, det_size=(320, 320))
    print("ArcFace buffalo_sc pronto")
except Exception as e:
    print("ArcFace preload skip:", e)
PY

APP_USER="${APP_USER:-vinset}"
chown -R "${APP_USER}:${APP_USER}" "${APP_ROOT}/venv" "${APP_ROOT}/data" 2>/dev/null || true

echo "==> Face deps completato"
