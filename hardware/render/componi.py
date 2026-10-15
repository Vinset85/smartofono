#!/usr/bin/env python3
"""Fotogrammi del videocitofono, in scala con parametri.py.

Le texture sono fotografiche, lo schermo e' l'OLED vero, il vetro ha un
riflesso. Ogni foro, striscia e fessura nasce comunque da una quota: una
foto intera sposta la lente.

Le due foto schermata-*.jpg non si toccano: sono il display vero.

Uso, dalla cartella hardware:
    ../.venv-cad/bin/python render/componi.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import parametri as p  # noqa: E402

QUI = Path(__file__).resolve().parent
MAT = QUI / "materiali"

VETRO = (12, 12, 14)
FESSURA = (42, 36, 30)


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


def _foto(nome: str) -> Image.Image:
    return Image.open(MAT / nome).convert("RGB")


def cover(im: Image.Image, w: int, h: int) -> Image.Image:
    src_w, src_h = im.size
    scala = max(w / src_w, h / src_h)
    nw, nh = max(w, round(src_w * scala)), max(h, round(src_h * scala))
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    x = (nw - w) // 2
    y = (nh - h) // 2
    return im.crop((x, y, x + w, y + h))


def grano(im: Image.Image, seme: int, sigma: float = 3.2) -> Image.Image:
    rng = np.random.default_rng(seme)
    a = np.asarray(im).astype(np.float32)
    n = rng.normal(0, sigma, a.shape[:2])
    a += n[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")


def alza_intonaco(im: Image.Image) -> Image.Image:
    """L'intonaco non deve scendere sotto R 140, sennò la misura del vetro
    prende le crepe della parete per la fessura."""
    a = np.asarray(im).astype(np.float32)
    a = 145 + a * 0.42
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")


def muro(w: int, h: int, notte: bool = False, malta: bool = False,
         seme: int = 1) -> Image.Image:
    nome = "malta-fresca.jpg" if malta else "intonaco-portico.jpg"
    im = alza_intonaco(cover(_foto(nome), w, h))
    if notte:
        a = np.asarray(im).astype(np.float32)
        a *= 0.11
        a[:, :, 0] *= 0.85
        a[:, :, 2] = np.clip(a[:, :, 2] * 1.15, 0, 255)
        im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")
    return grano(im, seme, 2.4 if not notte else 1.6)


def bagliore(im: Image.Image, cx: float, cy: float, raggio: float,
             forza: float, colore=(255, 214, 160),
             solo_sopra: float | None = None) -> Image.Image:
    h, w = im.size[1], im.size[0]
    yy, xx = np.mgrid[0:h, 0:w]
    dist = np.hypot(xx - cx, yy - cy)
    k = np.clip(1 - dist / raggio, 0, 1) ** 1.45 * forza
    if solo_sopra is not None:
        k *= np.clip((solo_sopra - yy) / 90, 0, 1)
    a = np.asarray(im).astype(np.float32)
    luce = np.array(colore, np.float32)
    a += (luce - a) * k[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")


class Piano:
    """x in mm dal centro del vetro, y in mm dal bordo inferiore."""

    def __init__(self, base: Image.Image, ox: float, oy: float, s: float):
        self.base = base
        self.draw = ImageDraw.Draw(base)
        self.ox = ox
        self.oy = oy
        self.s = s

    def box(self, x: float, y: float, w: float, h: float) -> list[int]:
        x0 = self.ox + (x - w / 2) * self.s
        x1 = self.ox + (x + w / 2) * self.s
        y1 = self.oy - y * self.s
        y0 = self.oy - (y + h) * self.s
        return [int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))]

    def rett(self, x, y, w, h, **kw):
        self.draw.rectangle(self.box(x, y, w, h), **kw)

    def tondo(self, x, y, w, h, r, **kw):
        self.draw.rounded_rectangle(self.box(x, y, w, h),
                                    radius=max(1, int(r * self.s)), **kw)

    def cerchio(self, x, y, d, **kw):
        self.draw.ellipse(self.box(x, y - d / 2, d, d), **kw)

    def texture(self, x, y, w, h, tex: Image.Image, r: float = 0) -> None:
        box = self.box(x, y, w, h)
        bw, bh = box[2] - box[0], box[3] - box[1]
        if bw < 2 or bh < 2:
            return
        pezzo = cover(tex, bw, bh)
        if r <= 0:
            self.base.paste(pezzo, (box[0], box[1]))
        else:
            maschera = Image.new("L", (bw, bh), 0)
            ImageDraw.Draw(maschera).rounded_rectangle(
                [0, 0, bw - 1, bh - 1], radius=max(1, int(r * self.s)), fill=255)
            self.base.paste(pezzo, (box[0], box[1]), maschera)
        self.draw = ImageDraw.Draw(self.base)


def _tratto(w: int) -> int:
    return max(2, w // 18)


def icona(d: ImageDraw.ImageDraw, tipo: str, x: int, y: int, lato: int) -> None:
    c = (220, 220, 224)
    t = _tratto(lato)
    cx, cy = x + lato / 2, y + lato / 2
    r = lato * 0.38
    if tipo == "nfc":
        for k, f in enumerate((0.35, 0.65, 0.95)):
            rr = r * f
            d.arc([int(cx - rr), int(cy - rr), int(cx + rr), int(cy + rr)],
                  -55, 55, fill=c, width=t)


def schermo(modo: str, w: int, h: int, luce: float) -> Image.Image:
    if modo == "spento":
        im = Image.new("RGB", (w, h), (6, 6, 8))
    else:
        nome = "oled-chiamata.jpg" if modo == "chiamata" else "oled-riposo.jpg"
        im = cover(_foto(nome), w, h)
        im = ImageEnhance.Contrast(im).enhance(1.06)
        im = ImageEnhance.Color(im).enhance(1.08)
    if luce < 0.999:
        a = np.asarray(im).astype(np.float32) * luce
        im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")
    return im


def ombra_contatto(im: Image.Image, box, raggio: int, forza: float = 0.45) -> None:
    """Occlusione intorno alla luce dell'intonaco: il vetro e' a filo, ma
    la fessura mangia un po' di luce."""
    w, h = im.size
    maschera = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(maschera)
    d.rectangle(box, fill=255)
    maschera = maschera.filter(ImageFilter.GaussianBlur(raggio))
    a = np.asarray(im).astype(np.float32)
    m = np.asarray(maschera).astype(np.float32) / 255.0
    # Solo l'anello, non il pieno.
    pieno = np.zeros((h, w), np.float32)
    x0, y0, x1, y1 = box
    pieno[max(0, y0):min(h, y1), max(0, x0):min(w, x1)] = 1
    anello = np.clip(m - pieno, 0, 1)
    a *= (1 - forza * anello)[..., None]
    im.paste(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB"))


def disegna_vetro(piano: Piano, modo: str, luce: float,
                  a_muro: bool = True) -> tuple[float, float]:
    s = piano.s
    if a_muro:
        luce_box = piano.box(0, -p.OMBRA_PERIMETRALE, p.LUCE_INTONACO_L,
                             p.LUCE_INTONACO_H)
        piano.rett(0, -p.OMBRA_PERIMETRALE, p.LUCE_INTONACO_L, p.LUCE_INTONACO_H,
                   fill=FESSURA)
        ombra_contatto(piano.base, luce_box, max(2, int(1.8 * s)), 0.38)
        piano.draw = ImageDraw.Draw(piano.base)
        # La fessura ha un filo di fondo piu' scuro, come il vano 5 mm dietro.
        piano.rett(0, -p.OMBRA_PERIMETRALE, p.LUCE_INTONACO_L, p.LUCE_INTONACO_H,
                   fill=FESSURA)

    piano.tondo(0, 0, p.VETRO_L, p.VETRO_H, p.VETRO_RAGGIO, fill=VETRO)

    y_att = p.FINESTRA_DISPLAY_Y + (p.FINESTRA_DISPLAY_H - p.DISPLAY_ATTIVO_H) / 2
    box = piano.box(0, y_att, p.DISPLAY_ATTIVO_L, p.DISPLAY_ATTIVO_H)
    pw, ph = box[2] - box[0], box[3] - box[1]
    sch = schermo(modo, pw, ph, luce)
    piano.base.paste(sch, (box[0], box[1]))
    if luce > 0.15 and modo != "spento":
        # Fioco dell'OLED sull'orlo della finestra, senza uscire dal vetro.
        bagliore_oled(piano.base, box, min(8, s * 1.4), 0.22 if luce > 0.8 else 0.12)

    lucida_serigrafia(piano)

    for i in range(p.GRIGLIA_N):
        piano.tondo(0, p.GRIGLIA_Y + i * p.GRIGLIA_PASSO,
                    p.GRIGLIA_L, p.GRIGLIA_SPESSORE, p.GRIGLIA_SPESSORE / 2,
                    fill=(52, 52, 56))

    piano.cerchio(p.CAMERA_X, p.OTTICA_Y, p.OTTICA_D, fill=(5, 5, 7))
    piano.cerchio(p.CAMERA_X, p.OTTICA_Y, p.CAMERA_LENTE_FRONTALE_D, fill=(16, 18, 24))
    piano.cerchio(p.CAMERA_X - 0.55, p.OTTICA_Y + 0.65, 1.15, fill=(90, 96, 108))

    piano.cerchio(p.MICROFONO_X, p.MICROFONO_Y, p.MICROFONO_D, fill=(3, 3, 5))
    piano.cerchio(p.MICROFONO_X, p.MICROFONO_Y, p.MICROFONO_D * 0.45, fill=(8, 8, 10))

    piano.cerchio(p.NFC_X, p.NFC_Y, p.NFC_D, outline=(168, 168, 172),
                  width=max(1, round(0.35 * s)))
    box_n = piano.box(p.NFC_X, p.NFC_Y - p.NFC_D / 2, p.NFC_D, p.NFC_D)
    icona(piano.draw, "nfc", box_n[0], box_n[1], box_n[2] - box_n[0])

    if modo == "chiamata":
        dito_sulla_card(piano, box)
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def bagliore_oled(im: Image.Image, box, raggio: float, forza: float) -> None:
    x0, y0, x1, y1 = box
    pezzo = im.crop((x0, y0, x1, y1)).filter(
        ImageFilter.GaussianBlur(radius=raggio))
    a = np.asarray(im).astype(np.float32)
    b = np.asarray(pezzo).astype(np.float32)
    a[y0:y1, x0:x1] += (b - a[y0:y1, x0:x1]) * forza
    im.paste(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB"))


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
    for x_mm, y_mm, diam in (
            (p.CAMERA_X, p.OTTICA_Y, p.OTTICA_D),
            (p.MICROFONO_X, p.MICROFONO_Y, p.MICROFONO_D)):
        cx = piano.ox + x_mm * s
        cy = piano.oy - y_mm * s
        nera &= (xx - cx) ** 2 + (yy - cy) ** 2 > (diam / 2 * s) ** 2
    t = np.clip((yy - y_top) / max(p.VETRO_H * s, 1), 0, 1)
    sheen = (1 - t) * 18
    rif = cover(_foto("riflesso-portico.jpg"), w, h).filter(
        ImageFilter.GaussianBlur(48))
    rif_a = np.asarray(rif).astype(np.float32)
    k_rif = 0.055 * (1 - t) ** 1.4
    for c in range(3):
        v = im[:, :, c] + sheen
        v = v * (1 - k_rif) + rif_a[:, :, c] * k_rif
        im[:, :, c] = np.where(nera, v, im[:, :, c])
    piano.base.paste(Image.fromarray(np.clip(im, 0, 255).astype(np.uint8), "RGB"))
    piano.draw = ImageDraw.Draw(piano.base)


def _ritaglio_su_nero(nome: str, soglia: int = 22, riempi: bool = False
                      ) -> tuple[Image.Image, Image.Image]:
    src = _foto(nome)
    lum = np.asarray(src).mean(2)
    vis = lum > soglia
    if vis.mean() < 0.005:
        return src, Image.new("L", src.size, 0)
    if riempi:
        # Le orbite nere stanno dentro la faccia: senza riempirle il key
        # le mangia e resta un buco.
        pieno = vis.copy()
        for y in range(pieno.shape[0]):
            xs = np.where(vis[y])[0]
            if len(xs) > 4:
                pieno[y, xs[0]:xs[-1] + 1] = True
        vis = pieno
    ys, xs = np.where(vis)
    pad = 2
    x0, x1 = max(0, xs.min() - pad), min(src.size[0], xs.max() + pad + 1)
    y0, y1 = max(0, ys.min() - pad), min(src.size[1], ys.max() + pad + 1)
    crop = src.crop((x0, y0, x1, y1))
    alpha = vis[y0:y1, x0:x1].astype(np.uint8) * 255
    mask = Image.fromarray(alpha, "L").filter(ImageFilter.GaussianBlur(1.1))
    return crop, mask


def dito_sulla_card(piano: Piano, box_display) -> None:
    """Mano vera: la punta tocca la prima card, il polso esce a destra."""
    crop, mask = _ritaglio_su_nero("dito-nero.jpg", 28)
    dh = box_display[3] - box_display[1]
    altezza = int(dh * 0.20)
    scala = altezza / crop.size[1]
    nw, nh = max(8, int(crop.size[0] * scala)), max(8, altezza)
    crop = crop.resize((nw, nh), Image.Resampling.LANCZOS)
    mask = mask.resize((nw, nh), Image.Resampling.LANCZOS)
    # Solo la punta sul bordo destro della prima card, il resto esce dal vetro.
    x = box_display[2] - int(nw * 0.28)
    y = box_display[1] + int(dh * 0.14)
    piano.base.paste(crop, (x, y), mask)
    piano.draw = ImageDraw.Draw(piano.base)


def porta(im: Image.Image, x0: int) -> None:
    w, h = im.size
    legno = cover(_foto("porta-legno.jpg"), w - x0, h)
    legno = ImageEnhance.Color(legno).enhance(0.9)
    im.paste(legno, (x0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([x0, 0, x0 + 6, h], fill=(28, 18, 12))
    # Ombra della porta sull'intonaco.
    ombra = Image.new("L", (w, h), 0)
    ImageDraw.Draw(ombra).rectangle([x0 - 18, 0, x0, h], fill=180)
    ombra = ombra.filter(ImageFilter.GaussianBlur(10))
    a = np.asarray(im).astype(np.float32)
    k = np.asarray(ombra).astype(np.float32) / 255.0
    a *= (1 - 0.28 * k)[..., None]
    im.paste(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB"))


def volto(im: Image.Image, cx: int, cy: int, raggio: int) -> None:
    crop, mask = _ritaglio_su_nero("volto-nero.jpg", 16, riempi=True)
    altezza = int(raggio * 3.6)
    scala = altezza / crop.size[1]
    nw, nh = max(8, int(crop.size[0] * scala)), max(8, altezza)
    crop = crop.resize((nw, nh), Image.Resampling.LANCZOS)
    mask = mask.resize((nw, nh), Image.Resampling.LANCZOS)
    im.paste(crop, (cx - nw // 2, cy - int(nh * 0.46)), mask)


def scena_parete(w, h, s, modo, luce, notte, glow, porta_x, volto_sotto,
                 seme) -> Image.Image:
    im = muro(w, h, notte=notte, seme=seme)
    ox = w / 2 if porta_x is None else min(w / 2, porta_x - (p.VETRO_L / 2 + 28) * s)
    vetro_h = p.VETRO_H * s
    if volto_sotto:
        oy = h - 36
    else:
        oy = (h + vetro_h) / 2
    if glow:
        cx = ox
        cy = oy - (p.FINESTRA_DISPLAY_Y + p.FINESTRA_DISPLAY_H / 2) * s
        raggio = (400 if glow == "tutto" else 180) * s
        im = bagliore(im, cx, cy, raggio, 0.78 if glow == "tutto" else 0.50,
                      solo_sopra=(cy if glow == "volto" else None))
    if porta_x:
        porta(im, porta_x)
    if volto_sotto:
        r = int(62 * s)
        testa = int(oy - vetro_h - 18 * s - 0.55 * r)
        volto(im, int(ox), testa, r)
    piano = Piano(im, ox, oy, s)
    disegna_vetro(piano, modo, luce)
    return im


def corrugato(piano: Piano, x: float, y0: float, h: float) -> None:
    """Due tubi Ø25: cilindro scuro con coste, dal fondo della nicchia."""
    s = piano.s
    box = piano.box(x, y0, p.CORRUGATO_D, h)
    bw, bh = max(2, box[2] - box[0]), max(2, box[3] - box[1])
    yy, xx = np.mgrid[0:bh, 0:bw]
    t = (xx / max(bw - 1, 1)) * 2 - 1
    luce = 22 + 55 * np.exp(-((t - 0.15) ** 2) / 0.18)
    coste = 8 * np.sin(yy / max(s * 3.2, 2) * np.pi) ** 8
    rgb = np.clip(luce - coste, 6, 70)
    tubo = np.stack([rgb, rgb, rgb * 0.95], 2).astype(np.uint8)
    maschera = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(maschera).rounded_rectangle(
        [0, 0, bw - 1, bh - 1], radius=bw // 2, fill=255)
    piano.base.paste(Image.fromarray(tubo, "RGB"), (box[0], box[1]), maschera)
    piano.draw = ImageDraw.Draw(piano.base)


def cassa_nel_muro(piano: Piano) -> None:
    asa = _foto("asa-stampato.jpg")
    piano.texture(0, (p.VETRO_H - p.CORNICE_H) / 2, p.CORNICE_L, p.CORNICE_H, asa)
    piano.rett(0, (p.VETRO_H - p.LUCE_INTONACO_H) / 2,
               p.LUCE_INTONACO_L, p.LUCE_INTONACO_H, fill=(22, 22, 24))
    scuro = ImageEnhance.Brightness(asa).enhance(0.42)
    piano.texture(0, (p.VETRO_H - p.CASSA_H) / 2, p.CASSA_L, p.CASSA_H, scuro)
    piano.rett(0, (p.VETRO_H - p.CASSA_INT_H) / 2,
               p.CASSA_INT_L, p.CASSA_INT_H, fill=(10, 10, 12))
    for sx in (-1, 1):
        piano.cerchio(sx * p.CORRUGATO_PASSO / 2, 26, p.CORRUGATO_D, fill=(8, 8, 10))
        piano.cerchio(sx * p.CORRUGATO_PASSO / 2, 26, p.CORRUGATO_D * 0.55,
                      fill=(18, 18, 20))


def telaio(piano: Piano, dy: float) -> None:
    alu = ImageEnhance.Brightness(_foto("alluminio-anodizzato.jpg")).enhance(0.55)
    y0 = p.TELAIO_Y0 + dy
    piano.texture(0, y0, p.TELAIO_L, p.TELAIO_H, alu, r=2)
    piano.rett(p.FLAT_ASOLA_X, p.FLAT_ASOLA_Y - p.FLAT_ASOLA_H / 2 + dy,
               p.FLAT_ASOLA_L, p.FLAT_ASOLA_H, fill=(12, 12, 14))
    piano.cerchio(p.CAMERA_X, p.OTTICA_Y + dy,
                  p.CAMERA_LENTE_D + p.GIOCO_LENTE_TELAIO, fill=(12, 12, 14))
    for x, y in p.posizioni_fori_camera():
        piano.cerchio(x, y + dy, p.CAMERA_FORO_D, fill=(12, 12, 14))
    piano.rett(p.SPEAKER_X, p.SPEAKER_LUCE_Y - p.SPEAKER_LUCE_H / 2 + dy,
               p.SPEAKER_LUCE_L, p.SPEAKER_LUCE_H, fill=(12, 12, 14))
    for x, y in p.posizioni_fori_speaker():
        piano.cerchio(x, y + dy, p.SPEAKER_FORO_D, fill=(12, 12, 14))
    piano.rett(p.NFC_APERTURA_X, p.NFC_Y - p.NFC_APERTURA_H / 2 + dy,
               p.NFC_APERTURA_L, p.NFC_APERTURA_H, fill=(12, 12, 14))
    piano.rett(p.MICROFONO_X, p.MIC_ASOLA_Y - p.MIC_ASOLA_H / 2 + dy,
               p.MIC_ASOLA_L, p.MIC_ASOLA_H, fill=(12, 12, 14))
    for x, y in p.posizioni_magneti():
        piano.cerchio(x, y + dy, p.MAGNETE_SEDE_D, fill=(18, 18, 20))
    y_perno = (p.VETRO_H + p.TELAIO_H) / 2 - p.PERNO_MARGINE / 2
    for sx in (-1, 1):
        piano.cerchio(sx * p.PERNO_PASSO / 2, y_perno + dy, p.PERNO_FORO_D,
                      fill=(12, 12, 14))


def scena_instal(w, h, s, fase: str) -> Image.Image:
    im = muro(w, h, malta=(fase not in ("nicchia", "finito")), seme=11)
    ox, oy = w / 2, h / 2 + (p.VETRO_H / 2) * s * 0.92
    meta = (p.FORO_MURO_H if fase == "nicchia" else p.CORNICE_H) / 2 * s
    oy = min(oy, h - 40 - (meta - p.VETRO_H / 2 * s))
    oy = max(oy, 40 + p.VETRO_H * s)
    piano = Piano(im, ox, oy, s)
    if fase == "nicchia":
        yb = p.VETRO_H / 2 - p.FORO_MURO_H / 2
        tufo_src = _foto("tufo-taglio.jpg")
        # Solo la faccia porosa, non la foto della cavita' gia' scavata.
        tufo = tufo_src.crop((0, 0, tufo_src.size[0], max(40, tufo_src.size[1] // 4)))
        piano.texture(0, yb, p.FORO_MURO_L, p.FORO_MURO_H, tufo)
        fondo = ImageEnhance.Brightness(tufo).enhance(0.48)
        piano.texture(0, yb + 8, p.FORO_MURO_L - 10, p.FORO_MURO_H - 16, fondo)
        for sx in (-1, 1):
            corrugato(piano, sx * p.CORRUGATO_PASSO / 2, yb - 10, 78)
        return im
    cassa_nel_muro(piano)
    if fase == "cassa":
        return im
    if fase == "telaio":
        telaio(piano, dy=36)
        y = p.TELAIO_Y0 + 36
        box = piano.box(0, y - 28, 6, 36)
        piano.draw.rounded_rectangle(box, radius=3, fill=(14, 14, 16))
        return im
    if fase == "vetro":
        telaio(piano, dy=0)
        # Ombra del vetro ancora in aria, sulla sede.
        ombra = piano.box(0, p.TELAIO_Y0, p.VETRO_L, p.VETRO_H)
        d = ImageDraw.Draw(piano.base, "RGBA")
        d.rounded_rectangle(ombra, radius=int(p.VETRO_RAGGIO * s),
                            fill=(0, 0, 0, 60))
        piano.oy = piano.oy - 28 * piano.s
        piano.draw = ImageDraw.Draw(piano.base)
        disegna_vetro(piano, "spento", 1, a_muro=False)
        return im
    im = muro(w, h, seme=4)
    piano = Piano(im, ox, oy, s)
    disegna_vetro(piano, "riposo", 1)
    return im


def scorcio(im: Image.Image, x_spigolo: int) -> None:
    w, h = im.size
    angolo = cover(_foto("angolo-muro.jpg"), w, h)
    # Prendi la faccia destra della foto d'angolo e la stendi dallo spigolo.
    pezzo = angolo.crop((int(angolo.size[0] * 0.55), 0, angolo.size[0], h))
    pezzo = pezzo.resize((w - x_spigolo, h), Image.Resampling.LANCZOS)
    pezzo = alza_intonaco(pezzo)
    im.paste(pezzo, (x_spigolo, 0))
    d = ImageDraw.Draw(im)
    d.line([(x_spigolo, 0), (x_spigolo, h)], fill=(150, 138, 122), width=2)


def salva(im: Image.Image, nome: str) -> None:
    cartella = QUI / "scala"
    cartella.mkdir(exist_ok=True)
    for percorso in (QUI / nome, cartella / nome):
        im.save(percorso, quality=93, subsampling=0, optimize=True)
    print(f"  {nome}  {im.size[0]}x{im.size[1]}")


def controlla() -> None:
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
    if abs(p.VETRO_L / p.VETRO_H - 100 / 240) > 1e-9:
        raise SystemExit("il vetro non e' 100 x 240")


def main() -> None:
    controlla()
    print("fotogrammi:")
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
    """Riapre il fronte e controlla che i pixel cadano sulle quote."""
    im = np.asarray(Image.open(QUI / "riposo-frontale.jpg")).astype(int)
    w = im.shape[1]
    scuro = im[:, :, 0] < 100
    col = np.where(scuro[:, w // 2])[0]
    top, bot = int(col.min()), int(col.max())
    s = (bot - top + 1) / p.LUCE_INTONACO_H
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

    def centro_scuro(x_mm: float, y_mm: float, meta: float) -> tuple[float, float, float]:
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
        meta_px = int(round(xs.mean()))
        gruppi = np.split(tratto, np.where(np.diff(tratto) > 1)[0] + 1)
        gruppo = next((g for g in gruppi if g.min() <= meta_px <= g.max()), gruppi[0])
        return cx, cy, (gruppo.max() - gruppo.min() + 1) / s

    ox, oy, od = centro_scuro(p.CAMERA_X, p.OTTICA_Y, 8)
    if abs(ox - p.CAMERA_X) > 1.2 or abs(oy - p.OTTICA_Y) > 1.2 or abs(od - p.OTTICA_D) > 1.5:
        problemi.append(f"ottica in ({ox:.1f}, {oy:.1f}) Ø{od:.1f}")
    mx, my, md = centro_scuro(p.MICROFONO_X, p.MICROFONO_Y, 6)
    if abs(mx - p.MICROFONO_X) > 1.2 or abs(my - p.MICROFONO_Y) > 1.2 or abs(md - p.MICROFONO_D) > 1.2:
        problemi.append(f"microfono in ({mx:.1f}, {my:.1f}) Ø{md:.1f}")
    if mx > -20:
        problemi.append("il microfono non sta a sinistra della lente")

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
