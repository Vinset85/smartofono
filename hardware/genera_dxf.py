#!/usr/bin/env python3
"""Genera i disegni 2D del videocitofono da incasso in formato DXF.

Produce sette file nella cartella cad/:

  01-vetro-frontale.dxf          per la vetreria: sagoma, fori e serigrafia
  02-telaio-portante.dxf         per la carpenteria: piastra in alluminio
  03-cassa-incasso.dxf           viste di controllo della cassa stampata
  04-dima-muratura.dxf           sagoma 1:1 per tracciare la nicchia
  05-disposizione.dxf            ingombri dei componenti, pianta e sezione
  06-gruppo-display.dxf          display, schede e flat
  07-staffa-e-pezzi-piani.dxf    squadretta e ritagli 1:1

Ogni file usa layer separati per lavorazioni diverse, cosi' il fornitore
importa solo quello che gli serve: TAGLIO per il profilo e i fori passanti,
SERIGRAFIA per la stampa, PIEGA per le piegature, QUOTE e NOTE come
riferimento da ignorare in macchina. Nei fogli che non vanno in macchina
(03, 04, 05) i colori distinguono le parti, e ogni foglio ha la sua legenda.

Uso:
    ../.venv-cad/bin/python genera_dxf.py
"""
from __future__ import annotations

import math
from pathlib import Path

import ezdxf
from ezdxf import units
from ezdxf.enums import TextEntityAlignment

import parametri as p

USCITA = Path(__file__).parent / "cad"

# Il bulge di un arco di 90 gradi in una polilinea leggera.
BULGE_90 = math.tan(math.radians(90) / 4)

LAYER = {
    "TAGLIO": (1, "CONTINUOUS"),          # rosso: profilo e fori passanti
    "SERIGRAFIA": (7, "CONTINUOUS"),      # nero: campitura opaca
    "FINESTRE": (4, "CONTINUOUS"),        # ciano: aperture nella serigrafia
    "SMOKE": (5, "CONTINUOUS"),           # blu: serigrafia semitrasparente
    "PIEGA": (2, "DASHED"),               # giallo: linee di piegatura
    "FILETTATURA": (3, "CONTINUOUS"),     # verde: fori da filettare
    "INGOMBRI": (8, "DASHED2"),           # grigio: componenti, non lavorare
    "QUOTE": (8, "CONTINUOUS"),
    "NOTE": (6, "CONTINUOUS"),
}


def nuovo_disegno() -> ezdxf.document.Drawing:
    doc = ezdxf.new("R2010", setup=True)
    doc.units = units.MM
    doc.header["$INSUNITS"] = 4
    doc.header["$MEASUREMENT"] = 1
    for nome, (colore, tipo) in LAYER.items():
        if tipo not in doc.linetypes:
            tipo = "CONTINUOUS"
        doc.layers.add(nome, color=colore, linetype=tipo)
    # Stile di quota leggibile su stampa A4/A3. dimlfac va forzato a 1: lo
    # stile predefinito di ezdxf applica un fattore che moltiplicherebbe le
    # misure scritte sul disegno.
    stile = doc.dimstyles.get("EZDXF")
    stile.dxf.dimtxt = 3.0
    stile.dxf.dimasz = 2.0
    stile.dxf.dimexe = 1.0
    stile.dxf.dimexo = 1.5
    stile.dxf.dimlfac = 1.0
    stile.dxf.dimdec = 1
    stile.dxf.dimgap = 1.0
    return doc


def rettangolo(msp, larghezza: float, altezza: float, *, raggio: float = 0.0,
               cx: float = 0.0, y0: float = 0.0, layer: str = "TAGLIO"):
    """Rettangolo centrato in x su cx, con il bordo inferiore a y0."""
    x0, x1 = cx - larghezza / 2, cx + larghezza / 2
    y1 = y0 + altezza
    if raggio <= 0:
        msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                           close=True, dxfattribs={"layer": layer})
        return
    r = raggio
    # Ogni vertice raccordato diventa due punti, con il bulge sul primo dei due.
    punti = [
        (x0 + r, y0, 0.0, 0.0, 0.0),
        (x1 - r, y0, 0.0, 0.0, BULGE_90),
        (x1, y0 + r, 0.0, 0.0, 0.0),
        (x1, y1 - r, 0.0, 0.0, BULGE_90),
        (x1 - r, y1, 0.0, 0.0, 0.0),
        (x0 + r, y1, 0.0, 0.0, BULGE_90),
        (x0, y1 - r, 0.0, 0.0, 0.0),
        (x0, y0 + r, 0.0, 0.0, BULGE_90),
    ]
    msp.add_lwpolyline(punti, format="xyseb", close=True,
                       dxfattribs={"layer": layer})


def foro(msp, x: float, y: float, diametro: float, layer: str = "TAGLIO"):
    msp.add_circle((x, y), diametro / 2, dxfattribs={"layer": layer})
    # Assi di riferimento per il centro, utili in officina.
    b = diametro / 2 + 1.5
    for dx, dy in ((b, 0), (0, b)):
        msp.add_line((x - dx, y - dy), (x + dx, y + dy),
                     dxfattribs={"layer": "QUOTE"})


def campitura_serigrafia(msp, finestre: list[tuple]) -> None:
    """Campisce il retro del vetro lasciando vuote le finestre trasparenti.

    `finestre` contiene tuple ("rett", larghezza, altezza, cx, y0, raggio)
    oppure ("cerchio", x, y, diametro): sono le isole da escludere dalla stampa.
    """
    hatch = msp.add_hatch(color=254, dxfattribs={"layer": "SERIGRAFIA"})
    hatch.set_pattern_fill("ANSI31", scale=2.0)
    bordo = hatch.paths.add_polyline_path(
        _punti_rettangolo(p.VETRO_L, p.VETRO_H, 0.0, 0.0, p.VETRO_RAGGIO),
        is_closed=True, flags=ezdxf.const.BOUNDARY_PATH_OUTERMOST)
    assert bordo is not None
    for isola in finestre:
        if isola[0] == "rett":
            _, l, h, cx, y0, r = isola
            hatch.paths.add_polyline_path(
                _punti_rettangolo(l, h, cx, y0, r), is_closed=True,
                flags=ezdxf.const.BOUNDARY_PATH_DEFAULT)
        else:
            _, x, y, d = isola
            hatch.paths.add_edge_path(
                flags=ezdxf.const.BOUNDARY_PATH_DEFAULT
            ).add_arc((x, y), d / 2, 0, 360)


def _punti_rettangolo(larghezza: float, altezza: float, cx: float,
                      y0: float, raggio: float) -> list[tuple[float, float]]:
    """Approssima un rettangolo raccordato con punti, per le campiture."""
    x0, x1 = cx - larghezza / 2, cx + larghezza / 2
    y1 = y0 + altezza
    if raggio <= 0:
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    punti: list[tuple[float, float]] = []
    angoli = [(x1 - raggio, y0 + raggio, -90), (x1 - raggio, y1 - raggio, 0),
              (x0 + raggio, y1 - raggio, 90), (x0 + raggio, y0 + raggio, 180)]
    for cxx, cyy, inizio in angoli:
        for k in range(5):
            a = math.radians(inizio + k * 22.5)
            punti.append((cxx + raggio * math.cos(a),
                          cyy + raggio * math.sin(a)))
    return punti


def nota(msp, x: float, y: float, testo: str, altezza: float = 2.5,
         layer: str = "NOTE"):
    msp.add_text(testo, height=altezza,
                 dxfattribs={"layer": layer}).set_placement((x, y))


def richiamo(msp, punto: tuple[float, float], x: float, y: float, testo: str,
             altezza: float = 2.6, layer: str = "NOTE"):
    """Nota fuori dal pezzo, con una linea che la lega al punto che descrive.

    Con x a sinistra del punto il testo finisce in x, allineato a destra.
    """
    a_sinistra = x < punto[0]
    msp.add_line(punto, (x, y + altezza / 2), dxfattribs={"layer": "NOTE"})
    t = msp.add_text(testo, height=altezza, dxfattribs={"layer": layer})
    if a_sinistra:
        t.set_placement((x - 1, y), align=TextEntityAlignment.BOTTOM_RIGHT)
    else:
        t.set_placement((x + 1, y))


def _segmenti(msp):
    """I tratti gia' disegnati, per cercare dove una scritta non li copre.

    Un cerchio conta come il suo quadrato circoscritto: e' piu' severo, ed e'
    lo stesso criterio di verifica_cad.py.
    """
    for e in msp:
        t = e.dxftype()
        if t == "LINE":
            yield (e.dxf.start[0], e.dxf.start[1], e.dxf.end[0], e.dxf.end[1])
        elif t == "LWPOLYLINE":
            q = [(v[0], v[1]) for v in e.get_points()]
            if e.closed:
                q.append(q[0])
            for a, b in zip(q, q[1:]):
                yield (a[0], a[1], b[0], b[1])
        elif t == "CIRCLE":
            c, r = e.dxf.center, e.dxf.radius
            for a, b in (((-r, -r), (r, -r)), ((r, -r), (r, r)),
                         ((r, r), (-r, r)), ((-r, r), (-r, -r))):
                yield (c[0] + a[0], c[1] + a[1], c[0] + b[0], c[1] + b[1])


def segmento_nel_riquadro(box, s) -> bool:
    """Liang-Barsky: True se il segmento s entra nel riquadro box."""
    x0, y0, x1, y1 = box
    ax, ay, bx, by = s
    ddx, ddy = bx - ax, by - ay
    t0, t1 = 0.0, 1.0
    for pp, q in ((-ddx, ax - x0), (ddx, x1 - ax), (-ddy, ay - y0),
                  (ddy, y1 - ay)):
        if pp == 0:
            if q < 0:
                return False
            continue
        r = q / pp
        if pp < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return False
    return True


def riquadro_testo(x: float, y: float, testo: str, altezza: float):
    """Stessa stima di verifica_cad.bbox_testo, ristretta di 0,3 per lato."""
    return (x + 0.3, y - altezza * 0.25 + 0.3,
            x + len(testo) * altezza * 0.62 - 0.3, y + altezza - 0.3)


def etichetta_libera(msp, x: float, y: float, testo: str, altezza: float,
                     layer: str, occupate: list) -> None:
    """Scrive testo vicino a (x, y), dove non copre linee ne' altre scritte.

    Cerca su anelli sempre piu' larghi; se deve allontanarsi piu' di 3 mm
    traccia un richiamo, altrimenti un numero lontano dal suo riquadro non si
    sa a chi appartiene.
    """
    tratti = list(_segmenti(msp))
    scelto = None
    for giro in range(0, 13):
        r = giro * 1.5
        prove = [(0.0, 0.0)] if giro == 0 else [
            (r * math.cos(math.radians(a)), r * math.sin(math.radians(a)))
            for a in range(0, 360, 30)]
        for ox, oy in prove:
            box = riquadro_testo(x + ox, y + oy, testo, altezza)
            if any(segmento_nel_riquadro(box, s) for s in tratti):
                continue
            if any(min(box[2], b[2]) > max(box[0], b[0])
                   and min(box[3], b[3]) > max(box[1], b[1])
                   for b in occupate):
                continue
            scelto = (x + ox, y + oy)
            break
        if scelto:
            break
    if scelto is None:
        scelto = (x, y)
    elif math.hypot(scelto[0] - x, scelto[1] - y) > 3.0:
        msp.add_line((x, y + altezza / 2),
                     (scelto[0], scelto[1] + altezza / 2),
                     dxfattribs={"layer": "NOTE"})
    occupate.append(riquadro_testo(*scelto, testo, altezza))
    nota(msp, scelto[0], scelto[1], testo, altezza, layer)


