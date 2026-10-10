#!/usr/bin/env python3
"""Controlla i file CAD generati, non i parametri che li hanno generati.

La distinzione non e' accademica. `parametri.py` verifica se stesso: se un
parametro e' sbagliato ma coerente con gli altri, passa. I difetti piu' gravi
trovati in questo progetto sono emersi solo misurando i file prodotti, perche'
fra i parametri e il file c'e' il generatore, che a sua volta puo' sbagliare.
Questo script misura quindi vetro, telaio e cassa come li riceverebbe un
fornitore: apre i DXF e gli STL e controlla che le quote tornino.

    ../.venv-cad/bin/python verifica_cad.py

Va eseguito dopo genera_dxf.py, anteprime.py e genera_3d.sh. Esce con codice 1
se trova almeno un problema, cosi' puo' stare in uno script di build.
"""

from __future__ import annotations

import itertools
import math
import sys
from collections import Counter
from pathlib import Path

import ezdxf

sys.path.insert(0, str(Path(__file__).parent))
import parametri as p  # noqa: E402

CAD = Path(__file__).parent / "cad"
STL = Path(__file__).parent / "stl"

# Tolleranza sulle quote: un centesimo di millimetro. Non e' la tolleranza di
# lavorazione, e' il margine per gli arrotondamenti in virgola mobile.
TOLL = 0.02


# ------------------------------------------------------------------ utilita'

def vertici_stl(percorso: Path) -> list[tuple[float, float, float]]:
    """Legge i vertici di uno STL ASCII, come li esporta OpenSCAD."""
    v = []
    for riga in percorso.read_text().splitlines():
        if "vertex" in riga:
            x, y, z = (float(n) for n in riga.split()[1:4])
            v.append((x, y, z))
    return v


