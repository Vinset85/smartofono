#!/usr/bin/env bash
# Installer componenti Home Assistant videocitofono.
#
# Da eseguire sull'host di Home Assistant, dall'addon "Advanced SSH & Web
# Terminal" oppure via `ssh` con la cartella del progetto raggiungibile:
#
#   cd installer-ha && ./install.sh
#
# Copia i package, i pyscript, le card e i default. Non riavvia HA da solo.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
HA_CONFIG="${HA_CONFIG:-/config}"

echo "==> Videocitofono HA installer"
echo "    config: ${HA_CONFIG}"

if [[ ! -d "${HA_CONFIG}" ]]; then
  echo "ERRORE: ${HA_CONFIG} non esiste. Sei sull'host di Home Assistant?" >&2
  echo "        Se la config sta altrove: HA_CONFIG=/percorso ./install.sh" >&2
  exit 1
fi

install -d "${HA_CONFIG}/packages" "${HA_CONFIG}/pyscript" "${HA_CONFIG}/www"

for f in configuration.yaml.fixed automations.yaml.fixed scripts.yaml.fixed scenes.yaml; do
  src="${ROOT}/packages/${f}"
  dst="${HA_CONFIG}/packages/${f%.fixed}"
  if [[ -f "${src}" ]]; then
    cp "${src}" "${dst}"
    echo "    packages/${f%.fixed}"
  fi
done

# Niente elenchi di file scritti a mano: si scollavano da quello che c'e'
# davvero nelle cartelle, e il risultato era una card che la dashboard
# chiamava senza che nessuno l'avesse copiata.
for py in "${ROOT}"/pyscript/*.py; do
  [[ -f "${py}" ]] || continue
  cp "${py}" "${HA_CONFIG}/pyscript/"
  echo "    pyscript/$(basename "${py}")"
done

for asset in "${ROOT}"/www/*; do
  [[ -f "${asset}" ]] || continue
  cp "${asset}" "${HA_CONFIG}/www/"
  echo "    www/$(basename "${asset}")"
done

if [[ -f "${ROOT}/config/videocitofono_defaults.json" ]]; then
  cp "${ROOT}/config/videocitofono_defaults.json" "${HA_CONFIG}/videocitofono_defaults.json"
  echo "    videocitofono_defaults.json"
fi

install -d "${HA_CONFIG}/lovelace"
for frag in "${ROOT}"/lovelace/videocitofono-*; do
  [[ -f "${frag}" ]] || continue
  cp "${frag}" "${HA_CONFIG}/lovelace/"
  echo "    lovelace/$(basename "${frag}")"
done

install -d "${HA_CONFIG}/themes"
for tema in "${ROOT}"/themes/*.yaml; do
  [[ -f "${tema}" ]] || continue
  cp "${tema}" "${HA_CONFIG}/themes/"
  echo "    themes/$(basename "${tema}")"
done

echo
if [[ ! -f "${HA_CONFIG}/secrets.yaml" ]]; then
  echo "ATTENZIONE: ${HA_CONFIG}/secrets.yaml non esiste."
  echo "    I package appena copiati usano !secret e Home Assistant non"
  echo "    ripartira' senza. Parti da secrets.yaml.example:"
  echo "    cp ${ROOT}/secrets.yaml.example ${HA_CONFIG}/secrets.yaml"
else
  mancanti=()
  while read -r chiave; do
    grep -q "^${chiave}:" "${HA_CONFIG}/secrets.yaml" || mancanti+=("${chiave}")
  done < <(grep -hoE "!secret [a-z0-9_]+" "${HA_CONFIG}"/packages/*.yaml 2>/dev/null \
           | awk '{print $2}' | sort -u)
  if [[ ${#mancanti[@]} -gt 0 ]]; then
    echo "ATTENZIONE: in secrets.yaml mancano queste chiavi, HA non ripartira':"
    printf '    %s\n' "${mancanti[@]}"
  fi
fi

echo
echo "==> Fatto. Ora: Impostazioni > Sistema > Riavvia Home Assistant."
echo "    Le card custom vanno aggiunte in Impostazioni > Dashboard >"
echo "    Risorse, come /local/<nome>.js (modulo JavaScript)."