def quota_oriz(msp, x1: float, x2: float, y: float, distanza: float = 8.0):
    msp.add_linear_dim(base=(0, y + distanza), p1=(x1, y), p2=(x2, y),
                       dxfattribs={"layer": "QUOTE"}).render()


def quota_vert(msp, y1: float, y2: float, x: float, distanza: float = 8.0):
    msp.add_linear_dim(base=(x + distanza, 0), p1=(x, y1), p2=(x, y2),
                       angle=90, dxfattribs={"layer": "QUOTE"}).render()


# --------------------------------------------------------------------------
# 1. Vetro frontale
# --------------------------------------------------------------------------

def vetro_frontale() -> None:
    doc = nuovo_disegno()
    msp = doc.modelspace()

    # Profilo esterno. La stampa copre tutto il retro tranne le finestre, che
    # diventano isole nella campitura.
    rettangolo(msp, p.VETRO_L, p.VETRO_H, raggio=p.VETRO_RAGGIO)
    isole: list[tuple] = [
        ("rett", p.FINESTRA_DISPLAY_L, p.FINESTRA_DISPLAY_H, 0.0,
         p.FINESTRA_DISPLAY_Y, 1.0),
        ("cerchio", p.CAMERA_X, p.OTTICA_Y, p.OTTICA_D),
        ("cerchio", p.MICROFONO_X, p.MICROFONO_Y, p.MICROFONO_D),
    ]
    for i in range(p.GRIGLIA_N):
        isole.append(("rett", p.GRIGLIA_L, p.GRIGLIA_SPESSORE, 0.0,
                      p.GRIGLIA_Y + i * p.GRIGLIA_PASSO,
                      p.GRIGLIA_SPESSORE / 2))
    campitura_serigrafia(msp, isole)

    # Finestra del display: unica apertura grande nella serigrafia.
    rettangolo(msp, p.FINESTRA_DISPLAY_L, p.FINESTRA_DISPLAY_H,
               y0=p.FINESTRA_DISPLAY_Y, raggio=1.0, layer="FINESTRE")

    # Obiettivo: finestra circolare trasparente, unica e centrata.
    foro(msp, p.CAMERA_X, p.OTTICA_Y, p.OTTICA_D, layer="FINESTRE")

    # Microfono: foro passante, da eseguire prima della tempra.
    foro(msp, p.MICROFONO_X, p.MICROFONO_Y, p.MICROFONO_D, layer="TAGLIO")

    # Griglia dell'altoparlante: solo stampa, il suono esce dalla fessura
    # perimetrale superiore della cornice.
    for i in range(p.GRIGLIA_N):
        y = p.GRIGLIA_Y + i * p.GRIGLIA_PASSO
        rettangolo(msp, p.GRIGLIA_L, p.GRIGLIA_SPESSORE, y0=y,
                   raggio=p.GRIGLIA_SPESSORE / 2, layer="FINESTRE")

    # Zona NFC: cerchio semitrasparente con l'icona al centro.
    foro(msp, p.NFC_X, p.NFC_Y, p.NFC_D, layer="SMOKE")

    # Battuta di incollaggio: dove va il biadesivo, niente finestre. Coincide
    # col profilo del telaio, che e' cio' a cui il vetro si incolla.
    rettangolo(msp, p.TELAIO_L, p.TELAIO_H,
               y0=(p.VETRO_H - p.TELAIO_H) / 2, layer="INGOMBRI")

    # Marca di orientamento: rende impossibile confondere la faccia.
    nota(msp, -p.VETRO_L / 2 + 4, p.VETRO_H + 4,
         "FUORI - vista dalla faccia 1", 3.0)
    richiamo(msp, (p.MICROFONO_X - p.MICROFONO_D, p.MICROFONO_Y),
             -p.VETRO_L / 2 - 4, p.MICROFONO_Y - 1.3, "microfono")

    quota_oriz(msp, -p.VETRO_L / 2, p.VETRO_L / 2, p.VETRO_H, 10)
    quota_vert(msp, 0, p.VETRO_H, p.VETRO_L / 2, 14)
    quota_vert(msp, p.FINESTRA_DISPLAY_Y,
               p.FINESTRA_DISPLAY_Y + p.FINESTRA_DISPLAY_H,
               -p.VETRO_L / 2, -14)

    y = -14.0
    for riga in [
        "VETRO FRONTALE VIDEOCITOFONO",
        f"Corning Gorilla Glass 3, {p.VETRO_S} mm, rinforzato chimicamente",
        "CS > 650 MPa, DOL > 40 um. Bordi 2.5D lucidati",
        f"profilo {p.VETRO_L} x {p.VETRO_H}, raggi R{p.VETRO_RAGGIO:.0f}",
        "",
        "ATTENZIONE - ORIENTAMENTO: il disegno e' in vista dalla faccia",
        "esterna (faccia 1). La serigrafia va sulla faccia interna, quindi",
        "il film va SPECCHIATO rispetto a questo file. Riferimento di",
        "controllo: il foro del microfono deve restare a sinistra guardando",
        "il pannello da fuori, come indicato dalla marca 'FUORI'.",
        "",
        "LAYER TAGLIO: profilo esterno + foro microfono, al CNC sul crudo",
        "LAYER SERIGRAFIA: stampa nera coprente sul retro (faccia 2),",
        "  inchiostro UV industriale resistente ai raggi UV",
        "LAYER FINESTRE: aree da lasciare trasparenti nella stampa",
        "LAYER SMOKE: stampa semitrasparente 15-20% per icona NFC,",
        "  da ottenere con meno passate dello stesso inchiostro",
        "LAYER INGOMBRI: battuta di incollaggio, riferimento, non lavorare",
        "",
        "TRATTAMENTI sulla faccia esterna (faccia 1):",
        "  antiriflesso AR, trasmissione > 94%",
        "  oleofobico anti-impronta AF, angolo di contatto > 110 gradi",
        "Nessun antiriflesso sulla faccia interna: e' laminata al display con",
        "adesivo ottico, quindi non c'e' interfaccia vetro-aria da trattare.",
        "",
        "SEQUENZA DI PRODUZIONE, vincolante:",
        "  1. taglio e lavorazioni CNC sul vetro crudo",
        "  2. rinforzo chimico per scambio ionico (CS > 650 MPa)",
        "  3. stampa serigrafica, inchiostro UV a bassa temperatura",
        "  4. trattamenti AR e AF",
        "Il rinforzo va fatto dopo le lavorazioni e prima della stampa: lo",
        "scambio ionico avviene a 400-450 C e l'inchiostro UV non lo subisce.",
    ]:
        nota(msp, -p.VETRO_L / 2, y, riga)
        y -= 4.5

    doc.saveas(USCITA / "01-vetro-frontale.dxf")


# --------------------------------------------------------------------------
# 2. Telaio portante
# --------------------------------------------------------------------------

