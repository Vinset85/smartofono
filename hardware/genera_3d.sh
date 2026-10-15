#!/bin/bash
# Produce i render e gli STL del videocitofono da incasso partendo dal modello
# parametrico. Richiede OpenSCAD (brew install --cask openscad@snapshot).
#
# Uso: ./genera_3d.sh
set -euo pipefail

cd "$(dirname "$0")"
SCAD=${SCAD:-openscad}
MODELLO=cad/videocitofono.scad

mkdir -p anteprime stl

# Le quote del 3D arrivano dal file Python: rigenerale prima di tutto.
python3 parametri.py >/dev/null

# L'inquadratura usa --viewall con distanza 0: OpenSCAD calcola da se' la
# distanza giusta e restano da scegliere solo gli angoli di rotazione.
# --render calcola le differenze invece di disegnarle in anteprima: senza, le
# facce coincidenti di cornice, feritoie e battuta escono a strisce.
echo "render:"
# Gli argomenti dopo i quattro fissi sono -D extra, solo per il PNG.
# Il fronte mostra la faccia finita: serigrafia opaca e intonaco a filo,
# con la sola fessura di 3 mm. L'assieme tiene la serigrafia ma non l'intonaco,
# cosi' si vede la cassa. Esploso, sezione e retro restano il modello nudo.
render() {           # render <nome> <vista> <rot_x> <rot_z> [ortho] [-D ...]
  local nome=$1 vista=$2 rx=$3 rz=$4
  shift 4
  local proj=()
  if [[ ${1:-} == ortho ]]; then
    proj=(--projection=ortho)
    shift
  fi
  "$SCAD" --quiet --backend=manifold --render -D "VISTA=\"$vista\"" "$@" \
    ${proj[@]+"${proj[@]}"} \
    --imgsize=900,1150 --colorscheme=Tomorrow \
    --camera=0,0,0,"$rx",0,"$rz",0 --viewall --autocenter \
    -o "anteprime/3d-$nome.png" "$MODELLO"
  echo "  anteprime/3d-$nome.png"
}

# Il fronte e' in proiezione ortografica: le proporzioni del vetro restano
# 100 x 240 e non si intravede il fondo della cassa.
render fronte   assieme 90 0 ortho -D MOSTRA_SERIGRAFIA=true -D MOSTRA_INTONACO=true
render assieme  assieme 72 25 -D MOSTRA_SERIGRAFIA=true
render esploso  esploso 76 22
render sezione  sezione 80 55
render retro    assieme 76 200

echo "stl per la produzione:"
for pezzo in cassa telaio vetro; do
  "$SCAD" --quiet -D "VISTA=\"$pezzo\"" -o "stl/$pezzo.stl" "$MODELLO"
  echo "  stl/$pezzo.stl"
done
