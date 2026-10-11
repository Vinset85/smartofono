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
        "cassa.stl": (p.CASSA_L + 2 * p.FLANGIA, p.Z_TELAIO + p.CASSA_PROF,
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


def controlla_sedi_riscontri() -> list[str]:
    """Le sei sedi dei riscontri devono esistere nel solido della cassa.

    Il modello le scava, ma una modifica all'ordine delle operazioni puo'
    farle riempire dal vano senza che niente protesti: il solido resta chiuso e
    le quote esterne non cambiano.

    Una prima versione cercava vertici alla quota del fondo della sede, e
    passava anche senza battuta: li trovava dove la sede intacca la parete.
    Ora si sonda il solido: vuoto dentro la sede, pieno subito sotto il suo
    fondo e accanto, sulla faccia d'appoggio.
    """
    percorso = STL / "cassa.stl"
    if not percorso.exists():
        return ["cassa.stl: manca, esegui genera_3d.sh"]
    v = vertici_stl(percorso)
    triangoli = [v[i:i + 3] for i in range(0, len(v), 3)]
    faccia = p.Z_TELAIO + p.TELAIO_S
    problemi = []
    for sx, sy in p.posizioni_riscontri():
        # verso l'interno del vano, lungo l'anello: e' sempre battuta piena
        lungo = (0, 4.5) if abs(sx) > 40 else (4.5, 0)
        sonde = (
            ("dentro la sede", (sx, sy, faccia + p.RISCONTRO_SEDE_PROF / 2),
             False),
            ("sotto il fondo della sede",
             (sx, sy, faccia + p.RISCONTRO_SEDE_PROF + 0.6), True),
            ("sulla battuta accanto alla sede",
             (sx + lungo[0], sy + lungo[1], faccia + 0.3), True),
        )
        for descrizione, (x, y, z), pieno in sonde:
            if dentro_al_solido(triangoli, (x + 0.013, z + 0.011, y + 0.017)) \
                    != pieno:
                problemi.append(
                    f"cassa.stl: sede del riscontro in ({sx:.1f}, {sy:.1f}),"
                    f" {descrizione}: "
                    + ("vuoto invece di pieno" if pieno
                       else "pieno invece di vuoto"))
    return problemi


def dentro_al_solido(triangoli, punto) -> bool:
    """Il punto sta dentro il solido? Conta le pareti attraversate da un raggio.

    Un raggio che passa esattamente su uno spigolo conta male, quindi se ne
    lanciano tre in direzioni oblique e decide la maggioranza.
    """
    def attraversamenti(d):
        n = 0
        for a, b, c in triangoli:
            e1 = [b[i] - a[i] for i in range(3)]
            e2 = [c[i] - a[i] for i in range(3)]
            h = [d[1] * e2[2] - d[2] * e2[1], d[2] * e2[0] - d[0] * e2[2],
                 d[0] * e2[1] - d[1] * e2[0]]
            det = sum(e1[i] * h[i] for i in range(3))
            if abs(det) < 1e-12:
                continue
            s = [punto[i] - a[i] for i in range(3)]
            u = sum(s[i] * h[i] for i in range(3)) / det
            if u < 0 or u > 1:
                continue
            q = [s[1] * e1[2] - s[2] * e1[1], s[2] * e1[0] - s[0] * e1[2],
                 s[0] * e1[1] - s[1] * e1[0]]
            w = sum(d[i] * q[i] for i in range(3)) / det
            if w < 0 or u + w > 1:
                continue
            if sum(e2[i] * q[i] for i in range(3)) / det > 1e-9:
                n += 1
        return n % 2

    direzioni = ((0.577, 0.577, 0.577), (-0.267, 0.534, 0.802),
                 (0.913, -0.183, 0.365))
    return sum(attraversamenti(d) for d in direzioni) >= 2


def controlla_solido_cassa() -> list[str]:
    """Dove deve esserci materiale e dove deve esserci aria, nella cassa.

    La cassa e' uscita senza parete di fondo: uno scavo arrivava fino a
    CASSA_PROF e se la portava via. Il solido restava chiuso e le quote
    esterne giuste, quindi nessun controllo sulle misure poteva accorgersene.
    E la flangia attraversava le feritoie, cosa che si vede solo guardando
    dentro. Qui si interroga il solido punto per punto: materiale dove serve,
    aria lungo tutto il percorso dell'aria.
    """
    percorso = STL / "cassa.stl"
    if not percorso.exists():
        return ["cassa.stl: manca, esegui genera_3d.sh"]
    v = vertici_stl(percorso)
    triangoli = [v[i:i + 3] for i in range(0, len(v), 3)]

    yc = p.VETRO_H / 2
    basso = yc - p.CASSA_H / 2              # faccia esterna della parete bassa
    alto = yc + p.CASSA_H / 2
    z_fer = p.Z_TELAIO + p.FESSURA_ARRETRAMENTO + p.FESSURA_ALTEZZA / 2
    y_lat = (p.FESSURA_LATO_Y0 + p.FESSURA_LATO_Y1) / 2
    mezza = p.CASSA_PARETE / 2
    canale = p.CANALE_PERIMETRALE / 2
    # (descrizione, x, altezza, profondita' dal vetro, deve essere pieno)
    sonde = [
        ("parete di fondo", 10, 150, p.Z_TELAIO + p.CASSA_PROF - mezza, True),
        ("parete alta, dove stava la feritoia", 0, alto - mezza, z_fer, True),
        ("fianco sotto la feritoia laterale", p.CASSA_L / 2 - mezza,
         p.FESSURA_LATO_Y0 - 5, z_fer, True),
        ("battuta bassa", 0, yc - p.CASSA_INT_H / 2 + p.BATTUTA / 2,
         p.Z_TELAIO + p.TELAIO_S + p.BATTUTA_PROF / 2, True),
        ("battuta laterale, appena dietro la faccia d'appoggio",
         p.CASSA_INT_L / 2 - p.BATTUTA / 2, 90, p.Z_TELAIO + p.TELAIO_S + 0.1,
         True),
        ("bocca, appena davanti alla faccia d'appoggio",
         p.CASSA_INT_L / 2 - p.BATTUTA / 2, 90, p.Z_TELAIO + p.TELAIO_S - 0.1,
         False),
        ("luce della battuta, nessuna pellicola sul fronte", 0, 120,
         p.Z_TELAIO + p.TELAIO_S - 0.02, False),
        ("scarico della squadretta", (p.SCARICO_STAFFA_X
                                      - (p.CASSA_INT_L / 2 - p.BATTUTA)) / 2,
         p.DRIVER_Y, p.Z_TELAIO + p.TELAIO_S + p.BATTUTA_PROF / 2, False),
        ("battuta accanto allo scarico", (p.SCARICO_STAFFA_X
                                          - p.CASSA_INT_L / 2) / 2,
         p.DRIVER_Y, p.Z_TELAIO + p.TELAIO_S + p.BATTUTA_PROF / 2, True),
        ("flangia dietro il canale basso", 0, basso - canale,
         p.Z_FLANGIA + mezza, True),
        ("flangia dietro il canale laterale", p.CASSA_L / 2 + canale, 150,
         p.Z_FLANGIA + mezza, True),
        ("cornice alta", 0, yc + p.LUCE_INTONACO_H / 2 + p.CORNICE_S / 2,
         p.Z_FLANGIA / 2, True),
        ("cornice laterale, sul fronte", p.LUCE_INTONACO_L / 2
         + p.CORNICE_S / 2, 150, 0.5, True),
        ("gocciolatoio", p.CASSA_L / 2 + 0.6, p.FESSURA_LATO_Y1 + 1.6,
         (p.Z_TELAIO + p.Z_FLANGIA) / 2, True),
        ("smusso di scarico", p.CASSA_INT_L / 2 - 1,
         yc - p.CASSA_INT_H / 2 + 1, z_fer, True),
        ("vano interno", 0, 120, 40, False),
        ("feritoia bassa", 0, basso + mezza, z_fer, False),
        ("feritoia laterale destra", p.CASSA_L / 2 - mezza, y_lat, z_fer,
         False),
        ("feritoia laterale sinistra", -(p.CASSA_L / 2 - mezza), y_lat, z_fer,
         False),
        ("canale sotto la feritoia bassa", 0, basso - canale, z_fer, False),
        ("canale davanti alla flangia", 0, basso - canale, p.Z_FLANGIA - 0.5,
         False),
        ("canale accanto alla feritoia laterale", p.CASSA_L / 2 + canale,
         y_lat, z_fer, False),
        ("bocca nella fessura d'ombra", 0,
         -p.OMBRA_PERIMETRALE / 2, p.VETRO_S / 2, False),
        ("canale sopra la cassa", 0, alto + canale, 20, False),
        ("passaggio del corrugato", p.CORRUGATO_PASSO / 2, 26,
         p.Z_TELAIO + p.CASSA_PROF - mezza, False),
        ("foro d'ancoraggio della flangia", p.FLANGIA_FORI_X,
         yc + p.FLANGIA_FORI_PASSO / 2, p.Z_FLANGIA + mezza, False),
    ]
    problemi = []
    for descrizione, x, h, z, pieno in sonde:
        # STL in piedi: x, profondita', altezza. Lo scarto di 0,013 tiene i
        # raggi lontani dai piani di simmetria, dove cadono gli spigoli.
        if dentro_al_solido(triangoli, (x + 0.013, z + 0.011, h + 0.017)) \
                != pieno:
            problemi.append(
                f"cassa.stl: {descrizione} in (x {x:.1f}, h {h:.1f},"
                f" z {z:.1f}) dovrebbe essere "
                + ("materiale ed e' vuoto" if pieno else "aria ed e' pieno"))
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
        # Una scritta sopra una linea non si legge, e sul telaio finiva
        # proprio sopra il profilo di taglio. Le quote generate da ezdxf sono
        # blocchi, non entita' sciolte, e qui non entrano.
        tratti = list(tratti_dxf(msp))
        for x0, y0, x1, y1, t in testi:
            riquadro = (x0 + 0.3, y0 + 0.3, x1 - 0.3, y1 - 0.3)
            for layer, s in tratti:
                if tratto_nel_riquadro(riquadro, s):
                    problemi.append(
                        f"{nome}: la scritta '{t[:30]}' passa sopra una linea"
                        f" del layer {layer}")
                    break
    return problemi


def tratti_dxf(msp):
    """Segmenti di LINE e LWPOLYLINE; i cerchi come quadrato circoscritto."""
    for e in msp:
        tipo = e.dxftype()
        if tipo == "LINE":
            a, b = e.dxf.start, e.dxf.end
            yield e.dxf.layer, (a.x, a.y, b.x, b.y)
        elif tipo == "LWPOLYLINE":
            q = [(v[0], v[1]) for v in e.get_points()]
            if e.closed:
                q.append(q[0])
            for a, b in zip(q, q[1:]):
                yield e.dxf.layer, (*a, *b)
        elif tipo == "CIRCLE":
            cx, cy, r = e.dxf.center.x, e.dxf.center.y, e.dxf.radius
            angoli = [(cx - r, cy - r), (cx + r, cy - r), (cx + r, cy + r),
                      (cx - r, cy + r), (cx - r, cy - r)]
            for a, b in zip(angoli, angoli[1:]):
                yield e.dxf.layer, (*a, *b)


def tratto_nel_riquadro(riquadro, s) -> bool:
    """Liang-Barsky: il segmento s entra nel riquadro?"""
    x0, y0, x1, y1 = riquadro
    ax, ay, bx, by = s
    t0, t1 = 0.0, 1.0
    for d, q in ((ax - bx, ax - x0), (bx - ax, x1 - ax),
                 (ay - by, ay - y0), (by - ay, y1 - ay)):
        if d == 0:
            if q < 0:
                return False
            continue
        r = q / d
        if d < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return False
    return True


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


def controlla_documenti() -> list[str]:
    """Le quote che i documenti citano a mano devono essere quelle vere.

    I disegni nascono dai parametri e non possono mentire, ma README,
    PRODUZIONE e ASSEMBLAGGIO scrivono le misure in prosa, perche' una tabella
    di ordinazione deve dire "Ø6 x 1" e non "RISCONTRO_D". Quelle cifre
    nessuno le ricontrolla quando un parametro cambia, ed e' cosi' che i
    documenti sono arrivati a chiedere al fornitore dischetti da 8 mentre il
    disegno li faceva da 6, e una rete alta come la feritoia che quindi non
    aveva dove incollarsi.

    Qui sotto c'e' una riga per ogni quota che un documento ripete a mano. Non
    e' un controllo generale sui numeri, che non si puo' fare: e' un elenco di
    cose che devono comparire, e che si rompe quando il parametro si muove.
    """
    attese = [
        ("README.md", f"Ø{p.RISCONTRO_D:.0f} x {p.RISCONTRO_S:.0f}",
         "diametro e spessore del riscontro ferroso"),
        ("README.md", f"{p.RETE_L:.0f} x {p.RETE_H:.0f} mm",
         "ritaglio della rete delle feritoie"),
        ("README.md", f"{p.BIADESIVO_S:.1f} mm".replace(".", ","),
         "spessore del VHB fra vetro e telaio"),
        ("README.md",
         f"{p.DISPLAY_MODULO_L:.0f} x {p.DISPLAY_MODULO_H:.0f} mm",
         "ritaglio dell'adesivo ottico"),
        ("PRODUZIONE.md", f"Ø{p.RISCONTRO_D:.0f} x {p.RISCONTRO_S:.0f}",
         "diametro e spessore del riscontro ferroso"),
        ("PRODUZIONE.md", f"{p.RETE_L:.0f} x {p.RETE_H:.0f}",
         "ritaglio della rete delle feritoie"),
        ("PRODUZIONE.md", f"**{p.CASSA_PARETE} mm**".replace(".", ","),
         "parete della cassa stampata"),
        ("PRODUZIONE.md",
         f"{p.VETRO_L:.0f} x {p.VETRO_H:.0f} x {p.VETRO_S:.0f}",
         "formato del vetro"),
        ("PRODUZIONE.md",
         f"{p.FINESTRA_DISPLAY_L:.1f} x {p.FINESTRA_DISPLAY_H:.1f}"
         .replace(".", ","),
         "finestra del display da controllare alla consegna"),
        ("ASSEMBLAGGIO.md", f"Ø{p.RISCONTRO_D:.0f} x {p.RISCONTRO_S:.0f}",
         "diametro e spessore del riscontro ferroso"),
        ("ASSEMBLAGGIO.md", f"{p.RETE_L:.0f} x {p.RETE_H:.0f}",
         "ritaglio della rete delle feritoie"),
        ("ASSEMBLAGGIO.md",
         f"{p.FORO_MURO_L:.0f} x {p.FORO_MURO_H:.0f} x {p.FORO_MURO_PROF:.0f}",
         "nicchia da scavare"),
    ]

    def virgola(valore: float, cifre: int = 1) -> str:
        return f"{valore:.{cifre}f}".replace(".", ",")

    sez = p.sezioni_aria()
    nicchia = (f"{p.FORO_MURO_L:.0f} x {p.FORO_MURO_H:.0f}"
               f" x {p.FORO_MURO_PROF:.0f}")
    rete_lato = f"{p.RETE_LATO_L:.0f} x {p.RETE_H:.0f}"
    bassa = f"{p.FESSURA_LARGHEZZA:.0f} x {p.FESSURA_ALTEZZA:.0f}"
    laterale = f"{p.FESSURA_LATO_L:.0f} x {p.FESSURA_ALTEZZA:.0f}"
    ansa = p.PI_Y0 - p.PCIE_ANSA - (p.NFC_Y + p.NFC_PCB_H / 2)
    for nome in ("README.md", "PRODUZIONE.md", "ASSEMBLAGGIO.md"):
        attese += [(nome, rete_lato, "ritaglio della rete delle feritoie"
                    " laterali"),
                   (nome, bassa, "feritoia bassa"),
                   (nome, laterale, "feritoie laterali")]
    attese += [
        ("README.md", nicchia, "nicchia da scavare"),
        ("README.md", f"**{virgola(ansa)} mm**",
         "margine fra l'ansa del flat PCIe e il lettore NFC"),
        ("README.md", f"{virgola(p.canale_aria())} mm",
         "canale d'aria dietro i componenti"),
        ("README.md", f"gruppo da {p.gruppo_massimo():.0f}",
         "gruppo del Pi oltre il quale il canale e' il collo di bottiglia"),
        ("ASSEMBLAGGIO.md", f"oltre i {p.gruppo_massimo():.0f}",
         "gruppo del Pi oltre il quale il canale e' il collo di bottiglia"),
        ("MISURE.md", f"gruppo da **{p.gruppo_massimo():.0f}**",
         "gruppo del Pi oltre il quale il canale e' il collo di bottiglia"),
        ("MISURE.md", f"se ne usano {p.FORO_MURO_PROF:.0f}",
         "profondita' della nicchia"),
        ("README.md", f"**{virgola(sez['ingresso_libera'], 2)} cm² liberi**",
         "sezione libera delle feritoie"),
        ("README.md", f"a {p.Z_FLANGIA:.0f} mm dal filo dell'intonaco",
         "posizione della flangia"),
        ("README.md", f"escono {virgola(p.tiraggio(20))} W",
         "tiraggio naturale a 20 gradi"),
        ("README.md",
         f"**{p.salto_termico(p.POTENZA_RIPOSO):.0f} gradi sopra**",
         "salto termico a riposo"),
        ("README.md", f"**{p.salto_termico(p.POTENZA_PICCO):.0f} gradi**",
         "salto termico a pieno carico"),
        ("README.md", f"**{virgola(p.DISPLAY_ARIA_TELAIO, 2)} mm d'aria**",
         "aria fra display e telaio"),
        ("MISURE.md", f"**{virgola(p.DISPLAY_ARIA_TELAIO, 2)} mm d'aria**",
         "aria fra display e telaio"),
        ("ASSEMBLAGGIO.md",
         f"{p.DISPLAY_MODULO_Y0 + p.DISPLAY_MODULO_H / 2:.0f} mm",
         "centro del display dal bordo inferiore del vetro"),
    ]
    # Le frasi di un progetto che non esiste piu'. Ciascuna e' stata vera, e
    # ciascuna e' sopravvissuta almeno una volta alla modifica che la smentiva.
    superate = [
        ("85 x 13", "la rete delle vecchie feritoie 80 x 8"),
        ("80 x 8", "le vecchie feritoie"),
        ("124 x 264", "la vecchia nicchia"),
        ("mezzo grado", "la pendenza della cassa, tolta"),
        ("feritoia superiore", "la feritoia alta, tolta"),
        ("solo sui due lati verticali", "il silicone nella fessura, tolto"),
        ("limite di 64", "il vecchio limite del gruppo del Pi"),
        ("gruppo da 64", "il vecchio limite del gruppo del Pi"),
        ("64 di gruppo", "il vecchio limite del gruppo del Pi"),
        ("nicchia a 81", "la nicchia e' 86 mm dal filo dell'intonaco"),
        ("1,0 mm d'aria", "l'aria dietro il display e' 0,85 mm"),
        ("distanziali 9,5", "i distanziali del Pi sono da 10"),
    ]
    problemi = []
    radice = Path(__file__).parent

    def leggi(nome: str) -> str:
        """Il testo con gli a capo ridotti a spazi: la prosa va a capo dove
        capita, anche in mezzo a una quota."""
        return " ".join((radice / nome).read_text().split())

    for nome, atteso, descrizione in attese:
        testo = leggi(nome)
        if atteso not in testo:
            problemi.append(
                f"{nome}: non dice '{atteso}' da nessuna parte"
                f" ({descrizione})")
    for nome in ("README.md", "PRODUZIONE.md", "ASSEMBLAGGIO.md", "MISURE.md"):
        testo = leggi(nome)
        for frase, motivo in superate:
            if frase in testo:
                problemi.append(f"{nome}: dice ancora '{frase}' ({motivo})")
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
                              ("sedi riscontri", controlla_sedi_riscontri),
                              ("pieni e vuoti cassa", controlla_solido_cassa),
                              ("disegni 2D", controlla_dxf),
                              ("coerenza 2D/3D", controlla_coerenza),
                              ("quote nei documenti", controlla_documenti),
                              ("ponti fra i fori", controlla_ponti)):
        trovati = controllo()
        stato = f"{len(trovati)} problemi" if trovati else "a posto"
        print(f"  {titolo:20s} {stato}")
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