def telaio_portante() -> None:
    doc = nuovo_disegno()
    msp = doc.modelspace()

    # Tutto il disegno e' nel sistema del vetro: il telaio e' centrato, quindi
    # il suo bordo inferiore sta a TELAIO_Y0 e non a zero.
    rettangolo(msp, p.TELAIO_L, p.TELAIO_H, y0=p.TELAIO_Y0, raggio=2.0)

    # Dietro il display il telaio e' pieno: fa da appoggio al pannello e porta
    # i fori del Raspberry. Passa solo il flat, da un'asola sul bordo basso.
    rettangolo(msp, p.DISPLAY_MODULO_L, p.DISPLAY_MODULO_H,
               y0=p.DISPLAY_MODULO_Y0, layer="INGOMBRI")
    nota(msp, -p.DISPLAY_MODULO_L / 2,
         p.DISPLAY_MODULO_Y0 + p.DISPLAY_MODULO_H + 1.5,
         f"appoggio display {p.DISPLAY_MODULO_L:.0f} x"
         f" {p.DISPLAY_MODULO_H:.0f} - non forare", 2.6)
    rettangolo(msp, p.FLAT_ASOLA_L, p.FLAT_ASOLA_H, cx=p.FLAT_ASOLA_X,
               y0=p.FLAT_ASOLA_Y - p.FLAT_ASOLA_H / 2, raggio=2.0)
    richiamo(msp, (p.FLAT_ASOLA_X + p.FLAT_ASOLA_L / 2, p.FLAT_ASOLA_Y),
             p.TELAIO_L / 2 + 6, p.FLAT_ASOLA_Y - 1.3, "flat display")

    # Fissaggio del Raspberry Pi, sul retro del telaio: la scheda e' centrata
    # in altezza, col lato lungo in verticale e l'RJ45 verso il basso. Da qui
    # i micro-HDMI finiscono sul fianco destro, che va percio' tenuto libero.
    pi_cx = 0.0
    pi_y0 = p.PI_Y0
    off_x = (p.PI_H - 2 * p.PI_MARGINE_FORI) / 2   # lato corto in orizzontale
    for sx in (-1, 1):
        for sy in (0, 1):
            foro(msp, pi_cx + sx * off_x,
                 pi_y0 + p.PI_MARGINE_FORI + sy * p.PI_FORI_X,
                 p.PI_FORO_D, layer="FILETTATURA")
    rettangolo(msp, p.PI_H, p.PI_L, y0=pi_y0, layer="INGOMBRI")

    # Camera: fori di fissaggio e passaggio della lente. I fori sono decentrati
    # rispetto al foro dell'ottica, perche' sul Camera Module 3 l'asse ottico
    # non cade al centro dei quattro fori.
    for fx, fy in p.posizioni_fori_camera():
        foro(msp, fx, fy, p.CAMERA_FORO_D, layer="FILETTATURA")
    foro(msp, p.CAMERA_X, p.OTTICA_Y, p.CAMERA_LENTE_D + p.GIOCO_LENTE_TELAIO)
    rettangolo(msp, p.CAMERA_PCB_L, p.CAMERA_PCB_H,
               cx=p.CAMERA_X, y0=p.CAMERA_PCB_Y0 - p.CAMERA_PCB_H / 2,
               layer="INGOMBRI")
    # Le note dei componenti stanno fuori dal profilo, coi richiami: dentro
    # finivano sopra il taglio e sopra i fori.
    fuori_dx = p.TELAIO_L / 2 + 6
    fuori_sx = -p.TELAIO_L / 2 - 6
    richiamo(msp, (p.CAMERA_X + p.CAMERA_PCB_L / 2, p.OTTICA_Y),
             fuori_dx, p.OTTICA_Y + 3,
             f"ottica a {p.CAMERA_ASSE_OFFSET:.1f} sopra i fori")
    richiamo(msp, (p.CAMERA_X + p.CAMERA_PCB_L / 2, p.OTTICA_Y - 8),
             fuori_dx, p.OTTICA_Y - 4,
             f"colonnine {p.CAMERA_COLONNINE:.0f} mm")

    # Microfono: la basetta e' incollata al vetro, davanti al telaio. Qui
    # serve solo l'asola per i fili.
    rettangolo(msp, p.MIC_ASOLA_L, p.MIC_ASOLA_H, cx=p.MICROFONO_X,
               y0=p.MIC_ASOLA_Y - p.MIC_ASOLA_H / 2, raggio=1.5)
    rettangolo(msp, p.MIC_PCB_L, p.MIC_PCB_H, cx=p.MICROFONO_X,
               y0=p.MICROFONO_Y - p.MIC_PCB_H / 2, layer="INGOMBRI")
    richiamo(msp, (p.MICROFONO_X - p.MIC_PCB_L / 2, p.MICROFONO_Y),
             fuori_sx, p.MICROFONO_Y + 4, "microfono I2S")

    # Altoparlante: luce davanti al cono e tre fori filettati. Il corpo sta
    # arretrato nel vano, su colonnine, per scavalcare la camera.
    rettangolo(msp, p.SPEAKER_LUCE_L, p.SPEAKER_LUCE_H, cx=p.SPEAKER_X,
               y0=p.SPEAKER_LUCE_Y - p.SPEAKER_LUCE_H / 2, raggio=2.0)
    for fx, fy in p.posizioni_fori_speaker():
        foro(msp, fx, fy, p.SPEAKER_FORO_D, layer="FILETTATURA")
    rettangolo(msp, p.SPEAKER_L, p.SPEAKER_H, cx=p.SPEAKER_X,
               y0=p.SPEAKER_Y - p.SPEAKER_H / 2, layer="INGOMBRI")

    # Lettore NFC dietro la zona bassa del pannello. Il telaio e' aperto per
    # tutta l'antenna: l'alluminio alle spalle della bobina azzererebbe la
    # portata di lettura.
    rettangolo(msp, p.NFC_APERTURA_L, p.NFC_APERTURA_H, cx=p.NFC_X,
               y0=p.NFC_Y - p.NFC_APERTURA_H / 2, raggio=2.0)
    rettangolo(msp, p.NFC_PCB_L, p.NFC_PCB_H, cx=p.NFC_PCB_X,
               y0=p.NFC_Y - p.NFC_PCB_H / 2, layer="INGOMBRI")
    # La spira, per far vedere che l'apertura ci cade dentro e che non e'
    # centrata sulla scheda.
    rettangolo(msp, p.NFC_ANTENNA_L, p.NFC_ANTENNA_H, cx=p.NFC_X,
               y0=p.NFC_Y - p.NFC_ANTENNA_H / 2, layer="INGOMBRI")
    for fx, fy in p.posizioni_fori_nfc():
        foro(msp, fx, fy, p.NFC_FORO_D, layer="FILETTATURA")

    # Aggancio ai perni della cassa: due fori in alto.
    for sx in (-1, 1):
        foro(msp, sx * p.PERNO_PASSO / 2,
             p.TELAIO_Y0 + p.TELAIO_H - p.PERNO_MARGINE / 2, p.PERNO_FORO_D)
    # Sedi dei magneti: fori passanti, il magnete si incolla a filo del retro.
    for mx, my in p.posizioni_magneti():
        foro(msp, mx, my, p.MAGNETE_SEDE_D)
    nota(msp, p.TELAIO_L / 2 + 4, p.TELAIO_Y0 + 2.0,
         f"6x sede magnete O{p.MAGNETE_D:.0f} passante", 2.6)

    # Reed switch di antimanomissione: solo ingombro, si incolla sul retro.
    rettangolo(msp, p.REED_L, p.REED_H, cx=p.REED_X,
               y0=p.TELAIO_Y0 + 8.0, layer="INGOMBRI")
    nota(msp, p.REED_X - p.REED_L / 2, p.TELAIO_Y0 + 14.0, "reed", 2.6)

    # Ingombro della scheda di ingresso, in piedi sul fianco: non e' una lavorazione,
    # serve a non montare nulla in quella fascia.
    rettangolo(msp, p.DRIVER_S, p.DRIVER_L, cx=p.DRIVER_X,
               y0=p.DRIVER_Y - p.DRIVER_L / 2, layer="INGOMBRI")
    richiamo(msp, (p.DRIVER_X - p.DRIVER_S / 2, p.DRIVER_Y + 8),
             fuori_sx, p.DRIVER_Y + 8, "scheda di ingresso")
    rettangolo(msp, p.TERMINALE_S, p.TERMINALE_H, cx=p.TERMINALE_X,
               y0=p.TERMINALE_Y - p.TERMINALE_H / 2, layer="INGOMBRI")
    richiamo(msp, (p.TERMINALE_X - p.TERMINALE_S / 2, p.TERMINALE_Y),
             fuori_sx, p.TERMINALE_Y, "schedina terminale")

    # I due fori della squadretta che tiene in piedi la scheda di ingresso.
    # Sono gli unici fori ciechi del pezzo, e vanno segnati come tali: cadono
    # nell'ombra del display, che corre a 1 mm dal fronte del telaio.
    for sx, sy in p.posizioni_fori_staffa():
        foro(msp, sx, sy, p.STAFFA_FORO_TELAIO_D, layer="FILETTATURA")
    sx, sy = min(p.posizioni_fori_staffa(), key=lambda f: f[1])
    richiamo(msp, (sx, sy), fuori_sx, sy - 8,
             f"2x M2.5 CIECHI prof. {p.STAFFA_FORO_PROF:.1f} (squadretta)",
             layer="FILETTATURA")

    y = -14.0
    for riga in [
        "TELAIO PORTANTE",
        f"alluminio 5754 o 6082 da {p.TELAIO_S} mm, anodizzato nero opaco",
        f"profilo {p.TELAIO_L} x {p.TELAIO_H}",
        "",
        "LAYER TAGLIO: profilo, asola del flat, luci e fori passanti",
        "LAYER FILETTATURA: i diametri sono PREFORI, non passaggi.",
        "  O1.60 = M2 camera (4), O2.05 = M2.5 Pi (4) e squadretta (2),",
        "  O2.50 = M3 altoparlante (3) e lettore NFC (2).",
        "  (le sedi magnete e i fori perno stanno sul layer TAGLIO)",
        f"  I due M2.5 della squadretta sono CIECHI dal retro,",
        f"  profondi {p.STAFFA_FORO_PROF:.1f} su {p.TELAIO_S:.0f}: passanti,"
        " la vite tocca il pannello.",
        "LAYER INGOMBRI: sagome dei componenti, riferimento di montaggio",
        "",
        "Il Raspberry va montato su distanziali da "
        f"{p.PI_DISTANZIALI:.0f} mm con il dissipatore verso il fondo cassa,",
        "per lasciare libero il canale d'aria fra scheda e telaio.",
        "",
        f"La zona {p.DISPLAY_MODULO_L:.0f} x {p.DISPLAY_MODULO_H:.0f} del"
        " display resta piena: il pannello ha solo 1 mm di",
        "cornice e ci appoggia sopra col retro, e li' dentro cadono i quattro"
        " fori del Pi.",
        "",
        f"L'apertura {p.NFC_APERTURA_L:.0f} x {p.NFC_APERTURA_H:.0f} in basso"
        " non va chiusa ne' schermata: il lettore NFC si",
        "monta sul retro del telaio e legge attraverso di essa. Non e'"
        " centrata, perche' non lo e' la spira:",
        f"la scheda e' 60 x 38 ma l'antenna occupa solo la sua meta', e cade"
        f" {abs(p.NFC_ANTENNA_OFFSET_X):.1f} mm a sinistra.",
        "Dei quattro fori della scheda se ne filettano due, quelli a destra:"
        " gli altri cadono sull'apertura.",
        "",
        f"L'asola {p.MIC_ASOLA_L:.0f} x {p.MIC_ASOLA_H:.0f} in alto a sinistra"
        f" e' solo il passaggio dei fili: la basetta del microfono si",
        f"incolla al vetro, davanti al telaio, dietro al suo foro, e sta nei"
        f" {p.Z_TELAIO - p.VETRO_S:.1f} mm del biadesivo.",
        "",
        f"La camera si monta arretrata su colonnine da"
        f" {p.CAMERA_COLONNINE:.0f} mm: l'obiettivo sporge",
        f"{p.CAMERA_ALTEZZA:.1f} mm dal retro del suo PCB e deve attraversare"
        " il foro per",
        f"arrivare a {p.CAMERA_GIOCO_VETRO:.1f} mm dal vetro. I suoi quattro"
        " fori sono decentrati",
        f"di {p.CAMERA_ASSE_OFFSET:.2f} mm sotto l'asse ottico: non e' un"
        " errore, e' il",
        "decentramento dell'ottica dichiarato dal costruttore.",
        "",
        f"L'altoparlante si monta arretrato di"
        f" {p.SPEAKER_ARRETRAMENTO:.0f} mm dal retro del telaio,",
        "su colonnine, per scavalcare la camera. Tre viti M3: la quarta"
        " cadrebbe",
        "dietro la basetta del microfono. Viti corte, non devono affiorare"
        " sul fronte.",
        "",
        "Il telaio si centra sui due perni in alto e si tiene sui sei",
        "magneti. Nessuna vite: sul fronte finirebbe sotto il vetro",
        "incollato, dal basso avrebbe la testa annegata nella malta.",
        "",
        f"Magneti neodimio N42 O{p.MAGNETE_D:.0f} x {p.MAGNETE_S:.0f},"
        " incollati a filo della faccia posteriore",
        "con epossidica. Attenzione alla polarita': tutti nello stesso verso.",
    ]:
        nota(msp, -p.TELAIO_L / 2, y, riga)
        y -= 4.5

    doc.saveas(USCITA / "02-telaio-portante.dxf")


# --------------------------------------------------------------------------
# 3. Cassa da incasso
# --------------------------------------------------------------------------

