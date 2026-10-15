#!/usr/bin/env python3
"""Fotogrammi del videocitofono, in scala con parametri.py.

Un'immagine disegnata a occhio non tiene i 100 x 240 del vetro, la fessura
di 3 mm, la finestra 69 x 122, il foro del microfono a sinistra della lente
e la griglia di tre strisce. Qui ogni pixel nasce da una quota.

Le due foto schermata-*.jpg non si toccano: sono il display vero.

Uso, dalla cartella hardware:
    ../.venv-cad/bin/python render/componi.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import parametri as p  # noqa: E402

QUI = Path(__file__).resolve().parent

VETRO = (12, 12, 14)
FESSURA = (36, 32, 28)
INTONACO = (228, 220, 206)
INTONACO_ALTO = (214, 206, 192)
TUFO = (196, 158, 102)
TUFO_FONDO = (142, 108, 68)
ASA = (138, 142, 148)
ASA_SCURO = (72, 76, 82)
ALLUMINIO = (54, 56, 60)
FORO = (14, 14, 16)
MALTA = (176, 168, 154)


def carattere(px: int, nero: bool = False) -> ImageFont.ImageFont:
    nome = "Arial Bold.ttf" if nero else "Arial.ttf"
    percorsi = [
        f"/System/Library/Fonts/Supplemental/{nome}",
        f"/Library/Fonts/{nome}",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for percorso in percorsi:
        if Path(percorso).is_file():
            return ImageFont.truetype(percorso, max(8, px))
    return ImageFont.load_default()


def muro(w: int, h: int, base, sigma: float, seed: int, alto=None) -> Image.Image:
    rng = np.random.default_rng(seed)
    img = np.empty((h, w, 3), np.float32)
    basso = np.array(base, np.float32)
    if alto is None:
        img[:] = basso
    else:
        t = np.linspace(0, 1, h, dtype=np.float32)[:, None]
        col = basso * (1 - t) + np.array(alto, np.float32) * t
        img[:] = col[:, None, :]
    for passo, peso in ((24, 0.65), (6, 0.35)):
        n = rng.normal(0, sigma * peso, ((h // passo) + 2, (w // passo) + 2))
        n = np.repeat(np.repeat(n, passo, 0), passo, 1)[:h, :w]
        img += n[..., None]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")


def attenua(im: Image.Image, k: float) -> Image.Image:
    if k >= 0.999:
        return im
    a = np.asarray(im).astype(np.float32)
    a[..., :3] *= k
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), im.mode)


def bagliore(im: Image.Image, cx: float, cy: float, raggio: float,
             forza: float, colore=(255, 206, 150),
             solo_sopra: float | None = None) -> Image.Image:
    """Luce che il pannello butta sull'intonaco. Il raggio e' in pixel.

    solo_sopra taglia la luce sotto quella riga: il volto sta sopra lo
    schermo e va illuminato dal basso, non il marciapiede.
    """
    h, w = im.size[1], im.size[0]
    yy, xx = np.mgrid[0:h, 0:w]
    dist = np.hypot(xx - cx, yy - cy)
    k = np.clip(1 - dist / raggio, 0, 1) ** 1.6 * forza
    if solo_sopra is not None:
        k *= np.clip((solo_sopra - yy) / 80, 0, 1)
    a = np.asarray(im).astype(np.float32)
    luce = np.array(colore, np.float32)
    a += (luce - a) * k[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")


class Piano:
    """x in mm dal centro del vetro, y in mm dal bordo inferiore. y dell'immagine verso il basso."""

    def __init__(self, base: Image.Image, ox: float, oy: float, s: float):
        self.base = base
        self.draw = ImageDraw.Draw(base)
        self.ox = ox
        self.oy = oy
        self.s = s

    def box(self, x: float, y: float, w: float, h: float) -> list[float]:
        """Rettangolo: centro x, bordo inferiore y, quote in mm."""
        x0 = self.ox + (x - w / 2) * self.s
        x1 = self.ox + (x + w / 2) * self.s
        y1 = self.oy - y * self.s
        y0 = self.oy - (y + h) * self.s
        return [x0, y0, x1, y1]

    def rett(self, x, y, w, h, **kw):
        self.draw.rectangle(self.box(x, y, w, h), **kw)

    def tondo(self, x, y, w, h, r, **kw):
        self.draw.rounded_rectangle(self.box(x, y, w, h), radius=max(1, r * self.s), **kw)

    def cerchio(self, x, y, d, **kw):
        self.draw.ellipse(self.box(x, y - d / 2, d, d), **kw)


def sfondo(w: int, h: int) -> Image.Image:
    """La geometria blu e arancio della schermata fotografata."""
    im = Image.new("RGB", (w, h), (16, 58, 140))
    d = ImageDraw.Draw(im)

    def poli(colore, *pti):
        d.polygon([(px * w, py * h) for px, py in pti], fill=colore)

    poli((20, 104, 186), (0, 0), (0.78, 0), (0.02, 0.58))
    poli((12, 40, 112), (0.28, 0), (1, 0), (1, 0.16), (0.48, 0.34))
    poli((18, 82, 176), (0, 0.22), (0.62, 0.04), (0.28, 0.62))
    poli((232, 148, 32), (0.40, 0.30), (1, 0.22), (1, 0.96), (0.12, 1))
    poli((214, 226, 234), (0, 0.60), (0.40, 0.74), (0.16, 1), (0, 1))
    poli((14, 46, 120), (0.08, 0.34), (0.70, 0.12), (0.42, 0.70), (0.02, 0.78))
    return im