def estensione(v: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    return tuple(max(c) - min(c) for c in zip(*v))


def bbox_testo(e) -> tuple[float, float, float, float, str]:
    """Ingombro stimato di un TEXT, per cercare le sovrapposizioni.

    La larghezza di un carattere nel font di default dipende dal visualizzatore;
    0,62 volte l'altezza e' la stima che corrisponde a quanto si vede stampando.
    """
    h = e.dxf.height
    testo = e.dxf.text
    larghezza = len(testo) * h * 0.62
    x, y = e.dxf.insert[0], e.dxf.insert[1]
    allineamento = e.dxf.get("halign", 0)
    if allineamento == 1:      # centrato
        x -= larghezza / 2
    elif allineamento == 2:    # a destra
        x -= larghezza
    return (x, y - h * 0.25, x + larghezza, y + h, testo)


# ------------------------------------------------------------------ controlli

def controlla_stl() -> list[str]:
    """Tenuta dei solidi e quote esterne.

    Un solido che non e' chiuso non si stampa e non si lavora: ogni spigolo
    deve appartenere a esattamente due triangoli. Le quote esterne attese
    comprendono, per la cassa, la flangia perimetrale che sborda da entrambi i
    lati, altrimenti sembrerebbe 24 mm piu' grande del dovuto.
    """
    problemi = []
    attese = {
        "vetro.stl": (p.VETRO_L, p.VETRO_S, p.VETRO_H),
        "telaio.stl": (p.TELAIO_L, p.TELAIO_S, p.TELAIO_H),
        "cassa.stl": (p.CASSA_L + 2 * p.FLANGIA, None,
                      p.CASSA_H + 2 * p.FLANGIA),
    }
    for nome, (att_l, att_s, att_h) in attese.items():
        percorso = STL / nome
        if not percorso.exists():
            problemi.append(f"{nome}: manca, esegui genera_3d.sh")
            continue
        v = vertici_stl(percorso)
        triangoli = [tuple(sorted(v[i:i + 3])) for i in range(0, len(v), 3)]

        degeneri = sum(1 for t in triangoli if len(set(t)) < 3)
        if degeneri:
            problemi.append(f"{nome}: {degeneri} triangoli degeneri")

        spigoli = Counter()
        for t in triangoli:
            for a, b in ((t[0], t[1]), (t[1], t[2]), (t[0], t[2])):
                spigoli[(a, b)] += 1
        spaiati = sum(1 for n in spigoli.values() if n != 2)
        if spaiati:
            problemi.append(
                f"{nome}: {spaiati} spigoli non condivisi da due triangoli,"
                " il solido non e' chiuso")

        # Negli STL il gruppo e' ruotato per stare in piedi: la y del file e'
        # lo spessore (la z del modello) e la z e' l'altezza.
        mis_l, mis_s, mis_h = estensione(v)
        for quota, misurata, attesa in (("larghezza", mis_l, att_l),
                                        ("spessore", mis_s, att_s),
                                        ("altezza", mis_h, att_h)):
            if attesa is not None and abs(misurata - attesa) > TOLL:
                problemi.append(
                    f"{nome}: {quota} {misurata:.2f} invece di {attesa:.2f}")
    return problemi


def controlla_dxf() -> list[str]:
    """Unita' di misura, contorni chiusi, entita' doppie.

    Un DXF senza unita' dichiarate viene importato in pollici da qualche CAM, e
    un contorno di taglio aperto manda il laser fuori strada. Le entita'
    doppie, invece, sono innocue a vedersi ma fanno tagliare due volte la stessa
    linea, che su un laser significa bruciare il bordo.
    """
    problemi = []
    for percorso in sorted(CAD.glob("0*.dxf")):
        nome = percorso.name
        doc = ezdxf.readfile(percorso)
        if doc.header.get("$INSUNITS") != 4:     # 4 = millimetri
            problemi.append(f"{nome}: unita' non dichiarate in millimetri")
        msp = doc.modelspace()

        for e in msp:
            if (e.dxftype() == "LWPOLYLINE" and e.dxf.layer == "TAGLIO"
                    and not e.closed):
                problemi.append(
                    f"{nome}: un contorno sul layer TAGLIO e' aperto")

        impronte = Counter()
        for e in msp:
            if e.dxftype() == "CIRCLE":
                c = e.dxf.center
                impronte[("C", e.dxf.layer, round(c[0], 3), round(c[1], 3),
                          round(e.dxf.radius, 3))] += 1
            elif e.dxftype() == "LWPOLYLINE":
                impronte[("P", e.dxf.layer,
                          tuple((round(q[0], 3), round(q[1], 3))
                                for q in e.get_points()))] += 1
        doppie = sum(n - 1 for n in impronte.values() if n > 1)
        if doppie:
            problemi.append(f"{nome}: {doppie} entita' sovrapposte identiche")

        testi = [bbox_testo(e) for e in msp
                 if e.dxftype() == "TEXT" and e.dxf.text.strip()]
        for a, b in itertools.combinations(testi, 2):
            sovr_x = min(a[2], b[2]) - max(a[0], b[0])
            sovr_y = min(a[3], b[3]) - max(a[1], b[1])
            if sovr_x > 0.4 and sovr_y > 0.4:
                problemi.append(
                    f"{nome}: le scritte '{a[4][:30]}' e '{b[4][:30]}'"
                    " si sovrappongono")
    return problemi


def controlla_coerenza() -> list[str]:
    """Il 2D e il 3D nascono da due generatori diversi: devono dire lo stesso.

    `genera_dxf.py` disegna i profili in Python, il .scad li ricostruisce in
    OpenSCAD. Finche' nessuno confronta i due risultati, una modifica fatta solo
    da un lato resta invisibile: il fornitore taglia dal DXF un pezzo che non e'
    quello montato nel modello.
    """
    problemi = []

    msp = ezdxf.readfile(CAD / "02-telaio-portante.dxf").modelspace()
    punti = [q for e in msp
             if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == "TAGLIO"
             for q in e.get_points()]
    xs = [q[0] for q in punti]
    ys = [q[1] for q in punti]
    for quota, misurata, attesa in (("larghezza", max(xs) - min(xs), p.TELAIO_L),
                                    ("altezza", max(ys) - min(ys), p.TELAIO_H)):
        if abs(misurata - attesa) > TOLL:
            problemi.append(
                f"02-telaio-portante.dxf: {quota} del profilo esterno"
                f" {misurata:.2f} invece di {attesa:.2f}")

    msp = ezdxf.readfile(CAD / "01-vetro-frontale.dxf").modelspace()
    taglio = [e for e in msp
              if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == "TAGLIO"]
    if len(taglio) != 1:
        problemi.append(
            f"01-vetro-frontale.dxf: {len(taglio)} profili di taglio"
            " invece di uno")
    else:
        punti = taglio[0].get_points()
        xs = [q[0] for q in punti]
        ys = [q[1] for q in punti]
        for quota, misurata, attesa in (
                ("larghezza", max(xs) - min(xs), p.VETRO_L),
                ("altezza", max(ys) - min(ys), p.VETRO_H)):
            if abs(misurata - attesa) > TOLL:
                problemi.append(
                    f"01-vetro-frontale.dxf: {quota} {misurata:.2f}"
                    f" invece di {attesa:.2f}")
    return problemi


def controlla_ponti() -> list[str]:
    """Quanto materiale resta fra due fori vicini del telaio.

    Sotto il millimetro e mezzo l'alluminio fra due fori si deforma in fresatura
    e, se i fori sono filettati, il filetto viene via. E' il controllo che
    nessun disegno mostra, perche' i fori si guardano uno alla volta.
    """
    problemi = []
    msp = ezdxf.readfile(CAD / "02-telaio-portante.dxf").modelspace()
    fori = [(e.dxf.center[0], e.dxf.center[1], e.dxf.radius) for e in msp
            if e.dxftype() == "CIRCLE"
            and e.dxf.layer in ("TAGLIO", "FILETTATURA")]
    minimo = None
    for (x1, y1, r1), (x2, y2, r2) in itertools.combinations(fori, 2):
        ponte = math.dist((x1, y1), (x2, y2)) - r1 - r2
        if minimo is None or ponte < minimo[0]:
            minimo = (ponte, (x1, y1), (x2, y2))
    if minimo and minimo[0] < 1.5:
        ponte, a, b = minimo
        problemi.append(
            f"02-telaio-portante.dxf: fra il foro in ({a[0]:.1f}, {a[1]:.1f})"
            f" e quello in ({b[0]:.1f}, {b[1]:.1f}) restano {ponte:.2f} mm"
            " di materiale")
    elif minimo:
        print(f"  ponte minimo fra i {len(fori)} fori del telaio:"
              f" {minimo[0]:.2f} mm")
    return problemi


# ---------------------------------------------------------------------- main

def main() -> int:
    problemi = []
    for titolo, controllo in (("solidi 3D", controlla_stl),
                              ("disegni 2D", controlla_dxf),
                              ("coerenza 2D/3D", controlla_coerenza),
                              ("ponti fra i fori", controlla_ponti)):
        trovati = controllo()
        stato = f"{len(trovati)} problemi" if trovati else "a posto"
        print(f"  {titolo:18s} {stato}")
        problemi += trovati

    if problemi:
        print(f"\n{len(problemi)} problemi nei file CAD:")
        for x in problemi:
            print(f"  - {x}")
        return 1
    print("\nI file CAD sono coerenti con i parametri.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