def cassa_incasso() -> None:
    doc = nuovo_disegno()
    msp = doc.modelspace()
    estremo = p.CASSA_L / 2 + p.FLANGIA
    z_fer = p.Z_TELAIO + p.FESSURA_ARRETRAMENTO
    y_basso = (p.VETRO_H - p.CASSA_H) / 2   # faccia esterna della parete bassa

    # --- pianta: sezione orizzontale all'altezza delle feritoie laterali ---
    # La profondita' cresce verso l'alto del foglio e parte dal piano
    # dell'intonaco finito, che e' il fronte della cornice.
    msp.add_line((-estremo - 6, 0), (estremo + 6, 0),
                 dxfattribs={"layer": "QUOTE"})
    rettangolo(msp, p.CASSA_L, p.CASSA_PROF, y0=p.Z_TELAIO)
    rettangolo(msp, p.CASSA_INT_L, p.CASSA_PROF - p.CASSA_PARETE,
               y0=p.Z_TELAIO, layer="INGOMBRI")
    for sx in (-1, 1):
        # anello di battuta, feritoia nel fianco, flangia e cornice
        rettangolo(msp, p.BATTUTA, p.BATTUTA_PROF,
                   cx=sx * (p.CASSA_INT_L / 2 - p.BATTUTA / 2),
                   y0=p.Z_TELAIO + p.TELAIO_S)
        rettangolo(msp, p.CASSA_PARETE, p.FESSURA_ALTEZZA,
                   cx=sx * (p.CASSA_L / 2 - p.CASSA_PARETE / 2), y0=z_fer)
        rettangolo(msp, p.FLANGIA, p.CASSA_PARETE,
                   cx=sx * (p.CASSA_L / 2 + p.FLANGIA / 2),
                   y0=p.Z_FLANGIA, layer="PIEGA")
        rettangolo(msp, p.CORNICE_S, p.Z_FLANGIA,
                   cx=sx * (p.LUCE_INTONACO_L / 2 + p.CORNICE_S / 2),
                   y0=0, layer="PIEGA")
    quota_vert(msp, 0, p.Z_TELAIO, estremo, 6)
    quota_vert(msp, z_fer, z_fer + p.FESSURA_ALTEZZA, estremo, 6)
    quota_vert(msp, 0, p.Z_FLANGIA, estremo, 20)
    quota_oriz(msp, -p.LUCE_INTONACO_L / 2, p.LUCE_INTONACO_L / 2, 0, -8)
    nota(msp, -estremo, p.Z_TELAIO + p.CASSA_PROF + 4,
         "PIANTA all'altezza delle feritoie laterali: in basso il piano"
         " dell'intonaco finito", 3.0)

    # --- parete bassa vista da sotto, con la cornice in trasparenza ---
    base = p.Z_TELAIO + p.CASSA_PROF + 24.0
    rettangolo(msp, p.CASSA_L, p.CASSA_PROF, y0=base + p.Z_TELAIO)
    rettangolo(msp, p.FESSURA_LARGHEZZA, p.FESSURA_ALTEZZA,
               y0=base + z_fer)
    rettangolo(msp, p.CORNICE_L, p.Z_FLANGIA, y0=base, layer="PIEGA")
    rettangolo(msp, p.CASSA_L + 2 * p.FLANGIA, p.CASSA_PARETE,
               y0=base + p.Z_FLANGIA, layer="PIEGA")
    quota_oriz(msp, -p.FESSURA_LARGHEZZA / 2, p.FESSURA_LARGHEZZA / 2,
               base + z_fer + p.FESSURA_ALTEZZA, 30)
    nota(msp, -estremo, base + p.Z_TELAIO + p.CASSA_PROF + 4,
         "PARETE BASSA vista da sotto: l'unica feritoia rivolta in basso."
         " La parete alta e' chiusa.", 3.0)

    # --- fianco destro (il sinistro e' speculare), visto da fuori ---
    # In orizzontale la profondita' dal piano dell'intonaco, in verticale
    # l'altezza con lo zero sul bordo basso del vetro.
    ox = estremo + 40.0

    def fianco(z1, z2, y1, y2, layer="TAGLIO"):
        rettangolo(msp, z2 - z1, y2 - y1, cx=ox + (z1 + z2) / 2, y0=y1,
                   layer=layer)

    fianco(p.Z_TELAIO, p.Z_TELAIO + p.CASSA_PROF, y_basso,
           y_basso + p.CASSA_H)
    fianco(z_fer, z_fer + p.FESSURA_ALTEZZA, p.FESSURA_LATO_Y0,
           p.FESSURA_LATO_Y1)
    fianco(p.Z_TELAIO, p.Z_FLANGIA, p.FESSURA_LATO_Y1 + 1.0,
           p.FESSURA_LATO_Y1 + 1.0 + p.GOCCIOLATOIO, "SMOKE")
    fianco(p.Z_FLANGIA, p.Z_FLANGIA + p.CASSA_PARETE,
           y_basso - p.FLANGIA, y_basso + p.CASSA_H + p.FLANGIA, "PIEGA")
    fianco(0, p.Z_FLANGIA, (p.VETRO_H - p.CORNICE_H) / 2,
           (p.VETRO_H + p.CORNICE_H) / 2, "PIEGA")
    quota_vert(msp, p.FESSURA_LATO_Y0, p.FESSURA_LATO_Y1,
               ox + p.Z_TELAIO + p.CASSA_PROF, 8)
    nota(msp, ox, y_basso + p.CASSA_H + p.FLANGIA + 4,
         "FIANCO, visto da fuori: feritoia e gocciolatoio", 3.0)

    # --- fondo, con i passaggi dei cavi ---
    base2 = base + p.Z_TELAIO + p.CASSA_PROF + 26.0
    rettangolo(msp, p.CASSA_L, p.CASSA_H, y0=base2)
    for sx in (-1, 1):
        foro(msp, sx * p.CORRUGATO_PASSO / 2,
             base2 + 26.0 - y_basso, p.CORRUGATO_D)
    nota(msp, -p.CASSA_L / 2, base2 + p.CASSA_H + 4,
         "FONDO visto da dietro: passaggi dei corrugati", 3.0)

    # --- prospetto frontale: cornice, bocca, battuta e flangia ---
    base3 = base2 + p.CASSA_H + 26.0 + p.FLANGIA
    dy = base3 - y_basso                    # dalla quota del vetro al foglio
    rettangolo(msp, p.CASSA_L + 2 * p.FLANGIA, p.CASSA_H + 2 * p.FLANGIA,
               y0=base3 - p.FLANGIA, raggio=4.0, layer="PIEGA")
    rettangolo(msp, p.CORNICE_L, p.CORNICE_H,
               y0=dy + (p.VETRO_H - p.CORNICE_H) / 2, layer="PIEGA")
    rettangolo(msp, p.LUCE_INTONACO_L, p.LUCE_INTONACO_H,
               y0=dy + (p.VETRO_H - p.LUCE_INTONACO_H) / 2, layer="PIEGA")
    rettangolo(msp, p.CASSA_L, p.CASSA_H, y0=base3)
    # Luce della battuta, con lo scarico lungo la squadretta sul fianco
    # sinistro (visto da fuori la x cresce verso destra, come nel modello).
    bx = p.CASSA_INT_L / 2 - p.BATTUTA
    by0 = dy + (p.VETRO_H - p.CASSA_INT_H) / 2 + p.BATTUTA
    by1 = dy + (p.VETRO_H + p.CASSA_INT_H) / 2 - p.BATTUTA
    s0, s1 = dy + p.SCARICO_STAFFA_Y0, dy + p.SCARICO_STAFFA_Y1
    msp.add_lwpolyline(
        [(-bx, by0), (bx, by0), (bx, by1), (-bx, by1), (-bx, s1),
         (p.SCARICO_STAFFA_X, s1), (p.SCARICO_STAFFA_X, s0), (-bx, s0)],
        close=True, dxfattribs={"layer": "TAGLIO"})
    # Perni di centraggio sulla battuta alta.
    for sx in (-1, 1):
        foro(msp, sx * p.PERNO_PASSO / 2,
             dy + (p.VETRO_H + p.TELAIO_H) / 2 - p.PERNO_MARGINE / 2,
             p.PERNO_D, layer="FILETTATURA")
    # Fori di ancoraggio nella malta, fuori dalla cornice.
    for sx in (-1, 1):
        for i in range(p.FLANGIA_FORI_N):
            foro(msp, sx * p.FLANGIA_FORI_X,
                 dy + p.VETRO_H / 2
                 + (i - (p.FLANGIA_FORI_N - 1) / 2) * p.FLANGIA_FORI_PASSO,
                 p.FLANGIA_FORO_D)
    # Sedi dei riscontri sulla battuta. Sono una lavorazione e non un
    # riferimento, quindi stanno sul layer delle lavorazioni: disegnate fra gli
    # INGOMBRI venivano lette come "non lavorare" e il dischetto finiva
    # appoggiato sopra, dove alza il gruppo. Accanto resta il magnete come
    # riferimento, per far vedere che le due circonferenze non sono concentriche
    # e che non e' una svista. Le quote sono quelle del vetro, quindi si
    # riportano al foglio con lo stesso dy della cassa: col bordo del telaio
    # al posto di quello della cassa finivano 2,5 mm piu' in basso.
    for mx, my in p.posizioni_magneti():
        foro(msp, mx, my + dy, p.MAGNETE_D, layer="INGOMBRI")
    for sx, sy in p.posizioni_riscontri():
        foro(msp, sx, sy + dy, p.RISCONTRO_SEDE_D, layer="FILETTATURA")
    nota(msp, -estremo, base3 + p.CASSA_H + p.FLANGIA + 4,
         "PROSPETTO FRONTALE: cornice, bocca, battuta, riscontri, flangia",
         3.0)

    sez = p.sezioni_aria()
    y = -16.0
    for riga in [
        "CASSA DA INCASSO - disegno di controllo della cassa stampata",
        f"corpo {p.CASSA_L:.0f} x {p.CASSA_H:.0f} x {p.CASSA_PROF:.0f},"
        f" con la cornice {p.CORNICE_L:.0f} x {p.CORNICE_H:.0f} e profonda"
        f" {p.Z_TELAIO + p.CASSA_PROF:.0f} in tutto",
        f"nicchia da scavare {p.FORO_MURO_L:.0f} x {p.FORO_MURO_H:.0f}"
        f" x {p.FORO_MURO_PROF:.0f}, profondita' dal filo dell'intonaco",
        "",
        "Si stampa da stl/cassa.stl in ASA. Questo foglio serve a controllare",
        "il pezzo e a murarlo, non a produrlo: cornice, gocciolatoi e smussi",
        "non sono una scatola piegata.",
        f"PARETE {p.CASSA_PARETE} mm, MASSIMO"
        f" {(p.CASSA_L - p.TELAIO_L - 1.0) / 2:.1f}: il telaio da"
        f" {p.TELAIO_L:.0f} x {p.TELAIO_H:.0f} va dentro il vano, e la misura",
        "esterna la fissa la fessura d'ombra. Parete piu' grossa = non entra.",
        "",
        "LAYER in questo foglio:",
        "  TAGLIO (rosso): corpo, battuta e tutte le aperture passanti",
        "  PIEGA (giallo): cornice d'intonaco e flangia di muratura",
        "  SMOKE (blu): gocciolatoi sopra le feritoie laterali",
        "  FILETTATURA (verde): sedi non passanti, due perni e sei riscontri",
        "  INGOMBRI (grigio): magneti del telaio e vano, per riferimento",
        "",
        "LA CORNICE e' il riferimento della posa: il suo fronte va a filo",
        "dell'intonaco finito, e allora il vetro e' a filo anche lui. Il",
        f"fronte del corpo sta {p.Z_TELAIO:.0f} mm piu' indietro. Fra cornice e"
        f" corpo resta un canale di {p.CANALE_PERIMETRALE:.0f} mm,"
        " chiuso in fondo dalla",
        f"flangia a {p.Z_FLANGIA:.0f} mm: la malta resta fuori, l'aria passa.",
        "",
        "FERITOIE: una in basso, rivolta in basso, e due nei fianchi in alto.",
        "Nessuna nella parete alta, dove guarderebbe in su sotto la fessura",
        "d'ombra e prenderebbe l'acqua che entra. Partono"
        f" a {p.FESSURA_ARRETRAMENTO:.0f} mm dal fronte",
        "del corpo, dietro la battuta: quattro magneti stanno dentro la",
        "larghezza di quella bassa e l'anello deve restare intero.",
        f"Bassa {p.FESSURA_LARGHEZZA:.0f} x {p.FESSURA_ALTEZZA:.0f},"
        f" laterali {p.FESSURA_LATO_L:.0f} x {p.FESSURA_ALTEZZA:.0f}:"
        f" {sez['ingresso']:.0f} cm2 per verso, {sez['ingresso_libera']:.1f}"
        .replace(".", ",") + " tolta la rete.",
        f"Rete inox maglia {p.RETE_MAGLIA} filo {p.RETE_FILO},"
        .replace(".", ",") + " incollata all'interno.",
        "",
        f"Due perni O{p.PERNO_D:.0f} x {p.PERNO_SPORGENZA:.0f} sulla battuta"
        f" alta, passo {p.PERNO_PASSO:.0f}: centrano il telaio.",
        "Il gruppo si tiene su sei magneti alloggiati nel telaio di",
        "alluminio, e la cassa stampata non ha ferro: vanno sei dischetti di",
        f"acciaio dolce O{p.RISCONTRO_D:.0f} x {p.RISCONTRO_S:.0f}, uno per",
        "magnete, ANNEGATI nelle sedi del layer FILETTATURA:",
        f"O{p.RISCONTRO_SEDE_D} profonde {p.RISCONTRO_SEDE_PROF}, sulla faccia"
        " dove appoggia il telaio.",
        "Appoggiati sopra invece che annegati si infilerebbero fra battuta e",
        f"magnete e alzerebbero il gruppo di {p.RISCONTRO_S:.0f} mm, mentre il"
        " vetro va a filo dell'intonaco.",
        "Le sedi NON sono concentriche ai magneti, che sono disegnati accanto",
        f"sul layer INGOMBRI: stanno sull'asse dell'anello, {p.BATTUTA / 2:.0f}"
        " mm dal bordo del vano,",
        "perche' centrate sul magnete sborderebbero dentro. Il dischetto copre",
        "comunque tutto il magnete, che e' quello che conta.",
        "Sul fianco sinistro l'anello si restringe a"
        f" {p.CASSA_INT_L / 2 - abs(p.SCARICO_STAFFA_X):.1f}"
        .replace(".", ",") + " mm per",
        f"{p.SCARICO_STAFFA_Y1 - p.SCARICO_STAFFA_Y0:.0f} mm: e' lo scarico"
        " per la squadretta della scheda di ingresso.",
        "",
        "POSA: il muro e' in tufo. Bagnare la nicchia a rifiuto prima di",
        "murare, altrimenti il tufo assorbe l'acqua d'impasto e la malta non",
        "fa presa. La cassa va murata a piombo e in bolla, senza pendenze: il",
        "vetro e' parallelo alla cornice, e inclinarla lo porterebbe fuori",
        "filo in alto o in basso. L'acqua esce dalla feritoia bassa.",
    ]:
        nota(msp, -estremo, y, riga)
        y -= 4.5

    doc.saveas(USCITA / "03-cassa-incasso.dxf")


