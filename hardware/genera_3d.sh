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
echo "render:"
render() {           # render <nome> <vista> <rot_x> <rot_z>
  "$SCAD" --quiet -D "VISTA=\"$2\"" \
    --imgsize=900,1150 --colorscheme=Tomorrow \
    --camera=0,0,0,"$3",0,"$4",0 --viewall --autocenter \
    -o "anteprime/3d-$1.png" "$MODELLO"
  echo "  anteprime/3d-$1.png"
}

render fronte   assieme 90 0
render assieme  assieme 72 25
render esploso  esploso 76 22
render sezione  sezione 80 55
render retro    assieme 76 200

echo "stl per la produzione:"
for pezzo in cassa telaio vetro; do
  "$SCAD" --quiet -D "VISTA=\"$pezzo\"" -o "stl/$pezzo.stl" "$MODELLO"
  echo "  stl/$pezzo.stl"
done