def _tratto(d: ImageDraw.ImageDraw, w: int) -> int:
    return max(2, w // 18)


def icona(d: ImageDraw.ImageDraw, tipo: str, x: int, y: int, lato: int) -> None:
    """Icone bianche, al centro del quadrato x,y di lato `lato`."""
    c = "white"
    t = _tratto(d, int(lato))
    x, y, lato = int(x), int(y), int(lato)
    cx, cy = x + lato / 2, y + lato / 2
    r = lato * 0.30
    if tipo == "homer":
        d.ellipse([cx - r, cy - r * 0.9, cx + r, cy + r * 1.1], outline=c, width=t)
        d.ellipse([cx - r * 0.35, cy - r * 0.35, cx - r * 0.05, cy - r * 0.05], fill=c)
        d.ellipse([cx + r * 0.05, cy - r * 0.35, cx + r * 0.35, cy - r * 0.05], fill=c)
        d.arc([int(cx - r * 0.45), int(cy - r * 0.1), int(cx + r * 0.45), int(cy + r * 0.7)],
              15, 165, fill=c, width=t)
    elif tipo == "marge":
        d.polygon([(cx - r * 0.7, cy + r), (cx - r * 0.85, cy - r * 1.3),
                   (cx + r * 0.85, cy - r * 1.3), (cx + r * 0.7, cy + r)], outline=c)
        d.line([(cx - r * 0.7, cy + r), (cx + r * 0.7, cy + r)], fill=c, width=t)
        d.ellipse([cx - r * 0.55, cy - r * 0.15, cx + r * 0.55, cy + r * 0.95], outline=c, width=t)
    elif tipo == "cat":
        d.ellipse([cx - r, cy - r * 0.55, cx + r, cy + r], outline=c, width=t)
        d.polygon([(cx - r * 0.7, cy - r * 0.2), (cx - r * 0.95, cy - r * 1.15),
                   (cx - r * 0.15, cy - r * 0.45)], outline=c)
        d.polygon([(cx + r * 0.7, cy - r * 0.2), (cx + r * 0.95, cy - r * 1.15),
                   (cx + r * 0.15, cy - r * 0.45)], outline=c)
        d.ellipse([cx - r * 0.38, cy - r * 0.05, cx - r * 0.12, cy + r * 0.2], fill=c)
        d.ellipse([cx + r * 0.12, cy - r * 0.05, cx + r * 0.38, cy + r * 0.2], fill=c)
    elif tipo == "pin":
        passo = r * 0.55
        for j in range(3):
            for i in range(3):
                px = cx + (i - 1) * passo
                py = cy + (j - 1) * passo - r * 0.15
                d.ellipse([px - t, py - t, px + t, py + t], fill=c)
        d.line([(cx + r * 0.15, cy + r * 0.55), (cx + r * 0.85, cy + r * 1.15)], fill=c, width=t)
    elif tipo == "face":
        d.rounded_rectangle([cx - r, cy - r * 1.05, cx + r, cy + r * 1.05],
                            radius=r * 0.35, outline=c, width=t)
        d.line([(cx - r, cy - r * 0.45), (cx - r * 0.45, cy - r * 0.45)], fill=c, width=t)
        d.line([(cx + r * 0.45, cy - r * 0.45), (cx + r, cy - r * 0.45)], fill=c, width=t)
        d.arc([int(cx - r * 0.45), int(cy - r * 0.1), int(cx + r * 0.45), int(cy + r * 0.7)],
              20, 160, fill=c, width=t)
    elif tipo == "nfc":
        for k, f in enumerate((0.35, 0.65, 0.95)):
            rr = r * f
            d.arc([int(cx - rr), int(cy - rr), int(cx + rr), int(cy + rr)],
                  -55, 55, fill=c, width=t)


def schermo(modo: str, w: int, h: int, luce: float) -> Image.Image:
    im = sfondo(w, h).convert("RGBA")
    d = ImageDraw.Draw(im)
    if modo == "riposo":
        titolo = carattere(max(16, w // 11), nero=True)
        ora = carattere(max(12, w // 16), nero=True)
        data = carattere(max(10, w // 26))
        d.text((w / 2, h * 0.30), "Via Pirandello 5", font=titolo,
               fill="white", anchor="mm")
        d.line([(w * 0.38, h * 0.355), (w * 0.62, h * 0.355)], fill=(255, 255, 255, 180), width=1)
        d.text((w / 2, h * 0.40), "15:08", font=ora, fill="white", anchor="mm")
        d.text((w / 2, h * 0.455), "Sabato 10 ottobre 2026", font=data,
               fill=(255, 255, 255, 210), anchor="mm")
    elif modo == "chiamata":
        marg = int(w * 0.07)
        card_h = int(h * 0.115)
        gap = int(h * 0.02)
        top = int(h * 0.13)
        font = carattere(max(13, w // 18), nero=True)
        voci = (("Vincenzo Quaranta", "homer"),
                ("Stefania Rosano", "marge"),
                ("Click", "cat"))
        prima = None
        for i, (nome, tipo) in enumerate(voci):
            y = top + i * (card_h + gap)
            d.rounded_rectangle([marg, y, w - marg, y + card_h], radius=card_h // 5,
                                fill=(22, 26, 34, 188), outline=(255, 255, 255, 50))
            lato = int(card_h * 0.72)
            icona(d, tipo, marg + int(card_h * 0.18), y + (card_h - lato) // 2, lato)
            d.text((marg + card_h, y + card_h / 2), nome, font=font,
                   fill="white", anchor="lm")
            if i == 0:
                prima = (marg, y, w - marg, y + card_h)
        btn = int(w * 0.24)
        by = h - int(h * 0.07) - btn
        spazio = int(w * 0.04)
        tot = 3 * btn + 2 * spazio
        x0 = (w - tot) // 2
        for i, tipo in enumerate(("pin", "face", "nfc")):
            x = x0 + i * (btn + spazio)
            d.rounded_rectangle([x, by, x + btn, by + btn], radius=btn // 6,
                                fill=(22, 26, 34, 188), outline=(255, 255, 255, 50))
            inset = int(btn * 0.16)
            icona(d, tipo, x + inset, by + inset, btn - 2 * inset)
        if prima:
            # Dito che entra da destra e si appoggia sul bordo del primo
            # campanello, lasciando il nome leggibile.
            x1, y0, x2, y1 = prima
            fy = y1 - card_h * 0.28
            pelle = (214, 176, 142, 255)
            d.ellipse([x2 - card_h * 0.45, fy - card_h * 0.28,
                       x2 + card_h * 0.05, fy + card_h * 0.22], fill=pelle)
            d.rounded_rectangle([x2 - card_h * 0.22, fy - card_h * 0.12, w + 4, fy + card_h * 0.16],
                                radius=max(2, card_h // 5), fill=pelle)
    elif modo == "spento":
        d.rectangle([0, 0, w, h], fill=(8, 8, 10, 255))
    if luce < 0.999:
        im = Image.fromarray(
            (np.asarray(im).astype(np.float32) * np.array([luce, luce, luce, 1])).clip(0, 255).astype(np.uint8),
            "RGBA")
    return im.convert("RGB")


def disegna_vetro(piano: Piano, modo: str, luce: float,
                  a_muro: bool = True) -> tuple[float, float]:
    """Vetro finito. Ritorna il centro in pixel della finestra del display.

    a_muro disegna anche la fessura di 3 mm: va messa solo quando il vetro e'
    gia' a filo dell'intonaco. Mentre lo si posa, la fessura non c'e' ancora.
    """
    s = piano.s
    # La luce dell'intonaco e' squadrata; il vetro ha gli spigoli a 3 mm.
    if a_muro:
        piano.rett(0, -p.OMBRA_PERIMETRALE, p.LUCE_INTONACO_L, p.LUCE_INTONACO_H,
                   fill=FESSURA)
    piano.tondo(0, 0, p.VETRO_L, p.VETRO_H, p.VETRO_RAGGIO, fill=VETRO)

    y_att = p.FINESTRA_DISPLAY_Y + (p.FINESTRA_DISPLAY_H - p.DISPLAY_ATTIVO_H) / 2
    box = piano.box(0, y_att, p.DISPLAY_ATTIVO_L, p.DISPLAY_ATTIVO_H)
    pw, ph = round(box[2] - box[0]), round(box[3] - box[1])
    sch = schermo(modo, pw, ph, luce)
    piano.base.paste(sch, (round(box[0]), round(box[1])))

    for i in range(p.GRIGLIA_N):
        piano.tondo(0, p.GRIGLIA_Y + i * p.GRIGLIA_PASSO,
                    p.GRIGLIA_L, p.GRIGLIA_SPESSORE, p.GRIGLIA_SPESSORE / 2,
                    fill=(32, 32, 36))

    # Finestra dell'ottica, a filo: dietro si vede la lente da 4 mm, non un oblò.
    piano.cerchio(p.CAMERA_X, p.OTTICA_Y, p.OTTICA_D, fill=(6, 6, 8))
    piano.cerchio(p.CAMERA_X, p.OTTICA_Y, p.CAMERA_LENTE_FRONTALE_D, fill=(18, 20, 26))
    piano.cerchio(p.CAMERA_X - 0.6, p.OTTICA_Y + 0.7, 1.3, fill=(70, 74, 82))

    # Foro vero, a sinistra della lente, sulla stessa quota.
    piano.cerchio(p.MICROFONO_X, p.MICROFONO_Y, p.MICROFONO_D, fill=(4, 4, 6))

    # Icona sull'antenna, non al centro del pannello.
    piano.cerchio(p.NFC_X, p.NFC_Y, p.NFC_D, outline=(168, 168, 172),
                  width=max(1, round(0.35 * s)))
    box_n = piano.box(p.NFC_X, p.NFC_Y - p.NFC_D / 2, p.NFC_D, p.NFC_D)
    lato = box_n[2] - box_n[0]
    icona(piano.draw, "nfc", box_n[0], box_n[1], lato)

    # Lucentezza solo sulla serigrafia nera: non sposta nessun foro e non
    # copre il display. Il vetro si legge come vetro, le quote restano.
    lucida_serigrafia(piano)
    cx = (box[0] + box[2]) / 2
    cy = (box[1] + box[3]) / 2
    return cx, cy


def lucida_serigrafia(piano: Piano) -> None:
    im = np.asarray(piano.base).astype(np.float32)
    h, w = im.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    s = piano.s
    x0 = piano.ox - p.VETRO_L / 2 * s
    x1 = piano.ox + p.VETRO_L / 2 * s
    y_top = piano.oy - p.VETRO_H * s
    dentro = (xx >= x0) & (xx <= x1) & (yy >= y_top) & (yy <= piano.oy)
    nera = dentro & (im[:, :, 0] < 45) & (im[:, :, 1] < 45) & (im[:, :, 2] < 45)
    # I fori restano del colore disegnato: la lucentezza non li schiarisce,
    # altrimenti la finestra da 10 mm si confonde con la serigrafia.
    for x_mm, y_mm, diam in (
            (p.CAMERA_X, p.OTTICA_Y, p.OTTICA_D),
            (p.MICROFONO_X, p.MICROFONO_Y, p.MICROFONO_D)):
        cx = piano.ox + x_mm * s
        cy = piano.oy - y_mm * s
        nera &= (xx - cx) ** 2 + (yy - cy) ** 2 > (diam / 2 * s) ** 2
    t = np.clip((yy - y_top) / max(p.VETRO_H * s, 1), 0, 1)
    sheen = (1 - t) * 26
    for c in range(3):
        im[:, :, c] = np.where(nera, im[:, :, c] + sheen, im[:, :, c])
    piano.base.paste(Image.fromarray(np.clip(im, 0, 255).astype(np.uint8), "RGB"))


def porta(im: Image.Image, x0: int) -> None:
    d = ImageDraw.Draw(im)
    w, h = im.size
    d.rectangle([x0, 0, w, h], fill=(54, 36, 24))
    d.rectangle([x0, 0, x0 + max(4, (w - x0) // 18), h], fill=(36, 24, 16))
    # Bugna, solo per leggere che e' un'anta e non un'ombra.
    inset = max(10, (w - x0) // 8)
    d.rounded_rectangle([x0 + inset, int(h * 0.08), w - inset, int(h * 0.46)],
                        radius=8, outline=(74, 50, 32), width=3)
    d.rounded_rectangle([x0 + inset, int(h * 0.52), w - inset, int(h * 0.90)],
                        radius=8, outline=(74, 50, 32), width=3)


def volto(im: Image.Image, cx: int, cy: int, raggio: int, da_sopra: bool) -> None:
    """Visitatore visto di fronte. La luce arriva dal pannello, piu' in basso:
    il mento si accende, le orbite restano in ombra."""
    sov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(sov)
    r = raggio
    d.ellipse([cx - int(r * 1.7), cy + int(r * 0.72),
               cx + int(r * 1.7), cy + int(r * 2.5)],
              fill=(24, 22, 26, 255))
    d.ellipse([cx - int(r * 0.78), cy - r, cx + int(r * 0.78), cy + int(r * 0.92)],
              fill=(150, 112, 86, 255))
    # Capelli, cosi' non si legge una nuca.
    d.chord([cx - int(r * 0.78), cy - r, cx + int(r * 0.78), cy - int(r * 0.05)],
            200, 340, fill=(32, 26, 24, 255))
    occhio_y = cy - int(r * 0.08)
    for sx in (-1, 1):
        ex = cx + sx * int(r * 0.28)
        d.ellipse([ex - int(r * 0.16), occhio_y - int(r * 0.09),
                   ex + int(r * 0.16), occhio_y + int(r * 0.09)],
                  fill=(28, 22, 20, 255))
    d.polygon([(cx, cy + int(r * 0.02)),
               (cx - int(r * 0.08), cy + int(r * 0.28)),
               (cx + int(r * 0.08), cy + int(r * 0.28))],
              fill=(120, 86, 66, 255))
    d.arc([cx - int(r * 0.22), cy + int(r * 0.32), cx + int(r * 0.22), cy + int(r * 0.52)],
          20, 160, fill=(90, 58, 48, 255), width=max(2, r // 28))
    a = np.asarray(sov).astype(np.float32)
    yy = np.arange(im.size[1], dtype=np.float32)[:, None]
    # 0 sulla fronte, 1 sul mento: la luce sale dal pannello.
    t = np.clip((yy - (cy - r)) / (1.9 * r), 0, 1)
    if da_sopra:
        t = 1 - t
    k = (0.22 + 0.95 * t ** 1.35)[..., None]
    a[..., :3] *= k
    fascia = np.clip(1 - np.abs(yy - occhio_y) / (r * 0.22), 0, 1)
    a[..., :3] *= (1 - 0.45 * fascia)[..., None]
    faccia = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")
    im.paste(faccia, (0, 0), faccia)


def scena_parete(w, h, s, modo, luce, notte, glow, porta_x, volto_sotto, seme) -> Image.Image:
    base_col = (22, 18, 16) if notte else INTONACO
    alto = (16, 14, 12) if notte else INTONACO_ALTO
    im = muro(w, h, base_col, 5 if not notte else 3, seme, alto)
    ox = w / 2 if porta_x is None else min(w / 2, porta_x - (p.VETRO_L / 2 + 28) * s)
    vetro_h = p.VETRO_H * s
    if volto_sotto:
        # Il pannello sta in basso: lo schermo illumina il volto dal basso.
        oy = h - 36
    else:
        oy = (h + vetro_h) / 2
    if glow:
        # Quaranta centimetri di intonaco illuminato, come da specifica.
        # Sul volto il raggio e' piu' corto: e' la luce dello schermo, non la lampada.
        cx = ox
        cy = oy - (p.FINESTRA_DISPLAY_Y + p.FINESTRA_DISPLAY_H / 2) * s
        raggio = (400 if glow == "tutto" else 180) * s
        im = bagliore(im, cx, cy, raggio, 0.72 if glow == "tutto" else 0.45,
                      solo_sopra=(cy if glow == "volto" else None))
    if porta_x:
        porta(im, porta_x)
    if volto_sotto:
        r = int(62 * s)
        # Il mento resta una ventina di millimetri sopra il vetro.
        testa = int(oy - vetro_h - 18 * s - 0.55 * r)
        volto(im, int(ox), testa, r, da_sopra=False)
    piano = Piano(im, ox, oy, s)
    disegna_vetro(piano, modo, luce)
    return im


def cassa_nel_muro(piano: Piano, finita: bool) -> None:
    """Cassa murata. La flangia e' sotto malta: in vista c'e' la cornice,
    e a parete finita nemmeno quella."""
    if finita:
        return
    piano.rett(0, (p.VETRO_H - p.CORNICE_H) / 2, p.CORNICE_L, p.CORNICE_H, fill=ASA)
    piano.rett(0, (p.VETRO_H - p.LUCE_INTONACO_H) / 2,
               p.LUCE_INTONACO_L, p.LUCE_INTONACO_H, fill=(18, 18, 20))
    y_corpo = (p.VETRO_H - p.CASSA_H) / 2
    piano.rett(0, y_corpo, p.CASSA_L, p.CASSA_H, fill=ASA_SCURO)
    y_bocca = (p.VETRO_H - p.CASSA_INT_H) / 2
    piano.rett(0, y_bocca, p.CASSA_INT_L, p.CASSA_INT_H, fill=(12, 12, 14))
    for sx in (-1, 1):
        piano.cerchio(sx * p.CORRUGATO_PASSO / 2, 26, p.CORRUGATO_D, fill=(8, 8, 10))
        # Le coste del corrugato, perche' si legga un tubo e non un foro qualunque.
        for k in range(-3, 4):
            piano.cerchio(sx * p.CORRUGATO_PASSO / 2, 26,
                          p.CORRUGATO_D - 4 + (k % 2), outline=(32, 32, 34), width=1)


def telaio(piano: Piano, dy: float) -> None:
    """Fronte del telaio, quote vere. dy lo stacca dalla sede, in mm verso l'alto."""
    y0 = p.TELAIO_Y0 + dy
    piano.tondo(0, y0, p.TELAIO_L, p.TELAIO_H, 2, fill=ALLUMINIO)
    piano.rett(p.FLAT_ASOLA_X, p.FLAT_ASOLA_Y - p.FLAT_ASOLA_H / 2 + dy,
               p.FLAT_ASOLA_L, p.FLAT_ASOLA_H, fill=FORO)
    piano.cerchio(p.CAMERA_X, p.OTTICA_Y + dy,
                  p.CAMERA_LENTE_D + p.GIOCO_LENTE_TELAIO, fill=FORO)
    for x, y in p.posizioni_fori_camera():
        piano.cerchio(x, y + dy, p.CAMERA_FORO_D, fill=FORO)
    piano.rett(p.SPEAKER_X, p.SPEAKER_LUCE_Y - p.SPEAKER_LUCE_H / 2 + dy,
               p.SPEAKER_LUCE_L, p.SPEAKER_LUCE_H, fill=FORO)
    for x, y in p.posizioni_fori_speaker():
        piano.cerchio(x, y + dy, p.SPEAKER_FORO_D, fill=FORO)
    piano.rett(p.NFC_APERTURA_X, p.NFC_Y - p.NFC_APERTURA_H / 2 + dy,
               p.NFC_APERTURA_L, p.NFC_APERTURA_H, fill=FORO)
    piano.rett(p.MICROFONO_X, p.MIC_ASOLA_Y - p.MIC_ASOLA_H / 2 + dy,
               p.MIC_ASOLA_L, p.MIC_ASOLA_H, fill=FORO)
    for x, y in p.posizioni_magneti():
        piano.cerchio(x, y + dy, p.MAGNETE_SEDE_D, fill=(20, 20, 22))
    y_perno = (p.VETRO_H + p.TELAIO_H) / 2 - p.PERNO_MARGINE / 2
    for sx in (-1, 1):
        piano.cerchio(sx * p.PERNO_PASSO / 2, y_perno + dy, p.PERNO_FORO_D, fill=FORO)


def scena_instal(w, h, s, fase: str) -> Image.Image:
    im = muro(w, h, MALTA if fase != "nicchia" else INTONACO, 6, 11, INTONACO_ALTO)
    ox, oy = w / 2, h / 2 + (p.VETRO_H / 2) * s * 0.92
    # tieni il soggetto dentro il quadro
    meta = (p.FORO_MURO_H if fase == "nicchia" else p.CORNICE_H) / 2 * s
    oy = min(oy, h - 40 - (meta - p.VETRO_H / 2 * s))
    oy = max(oy, 40 + p.VETRO_H * s)
    piano = Piano(im, ox, oy, s)
    if fase == "nicchia":
        yb = p.VETRO_H / 2 - p.FORO_MURO_H / 2
        # Il rettangolo e' la nicchia quotata. Il fondo piu' scuro sta dentro,
        # non la rimpicciolisce.
        piano.rett(0, yb, p.FORO_MURO_L, p.FORO_MURO_H, fill=TUFO)
        piano.rett(0, yb + 6, p.FORO_MURO_L - 8, p.FORO_MURO_H - 12, fill=TUFO_FONDO)
        # I due corrugati arrivano dal fondo del foro, non a mezza altezza.
        for sx in (-1, 1):
            x = sx * p.CORRUGATO_PASSO / 2
            piano.rett(x, yb - 8, p.CORRUGATO_D, 70, fill=(18, 18, 20))
            for k in range(8):
                piano.rett(x, yb + k * 7, p.CORRUGATO_D, 2, fill=(48, 48, 52))
        return im
    cassa_nel_muro(piano, finita=False)
    if fase == "cassa":
        return im
    if fase == "telaio":
        telaio(piano, dy=36)
        # Cavo di rete che entra gia' innestato: esce da sotto il telaio.
        y = p.TELAIO_Y0 + 36
        box = piano.box(0, y - 28, 6, 36)
        piano.draw.rounded_rectangle(box, radius=4, fill=(16, 16, 18))
        return im
    if fase == "vetro":
        telaio(piano, dy=0)
        # Il vetro non e' ancora sui magneti: sta sopra la sede.
        salva = (piano.oy, )
        piano.oy = piano.oy - 28 * piano.s
        disegna_vetro(piano, "spento", 1, a_muro=False)
        piano.oy = salva[0]
        return im
    # finito
    im = muro(w, h, INTONACO, 5, 4, INTONACO_ALTO)
    piano = Piano(im, ox, oy, s)
    disegna_vetro(piano, "riposo", 1)
    return im


def scorcio(im: Image.Image, x_spigolo: int) -> None:
    """Parete di lato, in proiezione obliqua. La faccia col vetro non si scorcia."""
    w, h = im.size
    d = ImageDraw.Draw(im)
    prof = int(min(w - x_spigolo - 4, h * 0.22))
    alza = int(prof * 0.45)
    col = (196, 188, 174)
    d.polygon([(x_spigolo, 0), (x_spigolo + prof, alza),
               (x_spigolo + prof, h), (x_spigolo, h)], fill=col)
    # Una riga d'ombra sullo spigolo, per staccare le due facce.
    d.line([(x_spigolo, 0), (x_spigolo, h)], fill=(160, 152, 140), width=3)


def salva(im: Image.Image, nome: str) -> None:
    # Questi jpg sono i render del progetto: le foto generiche non tenevano
    # le quote, quindi il file pubblicato e' questo disegno.
    cartella = QUI / "scala"
    cartella.mkdir(exist_ok=True)
    for percorso in (QUI / nome, cartella / nome):
        im.save(percorso, quality=93, subsampling=0, optimize=True)
    print(f"  {nome}  {im.size[0]}x{im.size[1]}")


def controlla() -> None:
    """Le quote che i fotogrammi sono tenuti a rispettare, stampate e basta:
    il disegno le legge dallo stesso modulo, non da numeri ricopiati."""
    print("quote usate:")
    print(f"  vetro {p.VETRO_L:.0f} x {p.VETRO_H:.0f}  raggio {p.VETRO_RAGGIO:.0f}")
    print(f"  finestra {p.FINESTRA_DISPLAY_L:.2f} x {p.FINESTRA_DISPLAY_H:.2f}"
          f"  y {p.FINESTRA_DISPLAY_Y:.2f}")
    print(f"  ottica Ø{p.OTTICA_D:.0f} in ({p.CAMERA_X:.0f}, {p.OTTICA_Y:.0f})"
          f"   mic Ø{p.MICROFONO_D:.0f} in ({p.MICROFONO_X:.0f}, {p.MICROFONO_Y:.0f})")
    print(f"  nfc Ø{p.NFC_D:.0f} in ({p.NFC_X:.1f}, {p.NFC_Y:.0f})")
    print(f"  griglia {p.GRIGLIA_N} x {p.GRIGLIA_L:.0f} x {p.GRIGLIA_SPESSORE}"
          f"  y {p.GRIGLIA_Y:.0f} passo {p.GRIGLIA_PASSO}")
    print(f"  fessura {p.OMBRA_PERIMETRALE:.0f}   luce {p.LUCE_INTONACO_L:.0f} x"
          f" {p.LUCE_INTONACO_H:.0f}")
    print(f"  nicchia {p.FORO_MURO_L:.0f} x {p.FORO_MURO_H:.0f} x {p.FORO_MURO_PROF:.0f}")
    print(f"  cornice {p.CORNICE_L:.0f} x {p.CORNICE_H:.0f}   telaio"
          f" {p.TELAIO_L:.0f} x {p.TELAIO_H:.0f}")
    rapporto = p.VETRO_L / p.VETRO_H
    if abs(rapporto - 100 / 240) > 1e-9:
        raise SystemExit("il vetro non e' 100 x 240")


def main() -> None:
    controlla()
    print("fotogrammi:")
    # Funzionamento, 9:16. Il vetro sta a 4,5 px/mm: la fessura di 3 mm sono
    # 13 pixel, la striscia da 1,5 mm ne fa 7.
    s = 4.5
    salva(scena_parete(1080, 1920, s, "riposo", 1, False, None, 900, False, 3),
          "func-1-giorno-riposo.jpg")
    salva(scena_parete(1080, 1920, s, "chiamata", 1, False, None, 900, False, 5),
          "func-2-giorno-chiamata.jpg")
    salva(scena_parete(1080, 1920, s, "riposo", 1, True, "tutto", 900, False, 7),
          "func-3-notte-piena.jpg")
    salva(scena_parete(1080, 1920, s, "riposo", 0.20, True, None, 900, False, 9),
          "func-4-notte-attenuata.jpg")
    salva(scena_parete(1080, 1920, s, "riposo", 0.45, True, "volto", 900, True, 13),
          "func-5-notte-volto.jpg")

    salva(scena_parete(1080, 1440, 4.2, "riposo", 1, False, None, 860, False, 2),
          "fronte-a-muro.jpg")
    salva(scena_parete(900, 1680, 5.8, "riposo", 1, False, None, None, False, 1),
          "riposo-frontale.jpg")
    tre = scena_parete(1280, 1500, 4.6, "riposo", 1, False, None, None, False, 6)
    scorcio(tre, 980)
    salva(tre, "riposo-tre-quarti.jpg")

    s_i = 3.15
    for fase, nome in (("nicchia", "inst-1-nicchia.jpg"),
                       ("cassa", "inst-2-cassa.jpg"),
                       ("telaio", "inst-3-telaio.jpg"),
                       ("vetro", "inst-4-vetro.jpg"),
                       ("finito", "inst-5-finito.jpg")):
        salva(scena_instal(1440, 1080, s_i, fase), nome)
    verifica_pixel()


def verifica_pixel() -> None:
    """Riapre il fronte e controlla che i pixel cadano sulle quote.

    In colonna, al centro, il tratto scuro e' la luce dell'intonaco: il vetro
    piu' la fessura da 3 mm per lato. La larghezza si misura piu' in dentro,
    dove c'e' solo il vetro.
    """
    im = np.asarray(Image.open(QUI / "riposo-frontale.jpg")).astype(int)
    w = im.shape[1]
    scuro = im[:, :, 0] < 100
    col = np.where(scuro[:, w // 2])[0]
    top, bot = int(col.min()), int(col.max())
    s = (bot - top + 1) / p.LUCE_INTONACO_H
    # A meta' vetro la serigrafia laterale e' piu' scura della fessura, e il
    # display in mezzo non entra nella misura: da bordo a bordo e' il vetro.
    riga = top + int((p.OMBRA_PERIMETRALE + p.VETRO_H / 2) * s)
    xs = np.where(im[riga, :, 0] < 30)[0]
    left, right = int(xs.min()), int(xs.max())
    larg = (right - left + 1) / s
    luce_h = (bot - top + 1) / s
    problemi = []
    if abs(luce_h - p.LUCE_INTONACO_H) > 0.8:
        problemi.append(f"luce alta {luce_h:.1f} mm")
    if abs(larg - p.VETRO_L) > 0.8:
        problemi.append(f"vetro largo {larg:.1f} mm")
    i = 1
    while left - i >= 0 and im[riga, left - i, 0] < 100:
        i += 1
    fessura = (i - 1) / s
    if abs(fessura - p.OMBRA_PERIMETRALE) > 0.5:
        problemi.append(f"fessura {fessura:.2f} mm")
    y0 = bot - int((p.OMBRA_PERIMETRALE + 45) * s)
    y1 = bot - int((p.OMBRA_PERIMETRALE + 8) * s)
    basso = im[y0:y1, left:right]
    chiaro = basso.sum(2) > 320
    ys, xs2 = np.where(chiaro)
    nfc_x = nfc_y = float("nan")
    if len(xs2) == 0:
        problemi.append("icona NFC assente")
    else:
        nfc_x = (xs2.mean() + left - (left + right) / 2) / s
        nfc_y = (bot - p.OMBRA_PERIMETRALE * s - (ys.mean() + y0)) / s
        if abs(nfc_y - p.NFC_Y) > 3.0:
            problemi.append(f"NFC y {nfc_y:.1f} invece di {p.NFC_Y:.0f}")
        if abs(nfc_x) > 4:
            problemi.append(f"NFC x {nfc_x:.1f}, deve stare al centro")

    def y_di(mm: float) -> int:
        return int(round(bot - (p.OMBRA_PERIMETRALE + mm) * s))

    def x_di(mm: float) -> int:
        return int(round((left + right) / 2 + mm * s))

    # La finestra dell'ottica e' il disco piu' scuro intorno a (0, 202).
    # Il microfono e' l'altro disco, 32 mm a sinistra, sulla stessa quota.
    def centro_scuro(x_mm: float, y_mm: float, meta: float) -> tuple[float, float, float]:
        """Centro e diametro del foro: i pixel che si staccano dalla serigrafia.

        La lente ha un riflesso chiaro in mezzo, quindi non basta cercare il
        pixel piu' scuro: il foro e' tutto cio' che non e' il nero del vetro.
        """
        x0, x1 = x_di(x_mm - meta), x_di(x_mm + meta)
        y_a, y_b = y_di(y_mm + meta), y_di(y_mm - meta)
        crop = im[y_a:y_b, x0:x1, 0].astype(int)
        seta = float(np.median(crop))
        ys, xs = np.where(np.abs(crop - seta) > 5)
        if len(xs) < 4:
            return float("nan"), float("nan"), 0.0
        cx = (xs.mean() + x0 - (left + right) / 2) / s
        cy = (bot - p.OMBRA_PERIMETRALE * s - (ys.mean() + y_a)) / s
        riga_f = int(round(ys.mean() + y_a))
        tratto = np.where(np.abs(im[riga_f, x0:x1, 0].astype(int) - seta) > 5)[0]
        if len(tratto) == 0:
            return cx, cy, 0.0
        # Solo il tratto che contiene il centro, non un secondo foro vicino.
        meta_px = int(round(xs.mean()))
        gruppi = np.split(tratto, np.where(np.diff(tratto) > 1)[0] + 1)
        gruppo = next(g for g in gruppi if g.min() <= meta_px <= g.max())
        return cx, cy, (gruppo.max() - gruppo.min() + 1) / s

    ox, oy, od = centro_scuro(p.CAMERA_X, p.OTTICA_Y, 8)
    if abs(ox - p.CAMERA_X) > 1.2 or abs(oy - p.OTTICA_Y) > 1.2 or abs(od - p.OTTICA_D) > 1.5:
        problemi.append(f"ottica in ({ox:.1f}, {oy:.1f}) Ø{od:.1f}")
    mx, my, md = centro_scuro(p.MICROFONO_X, p.MICROFONO_Y, 6)
    if abs(mx - p.MICROFONO_X) > 1.2 or abs(my - p.MICROFONO_Y) > 1.2 or abs(md - p.MICROFONO_D) > 1.2:
        problemi.append(f"microfono in ({mx:.1f}, {my:.1f}) Ø{md:.1f}")
    if mx > -20:
        problemi.append("il microfono non sta a sinistra della lente")

    # Tre strisce piu' chiare della serigrafia, non un campo di fori.
    centri = []
    xg0, xg1 = x_di(-20), x_di(20)
    precedente = 255.0
    for mm in np.arange(p.GRIGLIA_Y - 2, p.GRIGLIA_Y + p.GRIGLIA_N * p.GRIGLIA_PASSO + 2, 0.25):
        media = float(im[y_di(mm), xg0:xg1, 0].mean())
        if media > precedente + 6 and (not centri or mm - centri[-1] > 2):
            centri.append(mm)
        precedente = media
    if len(centri) != p.GRIGLIA_N:
        problemi.append(f"griglia con {len(centri)} strisce invece di {p.GRIGLIA_N}")
    else:
        attesi = [p.GRIGLIA_Y + i * p.GRIGLIA_PASSO + p.GRIGLIA_SPESSORE / 2
                  for i in range(p.GRIGLIA_N)]
        for trovato, atteso in zip(centri, attesi):
            if abs(trovato - atteso) > 1.2:
                problemi.append(f"striscia a y {trovato:.1f} invece di {atteso:.1f}")
                break

    if problemi:
        raise SystemExit("fotogramma fuori quota: " + "; ".join(problemi))
    print(f"controllo sul file: vetro {larg:.1f} mm, luce alta {luce_h:.1f} mm,"
          f" fessura {fessura:.2f} mm, NFC x {nfc_x:.1f} y {nfc_y:.1f},"
          f" ottica ({ox:.1f}, {oy:.1f}) Ø{od:.1f},"
          f" mic ({mx:.1f}, {my:.1f}) Ø{md:.1f}, griglia {len(centri)} strisce")


if __name__ == "__main__":
    main()