# --------------------------------------------------------------------------
# 4. Dima di muratura
# --------------------------------------------------------------------------

def dima_muratura() -> None:
    doc = nuovo_disegno()
    msp = doc.modelspace()

    # Tutto riferito al centro del vetro, cosi' la dima si allinea all'asse.
    cy = p.VETRO_H / 2
    rettangolo(msp, p.FORO_MURO_L, p.FORO_MURO_H,
               y0=cy - p.FORO_MURO_H / 2, raggio=4.0)
    rettangolo(msp, p.CASSA_L + 2 * p.FLANGIA, p.CASSA_H + 2 * p.FLANGIA,
               y0=cy - p.CASSA_H / 2 - p.FLANGIA, raggio=4.0,
               layer="INGOMBRI")
    rettangolo(msp, p.CORNICE_L, p.CORNICE_H, y0=cy - p.CORNICE_H / 2,
               layer="SMOKE")
    rettangolo(msp, p.LUCE_INTONACO_L, p.LUCE_INTONACO_H,
               y0=cy - p.LUCE_INTONACO_H / 2, layer="PIEGA")
    rettangolo(msp, p.VETRO_L, p.VETRO_H, y0=0,
               raggio=p.VETRO_RAGGIO, layer="FINESTRE")

    # Assi di tracciamento.
    msp.add_line((0, -20), (0, p.VETRO_H + 20), dxfattribs={"layer": "QUOTE"})
    msp.add_line((-p.FORO_MURO_L / 2 - 15, cy),
                 (p.FORO_MURO_L / 2 + 15, cy),
                 dxfattribs={"layer": "QUOTE"})

    y = -26.0
    for riga in [
        "DIMA DI TRACCIAMENTO 1:1",
        "Stampare in scala 1:1 (verificare la quota di controllo in cima),",
        "appoggiare al muro con l'asse verticale a piombo e tracciare.",
        "",
        f"TAGLIO (rosso): nicchia da scavare, {p.FORO_MURO_L:.0f} x"
        f" {p.FORO_MURO_H:.0f} x {p.FORO_MURO_PROF:.0f} mm,",
        "  la profondita' misurata dalla superficie dell'intonaco",
        f"INGOMBRI (grigio): flangia della cassa,"
        f" {p.CASSA_L + 2 * p.FLANGIA:.0f} x {p.CASSA_H + 2 * p.FLANGIA:.0f}",
        f"SMOKE (blu): bordo esterno della cornice, {p.CORNICE_L:.0f} x"
        f" {p.CORNICE_H:.0f}: l'intonaco finisce qui",
        f"PIEGA (giallo): luce, cioe' bordo interno della cornice,"
        f" {p.LUCE_INTONACO_L:.0f} x {p.LUCE_INTONACO_H:.0f}",
        f"FINESTRE (ciano): filo del vetro, {p.VETRO_L:.0f} x {p.VETRO_H:.0f}",
        "",
        f"Fra giallo e ciano corre la fessura d'ombra di"
        f" {p.OMBRA_PERIMETRALE:.0f} mm, aperta su tutti e",
        "quattro i lati: e' la via d'aria. La fa la cornice, non il rasante.",
        "",
        "Muro in tufo: si scava facilmente e si arriverebbe a 170 mm, ma la",
        f"nicchia va fatta di {p.FORO_MURO_PROF:.0f} e non di piu'. Bagnarla a"
        " rifiuto prima di murare.",
    ]:
        nota(msp, -p.FORO_MURO_L / 2, y, riga)
        y -= 4.5

    # Quota di controllo stampa: se non misura 100 mm, la scala e' sbagliata.
    yq = cy + p.FORO_MURO_H / 2 + 10
    msp.add_line((-50, yq), (50, yq), dxfattribs={"layer": "NOTE"})
    for x in (-50, 50):
        msp.add_line((x, yq - 3), (x, yq + 3), dxfattribs={"layer": "NOTE"})
    nota(msp, -22, yq + 3, "controllo stampa: 100 mm", 3.0)

    doc.saveas(USCITA / "04-dima-muratura.dxf")


# --------------------------------------------------------------------------
# 5. Disposizione dei componenti
# --------------------------------------------------------------------------

