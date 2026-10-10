#!/usr/bin/env python3
"""Converte i DXF in immagini PNG, per controllarli senza aprire un CAD.

Uso:
    ../.venv-cad/bin/python anteprime.py
"""
from __future__ import annotations

from pathlib import Path

import ezdxf
import matplotlib.pyplot as plt
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

BASE = Path(__file__).parent
CAD = BASE / "cad"
USCITA = BASE / "anteprime"


# I 130 dpi bastano a controllare una tavola di produzione a video, dove
# contano i profili. Non bastano per i fogli fatti di testo: il 06 e' una
# scheda da leggere, con note da 2,4 mm che a 130 dpi diventano due pixel.
DPI = {"06-gruppo-display": 300, "07-staffa-e-pezzi-piani": 300}


def disegna(percorso: Path) -> Path:
    doc = ezdxf.readfile(percorso)
    msp = doc.modelspace()

    fig = plt.figure(figsize=(8.5, 11))
    ax = fig.add_axes([0.02, 0.02, 0.96, 0.96])
    ax.set_facecolor("white")
    Frontend(RenderContext(doc), MatplotlibBackend(ax)).draw_layout(
        msp, finalize=True)
    ax.set_axis_off()

    destinazione = USCITA / (percorso.stem + ".png")
    fig.savefig(destinazione, dpi=DPI.get(percorso.stem, 130),
                facecolor="white")
    plt.close(fig)
    return destinazione


def main() -> int:
    USCITA.mkdir(exist_ok=True)
    for dxf in sorted(CAD.glob("*.dxf")):
        png = disegna(dxf)
        print(f"  {png.name:28} {png.stat().st_size // 1024} kB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