def disposizione() -> None:
    """Mappa dei componenti: pianta dal retro e sezione in profondita'.

    Non e' un disegno da mandare in produzione, e' quello da guardare per
    capire dove va cosa. I volumi vengono da parametri.componenti(), la stessa
    lista che usa il controllo di interferenza, quindi se il disegno mostra
    due pezzi che si toccano il controllo lo sta gia' dicendo.
    """
    doc = nuovo_disegno()
    msp = doc.modelspace()
    comp = p.componenti()

    # ---- vista A: pianta vista dal retro -------------------------------
    nota(msp, -p.VETRO_L / 2, (p.VETRO_H + p.CASSA_H) / 2 + p.FLANGIA + 6,
         "A - PIANTA DAL RETRO: dove va cosa", 4.0, "TAGLIO")
    rettangolo(msp, p.VETRO_L, p.VETRO_H, raggio=p.VETRO_RAGGIO,
               layer="FINESTRE")
    rettangolo(msp, p.TELAIO_L, p.TELAIO_H, y0=p.TELAIO_Y0, layer="TAGLIO")

    # I nomi stanno nella legenda in fondo al foglio e nel disegno restano i
    # numeri: sei degli otto componenti si sovrappongono in pianta, e le
    # etichette per esteso diventavano illeggibili le une sulle altre.
    for n, (nome, x1, y1, z1, x2, y2, z2) in enumerate(comp, 1):
        msp.add_lwpolyline(
            [(x1, y1), (x2, y1), (x2, y2), (x1, y2)], close=True,
            dxfattribs={"layer": "INGOMBRI"})

    # Le fasce libere servono a rispondere a "ci sta anche questo?", e la
    # domanda ha senso solo nel vano dietro il telaio: il display e la basetta
    # del microfono stanno davanti, su un altro piano, e includerli
    # restringerebbe fasce che in realta' sono liberissime.
    z_retro = p.Z_TELAIO + p.TELAIO_S
    confini = sorted((c[2], c[5]) for c in comp if c[6] > z_retro)
    occupato: list[list[float]] = []
    for a, b in confini:
        if occupato and a <= occupato[-1][1]:
            occupato[-1][1] = max(occupato[-1][1], b)
        else:
            occupato.append([a, b])
    y = p.TELAIO_Y0
    fasce = []
    for a, b in occupato + [[p.TELAIO_Y0 + p.TELAIO_H] * 2]:
        if a - y > 6:
            msp.add_lwpolyline(
                [(-p.TELAIO_L / 2, y), (p.TELAIO_L / 2, y),
                 (p.TELAIO_L / 2, a), (-p.TELAIO_L / 2, a)], close=True,
                dxfattribs={"layer": "PIEGA"})
            fasce.append((y, a))
        y = max(y, b)

    # Le scritte vanno messe dopo tutta la geometria della vista, perche'
    # etichetta_libera() schiva solo quello che e' gia' disegnato.
    occupate: list = []
    for y, a in fasce:
        etichetta_libera(msp, -p.TELAIO_L / 2 + 2, (y + a) / 2 - 1.5,
                         f"nel vano: libero {a - y:.0f} mm", 2.5, "PIEGA",
                         occupate)
    for n, (nome, x1, y1, z1, x2, y2, z2) in enumerate(comp, 1):
        etichetta_libera(msp, x2 - 5, y2 - 5, f"{n}", 4.0, "QUOTE", occupate)

    # ---- vista B: sezione in profondita' -------------------------------
    # Asse orizzontale = z, cioe' la profondita' misurata dalla faccia del
    # vetro; asse verticale = y, la stessa della pianta. Le due viste sono
    # quindi allineate in altezza e si leggono affiancate.
    dx = p.VETRO_L / 2 + 55
    fondo = p.fondo_interno()
    nota(msp, dx, (p.VETRO_H + p.CASSA_H) / 2 + p.FLANGIA + 6,
         "B - SEZIONE: profondita' da sinistra (vetro) a destra (fondo)",
         4.0, "TAGLIO")

    def sez(z1, y1, z2, y2, layer):
        msp.add_lwpolyline(
            [(dx + z1, y1), (dx + z2, y1), (dx + z2, y2), (dx + z1, y2)],
            close=True, dxfattribs={"layer": layer})

    sez(0, 0, p.VETRO_S, p.VETRO_H, "FINESTRE")                  # vetro
    sez(p.Z_TELAIO, p.TELAIO_Y0, p.Z_TELAIO + p.TELAIO_S,
        p.TELAIO_Y0 + p.TELAIO_H, "TAGLIO")                      # telaio
    # Cassa: pareti orizzontali e fondo, nelle loro posizioni vere. Le pareti
    # stanno all'interno del contorno esterno CASSA_H, e il fondo finisce
    # dove finisce la cassa.
    y_basso = (p.VETRO_H - p.CASSA_H) / 2
    y_alto = (p.VETRO_H + p.CASSA_H) / 2
    z_fer = p.Z_TELAIO + p.FESSURA_ARRETRAMENTO
    sez(p.Z_TELAIO, y_basso, p.Z_TELAIO + p.CASSA_PROF,
        y_basso + p.CASSA_PARETE, "SMOKE")
    sez(p.Z_TELAIO, y_alto - p.CASSA_PARETE, p.Z_TELAIO + p.CASSA_PROF,
        y_alto, "SMOKE")
    sez(fondo, y_basso, fondo + p.CASSA_PARETE, y_alto, "SMOKE")
    # Cornice e flangia, sopra e sotto.
    for y1, y2 in ((y_basso - p.CANALE_PERIMETRALE - p.CORNICE_S,
                    y_basso - p.CANALE_PERIMETRALE),
                   (y_alto + p.CANALE_PERIMETRALE,
                    y_alto + p.CANALE_PERIMETRALE + p.CORNICE_S)):
        sez(0, y1, p.Z_FLANGIA, y2, "SMOKE")
    sez(p.Z_FLANGIA, y_basso - p.FLANGIA, p.Z_FLANGIA + p.CASSA_PARETE,
        y_basso, "SMOKE")
    sez(p.Z_FLANGIA, y_alto, p.Z_FLANGIA + p.CASSA_PARETE,
        y_alto + p.FLANGIA, "SMOKE")
    # La feritoia bassa sta nel piano della sezione; le laterali sono sui
    # fianchi e qui si vedono in proiezione.
    sez(z_fer, y_basso, z_fer + p.FESSURA_ALTEZZA, y_basso + p.CASSA_PARETE,
        "TAGLIO")
    sez(z_fer, p.FESSURA_LATO_Y0, z_fer + p.FESSURA_ALTEZZA,
        p.FESSURA_LATO_Y1, "TAGLIO")
    for n, (nome, x1, y1, z1, x2, y2, z2) in enumerate(comp, 1):
        sez(z1, y1, z2, y2, "INGOMBRI")

    # Il canale d'aria, che e' il vincolo del raffreddamento.
    zmax = max(c[6] for c in comp)
    sez(zmax, y_basso, fondo, y_alto, "PIEGA")
    quota_oriz(msp, dx + zmax, dx + fondo, y_basso, -12)
    quota_oriz(msp, dx, dx + p.Z_TELAIO + p.CASSA_PROF, 0, -26)

    # Le scritte dopo la geometria, come nella pianta. Fuori dal disegno
    # quelle lunghe, dentro solo i numeri dei componenti.
    z_fuori = p.Z_TELAIO + p.CASSA_PROF + 4
    richiamo(msp, (dx + z_fer, y_basso), dx - 3, y_basso - 12,
             f"feritoia bassa {p.FESSURA_LARGHEZZA:.0f}x{p.FESSURA_ALTEZZA:.0f}",
             2.5, "TAGLIO")
    richiamo(msp, (dx + z_fer, p.FESSURA_LATO_Y1), dx - 3,
             p.FESSURA_LATO_Y1 + 4,
             f"feritoie laterali {p.FESSURA_LATO_L:.0f}x{p.FESSURA_ALTEZZA:.0f}",
             2.5, "TAGLIO")
    richiamo(msp, (dx + fondo, y_basso + 20), dx + z_fuori, y_basso + 20,
             f"canale d'aria {p.canale_aria():.1f} mm"
             f" = {p.CASSA_INT_L * p.canale_aria() / 100:.1f} cm2", 3.0,
             "PIEGA")
    for n, (nome, x1, y1, z1, x2, y2, z2) in enumerate(comp, 1):
        etichetta_libera(msp, dx + z2 + 1, y2 - 5, f"{n}", 4.0, "QUOTE",
                         occupate)

    y = -40
    righe_legenda = ["LEGENDA   (quote in mm, z dalla faccia esterna del vetro)",
                     "  n  componente          pianta        z"]
    for n, (nome, x1, y1, z1, x2, y2, z2) in enumerate(comp, 1):
        righe_legenda.append(
            f" {n:2}  {nome:18}  {x2 - x1:4.0f} x {y2 - y1:4.0f}"
            f"   {z1:5.1f} .. {z2:5.1f}")
    righe_legenda.append("")
    for riga in righe_legenda + [
        "DISPOSIZIONE DEI COMPONENTI",
        "Vista dal retro a sinistra, sezione in profondita' a destra.",
        "Le due viste sono allineate in altezza: una riga orizzontale",
        "attraversa lo stesso punto del pannello in entrambe.",
        "",
        "INGOMBRI (grigio): volume occupato, da parametri.componenti()",
        "PIEGA (giallo): in pianta le fasce libere nel vano dietro il telaio,",
        "  in sezione il canale d'aria. Il display e la basetta del microfono",
        "  stanno davanti al telaio e non restringono quelle fasce.",
        "SMOKE (blu): cassa, cornice e flangia   TAGLIO (rosso): telaio e"
        " feritoie;",
        "  in sezione la feritoia bassa e' tagliata, le laterali stanno sui"
        " fianchi e si vedono in proiezione.",
        "FINESTRE (ciano): vetro",
        "",
        f"La z si misura dalla faccia esterna del vetro. Il fronte della cassa"
        f" sta a {p.Z_TELAIO:.1f},",
        f"il fondo interno a {fondo:.1f}: sono due riferimenti diversi e vanno"
        " tenuti distinti.",
        "",
        f"Gruppo del Pi: {p.PI_GRUPPO_H:.1f} mm dal telaio, di cui"
        f" {p.PI_DISTANZIALI:.1f} di distanziali sotto la scheda."
        .replace(".", ",", 2),
        f"In quei {p.PI_DISTANZIALI:.0f} mm ci sta la base NVMe, che con l'SSD"
        f" montato ne misura {p.NVME_BASE_S}: sono"
        .replace(".", ",", 1),
        "due quote diverse e il controllo verifica che la prima contenga la"
        " seconda.",
        f"Canale d'aria residuo {p.canale_aria():.1f} mm. Il controllo di"
        " interferenza protesta",
        "quando la sua sezione scende sotto quella lorda di una feritoia,"
        " cioe' con un",
        f"gruppo da {p.gruppo_massimo():.0f} mm:"
        f" {p.gruppo_massimo() - p.PI_GRUPPO_H:.0f} in piu' di quanto misura"
        " oggi.",
        "",
        "Cosa questo disegno NON dice: i percorsi dei cavi. L'ansa dei fili fra",
        "la base dell'SSD e i pin in cima allo stack non e' modellata, e nei",
        f"fianchi restano {(p.CASSA_INT_L - p.PI_H) / 2:.1f} mm per lato dove"
        " passa anche il cavo di rete.",
    ]:
        nota(msp, -p.VETRO_L / 2, y, riga)
        y -= 4.5

    doc.saveas(USCITA / "05-disposizione.dxf")


# --------------------------------------------------------------------------
# 6. Il gruppo del display: come si monta
# --------------------------------------------------------------------------

def gruppo_display() -> None:
    """Come si monta il gruppo del display, ora che e' tutto misurato.

    Non e' un disegno di produzione e non e' piu' una scheda di rilievo: e' il
    foglio che risponde alle due domande che le misure hanno aperto. Come si
    spartiscono i 3,0 mm fra vetro e telaio, visto che il display misurato ne
    occupa 2,0 e il microfono 2,5; e dove passano i due flat, visto che le
    schede sono due e stanno entrambe su un fianco.

    Il foglio si compone da se': ogni sezione dichiara quanto spazio le serve e
    il cursore scende.
    """
    doc = nuovo_disegno()
    msp = doc.modelspace()
    cursore = 0.0

    def righe(x, y, testi, altezza=2.4, passo=3.8, layer="NOTE"):
        for k, t in enumerate(testi):
            nota(msp, x, y - k * passo, t, altezza, layer)
        return y - len(testi) * passo

    def sezione(titolo: str, sottotitolo: str, alto: float) -> float:
        nonlocal cursore
        msp.add_line((0, cursore), (250, cursore),
                     dxfattribs={"layer": "QUOTE"})
        nota(msp, 0, cursore - 8, titolo, 5.0, "TAGLIO")
        nota(msp, 0, cursore - 14, sottotitolo, 2.8, "SMOKE")
        base = cursore - 20 - alto
        cursore = base - 12
        return base

    nota(msp, 0, 14, "IL GRUPPO DEL DISPLAY: COME SI MONTA", 6.0, "TAGLIO")
    righe(0, 6, [
        "Il pannello e' 70 x 125, spesso 1,8 con la coda ripiegata, e la sua"
        " scheda e' in due pezzi. Tutto misurato. Ne",
        "seguono due cose che nessun'altra tavola mostra: come si spartisce lo"
        " spessore dietro il vetro, ora che il",
        "display ne occupa meno di quanto si pensava, e dove passano i due"
        " flat, ora che le schede sono due."],
        2.8, 4.5, "SMOKE")
    cursore = -12.0

    # =============== 1. la sezione dietro il vetro =======================
    base = sezione("1 - LO SPESSORE DIETRO IL VETRO",
                   "in sezione, ingrandita 8 volte: chi fissa la distanza del"
                   " telaio dal vetro, e cosa ci sta dentro", 112.0)
    k = 8.0                            # ingrandimento della sezione
    x0 = 0.0
    # Il vetro, sempre presente, e i due casi appaiati.
    for colonna, (titolo, componenti) in enumerate((
            ("nella zona del display", (
                ("vetro, 2,0", p.VETRO_S, "TAGLIO"),
                ("adesivo ottico, 0,2", p.BIADESIVO_DISPLAY_S, "FINESTRE"),
                (f"pannello, {p.DISPLAY_PANNELLO_S}", p.DISPLAY_PANNELLO_S,
                 "SMOKE"),
                ("dentro il modulo", p.DISPLAY_MODULO_S
                 - p.DISPLAY_PANNELLO_S - p.DISPLAY_CODA_S, "QUOTE"),
                (f"coda ripiegata, {p.DISPLAY_CODA_S}", p.DISPLAY_CODA_S,
                 "FILETTATURA"),
                (f"aria, {p.DISPLAY_ARIA_TELAIO:.1f}: il display NON"
                 f" tocca il telaio", p.DISPLAY_ARIA_TELAIO, "QUOTE"),
                (f"telaio, {p.TELAIO_S:.0f}", p.TELAIO_S, "TAGLIO"))),
            ("nella zona del microfono", (
                ("vetro, 2,0", p.VETRO_S, "TAGLIO"),
                (f"basetta, {p.MIC_INGOMBRO_S}", p.MIC_INGOMBRO_S, "SMOKE"),
                (f"aria, {p.Z_TELAIO - p.VETRO_S - p.MIC_INGOMBRO_S:.1f}",
                 p.Z_TELAIO - p.VETRO_S - p.MIC_INGOMBRO_S, "QUOTE"),
                (f"telaio, {p.TELAIO_S:.0f}", p.TELAIO_S, "TAGLIO"))))):
        cx = x0 + colonna * 120.0
        nota(msp, cx, base + 106, titolo, 3.2, "TAGLIO")
        z = base + 40
        # Gli strati sottili sono piu' bassi del testo che li nomina: le
        # etichette si tengono quindi a passo fisso e si collegano con una
        # linea guida al loro strato.
        y_etichetta = z
        for nome, spessore, layer in componenti:
            if spessore <= 0:
                continue
            rettangolo(msp, 40, spessore * k, cx=cx + 20, y0=z, layer=layer)
            y_etichetta = max(y_etichetta + 4.4, z + spessore * k / 2 - 1)
            msp.add_line((cx + 40, z + spessore * k / 2),
                         (cx + 43, y_etichetta + 1),
                         dxfattribs={"layer": "QUOTE"})
            nota(msp, cx + 44, y_etichetta, nome, 2.6)
            if nome.startswith(("telaio", "la finestra")):
                z_telaio = z
            z += spessore * k
        # La quota utile e' una sola: quanto spazio c'e' fra la faccia interna
        # del vetro e il fronte del telaio. Nella colonna del microfono quel
        # posto lo chiede la basetta, e il confronto fra i due numeri e' il
        # motivo per cui la finestra esiste.
        msp.add_linear_dim(base=(cx - 8, base + 40),
                           p1=(cx, base + 40 + p.VETRO_S * k),
                           p2=(cx, z_telaio), angle=90,
                           text=f"{(z_telaio - base - 40) / k - p.VETRO_S:.1f}",
                           dxfattribs={"layer": "QUOTE"}).render()

    righe(0, base + 32, [
        f"La distanza del telaio dal vetro -"
        f" {p.Z_TELAIO - p.VETRO_S:.1f} mm, e quindi Z_TELAIO, da cui parte"
        f" tutto il resto del progetto - la fissa il",
        f"biadesivo che tiene su il telaio, non il display. Il nastro e'"
        f" {p.BIADESIVO_S:.1f} mm perche' era stato scelto per pareggiare"
        f" display",
        f"piu' adesivo, che il progetto assumeva spessi altrettanto: misurati"
        f" fanno"
        f" {p.BIADESIVO_DISPLAY_S + p.DISPLAY_MODULO_S:.1f}, e il nastro resta"
        f" quello.",
        "",
        f"Restano cosi' {p.DISPLAY_ARIA_TELAIO:.1f} mm d'aria dietro il"
        f" display, e vanno bene: il pannello e' incollato in pieno al vetro"
        f" con",
        "l'adesivo ottico, che su una lastra da 0,4 mm basta e avanza, e la"
        " coda ripiegata resta libera invece di",
        "essere schiacciata dall'alluminio. Un VHB da 2,0 esiste, ma la"
        " schiuma piu' spessa assorbe meglio le",
        "ondulazioni del vetro temperato e le dilatazioni differenziali, e"
        " quel millimetro non serve a nessun altro.",
        "",
        f"Il microfono e' il componente che quello spazio lo usa per intero:"
        f" {p.MIC_INGOMBRO_S:.1f} mm su"
        f" {p.Z_TELAIO - p.VETRO_S:.1f}, con mezzo millimetro"
        f" di",
        "margine. E' per questo che il nastro del telaio non si assottiglia:"
        " non c'e' solo il display, dietro il vetro."])

    # ================= 2. il percorso dei due flat =======================
    base = sezione("2 - IL PERCORSO DEI DUE FLAT",
                   "il telaio visto dal retro, in scala 1:1: le schede"
                   " stanno entrambe sul fianco sinistro", 236.0)
    ty = base
    rettangolo(msp, p.TELAIO_L, p.TELAIO_H, cx=p.TELAIO_L / 2 + 6,
               y0=ty, layer="QUOTE")
    ox = p.TELAIO_L / 2 + 6           # asse del telaio nel foglio

    def px(x):                        # da coordinate progetto a foglio
        return ox + x

    def py(y):
        return ty + y - p.TELAIO_Y0

    # il display e la sua coda
    rettangolo(msp, p.DISPLAY_MODULO_L, p.DISPLAY_MODULO_H, cx=px(0),
               y0=py(p.DISPLAY_MODULO_Y0), layer="SMOKE")
    rettangolo(msp, p.DISPLAY_CODA_L, p.DISPLAY_CODA_H, cx=px(0),
               y0=py(p.DISPLAY_MODULO_Y0), layer="FILETTATURA")
    # l'asola, le due schede
    rettangolo(msp, p.FLAT_ASOLA_L, p.FLAT_ASOLA_H, cx=px(p.FLAT_ASOLA_X),
               y0=py(p.FLAT_ASOLA_Y) - p.FLAT_ASOLA_H / 2, layer="TAGLIO")
    rettangolo(msp, p.TERMINALE_S, p.TERMINALE_H, cx=px(p.TERMINALE_X),
               y0=py(p.TERMINALE_Y) - p.TERMINALE_H / 2, layer="INGOMBRI")
    rettangolo(msp, p.DRIVER_S, p.DRIVER_L, cx=px(p.DRIVER_X),
               y0=py(p.DRIVER_Y) - p.DRIVER_L / 2, layer="INGOMBRI")
    # i due percorsi
    msp.add_lwpolyline([(px(p.FLAT_ASOLA_X), py(p.FLAT_ASOLA_Y)),
                        (px(p.FLAT_ASOLA_X), py(p.FLAT_ASOLA_Y) - 10),
                        (px(p.TERMINALE_X), py(p.FLAT_ASOLA_Y) - 10),
                        (px(p.TERMINALE_X), py(p.TERMINALE_Y))],
                       dxfattribs={"layer": "NOTE"})
    msp.add_line((px(p.TERMINALE_X), py(p.TERMINALE_Y)),
                 (px(p.DRIVER_X), py(p.DRIVER_Y)),
                 dxfattribs={"layer": "NOTE"})
    corsa_p = math.dist((p.FLAT_ASOLA_X, p.FLAT_ASOLA_Y),
                        (p.TERMINALE_X, p.TERMINALE_Y))
    corsa_d = math.dist((p.DRIVER_X, p.DRIVER_Y),
                        (p.TERMINALE_X, p.TERMINALE_Y))
    # il Pi, per capire perche' il resto e' occupato
    rettangolo(msp, p.PI_H, p.PI_L, cx=px(0), y0=py(p.PI_Y0), layer="QUOTE")

    # Le etichette stanno fuori dalla pianta, in colonna, e si collegano al
    # loro componente con una guida: dentro il telaio non c'e' un angolo
    # libero dove scriverle.
    def etichetta(x, y, testi, layer="NOTE"):
        msp.add_line((px(x), py(y)), (96, py(y)),
                     dxfattribs={"layer": "QUOTE"})
        righe(98, py(y) + (len(testi) - 1) * 1.9, testi, 2.4, 3.8, layer)

    etichetta(p.DRIVER_X, p.DRIVER_Y + 14, [
        f"scheda di ingresso, {p.DRIVER_L:.0f} x {p.DRIVER_H:.0f}",
        f"in piedi, {p.DRIVER_S} di spessore"])
    etichetta(p.DRIVER_X, p.DRIVER_Y - 18,
              ["HDMI-A e USB-C girati verso", "l'interno del vano"], "TAGLIO")
    etichetta(p.TERMINALE_X, p.TERMINALE_Y + 6, [
        f"schedina terminale,",
        f"{p.TERMINALE_L:.0f} x {p.TERMINALE_H:.0f}, anche lei in piedi"])
    etichetta(p.TERMINALE_X + 10, p.TERMINALE_Y - 10, [
        f"flat largo: {corsa_d:.0f} mm da coprire,",
        f"ne ha {p.FLAT_DRIVER_L:.0f}"], "FILETTATURA")
    etichetta(0, p.FLAT_ASOLA_Y, [
        f"asola {p.FLAT_ASOLA_L:.0f} x {p.FLAT_ASOLA_H:.0f}: ci passa solo il",
        f"flat, che e' largo {p.FLAT_PANNELLO_W:.0f}"])
    etichetta(-20, p.FLAT_ASOLA_Y - 10, [
        f"flat del pannello: {corsa_p:.0f} mm in linea",
        f"d'aria, ne ha {p.FLAT_PANNELLO_LUNG:.0f} ma con curve"],
        "FILETTATURA")
    etichetta(0, p.DISPLAY_MODULO_Y0 + 14, [
        f"la coda ripiegata,",
        f"{p.DISPLAY_CODA_L:.0f} x {p.DISPLAY_CODA_H:.0f}"])
    etichetta(0, p.DISPLAY_MODULO_Y0 + 90, ["display 70 x 125"], "SMOKE")
    etichetta(-20, p.PI_Y0 + 42, ["il Raspberry, e sotto di lui",
                                  "il flat PCIe e il patch"], "SMOKE")

    righe(155, base + 212, [
        "Le schede stanno entrambe sul fianco sinistro,",
        "in piedi, perche' in piano non c'e' posto: la",
        "fascia sotto il Pi e' occupata dall'ansa del flat",
        "PCIe e dal patch di rete, e quella sopra e' fuori",
        "dalla portata del flat del pannello.",
        "",
        "Il fianco destro non e' una scelta: e' quello dei",
        "micro-HDMI del Pi, e il suo cavo angolato ha",
        f"bisogno di tutti i {p.CASSA_INT_L / 2 - p.PI_H / 2:.1f} mm di luce.",
        "",
        "La schedina terminale sta cinquanta millimetri",
        "sotto la scheda di ingresso: e' l'unico punto che",
        "i due flat raggiungono entrambi. Spostarla piu'",
        "in alto la mette addosso alla scheda di ingresso,",
        "piu' in basso il flat del pannello non ci arriva.",
        "",
        "Il flat largo e' 25 mm: fra le due schede il suo",
        "piano sta parallelo al fianco, quindi quei 25 mm",
        "si sviluppano in profondita', dove ce ne sono",
        f"{p.fondo_interno() - p.Z_TELAIO - p.TELAIO_S:.1f}.".replace(".", ",", 1),
    ])

    # ================== 3. quello che resta ==============================
    base = sezione("3 - QUELLO CHE RESTA DA GUARDARE",
                   "del gruppo display non manca nessuna quota: manca"
                   " un'osservazione", 30.0)
    righe(0, base + 28, [
        "- il TOUCH e' integrato nel pannello, o e' una lastra separata"
        " incollata sopra? Se e' separata servono le sue",
        "  quote, e vanno a sommarsi ai 2,0 mm dietro il vetro, che sono gia'"
        " contesi col microfono.",
        "- su quale bordo sta il connettore del flat, su ciascuna delle due"
        " schede: da quello dipende come si girano",
        "  in piedi sul fianco, e quindi se i flat partono verso l'alto o"
        " verso il basso.",
        "- sulla scheda di ingresso c'e' una piazzola o un header di dimming"
        " del backlight, siglato BL_PWM, DIM, PWM o",
        "  ADJ? E' l'ultima speranza per abbassare la luminosita' di notte:"
        " /sys/class/backlight e' vuoto e il DDC/CI",
        "  non risponde. Se c'e', GPIO12 e GPIO13 sono liberi e sono canali"
        " PWM hardware del RP1."], 2.6, 4.2)

    doc.saveas(USCITA / "06-gruppo-display.dxf")

# --------------------------------------------------------------------------
# 7. Squadretta della scheda di ingresso e pezzi piani da tagliare
# --------------------------------------------------------------------------

def pezzi_minori() -> None:
    """I pezzi che restavano senza disegno, e senza i quali non si monta.

    La squadretta della scheda di ingresso era descritta come "biadesivo o una
    squadretta": qui diventa un pezzo con delle quote. Gli altri quattro sono
    ritagli piani che chiunque fa con un cutter, ma averli in scala 1:1 evita
    di misurarli sul pezzo montato.

    Le quote stanno sempre sopra o a lato del pezzo e il testo sempre sotto, a
    distanza fissa: su questi fogli composti a mano le collisioni fra quote e
    didascalie sono l'errore che torna ogni volta.
    """
    doc = nuovo_disegno()
    msp = doc.modelspace()

    def righe(x, y, testi, altezza=2.4, passo=4.0, layer="SMOKE"):
        for k, t in enumerate(testi):
            if t:
                nota(msp, x, y - k * passo, t, altezza, layer)
        return y - len(testi) * passo

    nota(msp, 0, 14, "SQUADRETTA DEL DISPLAY E PEZZI PIANI", 6.0, "TAGLIO")
    righe(0, 6, [
        "Tutto in scala 1:1. La squadretta e' da piegare, gli altri quattro"
        " sono ritagli. Le quote di piega sono",
        "nominali: la detrazione va rifatta sulla macchina di chi piega."],
        2.8, 4.5)

    # ================= 1. la squadretta ==================================
    msp.add_line((0, -16), (340, -16), dxfattribs={"layer": "QUOTE"})
    nota(msp, 0, -24, "1 - SQUADRETTA DELLA SCHEDA DI INGRESSO", 5.0, "TAGLIO")
    nota(msp, 0, -30, "alluminio 1,5 mm, una piega a 90 gradi."
         "  A sinistra lo sviluppo da tagliare, a destra il pezzo piegato"
         " in opera", 2.8)

    sv_l = p.STAFFA_L
    sv_h = p.STAFFA_ALA_H + p.STAFFA_ALA_BASE
    # Lo sviluppo: ala corta in basso, ala lunga sopra, piega fra le due.
    cx = 24.0 + sv_l / 2
    y0 = -58.0 - sv_h
    rettangolo(msp, sv_l, sv_h, cx=cx, y0=y0)
    y_piega = y0 + p.STAFFA_ALA_BASE
    msp.add_line((cx - sv_l / 2, y_piega), (cx + sv_l / 2, y_piega),
                 dxfattribs={"layer": "PIEGA"})

    z_foro1 = y_piega + 4.0
    z_foro2 = z_foro1 + p.DRIVER_FORI_Y
    for dy in (-p.DRIVER_FORI_X / 2, p.DRIVER_FORI_X / 2):
        for zf in (z_foro1, z_foro2):
            foro(msp, cx + dy, zf, p.STAFFA_FORO_SCHEDA_D)
    for dy in (-p.STAFFA_FORI_TELAIO_PASSO / 2, p.STAFFA_FORI_TELAIO_PASSO / 2):
        foro(msp, cx + dy, y0 + p.STAFFA_ALA_BASE / 2, p.STAFFA_FORO_ALA_D)

    # Quote: larghezza sopra, altezze a destra, interassi a sinistra.
    quota_oriz(msp, cx - sv_l / 2, cx + sv_l / 2, y0 + sv_h, 7.0)
    quota_oriz(msp, cx - p.DRIVER_FORI_X / 2, cx + p.DRIVER_FORI_X / 2,
               y0, -8.0)
    quota_vert(msp, y0, y0 + sv_h, cx + sv_l / 2, 26.0)
    quota_vert(msp, y0, y_piega, cx + sv_l / 2, 10.0)
    quota_vert(msp, z_foro1, z_foro2, cx - sv_l / 2, -10.0)
    nota(msp, cx + sv_l / 2 + 1.5, y_piega + 0.5, "piega", 2.4, "PIEGA")

    # Il pezzo piegato, visto di fianco, con lo spessore disegnato.
    vx = cx + sv_l / 2 + 58
    s = p.STAFFA_S
    msp.add_lwpolyline([
        (vx, y0), (vx + p.STAFFA_ALA_BASE, y0),
        (vx + p.STAFFA_ALA_BASE, y0 + s), (vx + s, y0 + s),
        (vx + s, y0 + sv_h - p.STAFFA_ALA_BASE), (vx, y0 + sv_h - p.STAFFA_ALA_BASE),
    ], close=True, dxfattribs={"layer": "TAGLIO"})
    # La scheda che ci appoggia, e il fianco della cassa che sta a sinistra.
    msp.add_lwpolyline([
        (vx + s, y0 + 4), (vx + s + p.DRIVER_S, y0 + 4),
        (vx + s + p.DRIVER_S, y0 + 4 + p.DRIVER_H), (vx + s, y0 + 4 + p.DRIVER_H),
    ], close=True, dxfattribs={"layer": "INGOMBRI"})
    nota(msp, vx + s + p.DRIVER_S + 1.5, y0 + 4 + p.DRIVER_H / 2, "scheda",
         2.4, "INGOMBRI")
    gioco = (p.CASSA_L / 2 - p.CASSA_PARETE) - abs(p.STAFFA_X - s / 2)
    msp.add_line((vx - gioco, y0 - 4), (vx - gioco, y0 + sv_h),
                 dxfattribs={"layer": "INGOMBRI"})
    nota(msp, vx - gioco - 2, y0 + sv_h + 3, "fianco cassa", 2.4, "INGOMBRI")
    quota_oriz(msp, vx - gioco, vx, y0 + sv_h - p.STAFFA_ALA_BASE, 6.0)

    righe(vx + 34, y0 + sv_h - 4, [
        "L'ala lunga sta contro il fianco e la scheda le",
        "appoggia dentro: dall'altra parte, verso il Pi,",
        "non ci sarebbe stato il plug HDMI.",
        "",
        f"L'ala corta si avvita al retro del telaio con due",
        f"viti M2.5 in fori CIECHI, profondi"
        f" {p.STAFFA_FORO_PROF:.1f} su {p.TELAIO_S:.0f}:",
        "cadono nell'ombra del display, che corre a 1 mm",
        "dal fronte del telaio. Passanti, la vite lo tocca.",
        "",
        f"Fra ala e fianco restano {gioco:.1f} mm, per le teste.",
    ], 2.5, 4.3)

    # ================= 2. i ritagli piani ===============================
    cursore = y0 - 26.0
    msp.add_line((0, cursore), (340, cursore), dxfattribs={"layer": "QUOTE"})
    nota(msp, 0, cursore - 8, "2 - RITAGLI PIANI, SCALA 1:1", 5.0, "TAGLIO")
    nota(msp, 0, cursore - 14, "sagome in scala 1:1 da riportare sul materiale",
         2.8)

    ritagli = [
        (f"OCA {p.DISPLAY_MODULO_L:.0f} x {p.DISPLAY_MODULO_H:.0f}",
         p.DISPLAY_MODULO_L, p.DISPLAY_MODULO_H,
         [f"adesivo ottico {p.BIADESIVO_DISPLAY_S:.2f} mm:".replace(".", ","),
          "scavalca il bordo serigrafato,",
          "chiedilo tagliato al fornitore"]),
        (f"PET {p.NFC_APERTURA_L + 8:.0f} x {p.NFC_APERTURA_H + 8:.0f}",
         p.NFC_APERTURA_L + 8, p.NFC_APERTURA_H + 8,
         ["PET nero opaco 0,2 mm:", "diaframma dietro l'apertura",
          f"NFC {p.NFC_APERTURA_L:.0f}x{p.NFC_APERTURA_H:.0f}, 4 mm di bordo"]),
        (f"rete {p.RETE_L:.0f} x {p.RETE_H:.0f}",
         p.RETE_L, p.RETE_H,
         [f"inox maglia {p.RETE_MAGLIA} filo {p.RETE_FILO}:".replace(".", ","),
          "un pezzo, per la feritoia bassa",
          f"{p.FESSURA_LARGHEZZA:.0f} x {p.FESSURA_ALTEZZA:.0f};"
          f" {p.RETE_SOVRAPPOSIZIONE / 2:.1f} mm di".replace(".", ","),
          "bordo per incollarla"]),
        (f"rete {p.RETE_LATO_L:.0f} x {p.RETE_H:.0f}",
         p.RETE_LATO_L, p.RETE_H,
         ["stessa rete: due pezzi, uno",
          "per feritoia laterale",
          f"{p.FESSURA_LATO_L:.0f} x {p.FESSURA_ALTEZZA:.0f}, stesso bordo"]),
    ]
    # Tutti i pezzi appoggiano sulla stessa linea di base e il testo sta
    # sotto quella linea, cosi' nessuna didascalia finisce su un disegno.
    y_cima = cursore - 34.0
    alto = max(a for _, _, a, _ in ritagli)
    y_terra = y_cima - alto
    x = 0.0
    for titolo, larghezza, altezza, descrizione in ritagli:
        rettangolo(msp, larghezza, altezza, cx=x + larghezza / 2, y0=y_terra)
        nota(msp, x, y_cima + 11, titolo, 3.2, "TAGLIO")
        quota_oriz(msp, x, x + larghezza, y_terra + altezza, 5.0)
        quota_vert(msp, y_terra, y_terra + altezza, x + larghezza, 7.0)
        righe(x, y_terra - 7, descrizione, 2.5, 4.3)
        x += max(larghezza, 62.0) + 22.0

    doc.saveas(USCITA / "07-staffa-e-pezzi-piani.dxf")


def main() -> int:
    USCITA.mkdir(parents=True, exist_ok=True)
    vetro_frontale()
    telaio_portante()
    cassa_incasso()
    dima_muratura()
    disposizione()
    gruppo_display()
    pezzi_minori()
    print("file generati in", USCITA)
    for f in sorted(USCITA.glob("*.dxf")):
        print(f"  {f.name:28} {f.stat().st_size // 1024} kB")
    print()
    print(p.riepilogo())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
