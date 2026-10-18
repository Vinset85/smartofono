"""Icone vettoriali line-art disegnate direttamente via canvas Kivy.

Usato per pulsanti e schermate dove serve un'icona scalabile e nitida senza
ricorrere a file PNG. Tipi supportati:
    - "dialpad"     : tastierino numerico 3x3 + 1 dot centrale in basso
    - "face"        : silhouette volto/spalle (testa + busto)
    - "nfc"         : onde wireless / NFC
"""
from __future__ import annotations

from kivy.graphics import Color, Ellipse, Line
from kivy.properties import ColorProperty, NumericProperty, StringProperty
from kivy.uix.widget import Widget


class VectorIcon(Widget):
    """Disegna un'icona line-art nel proprio canvas, scalata al box."""

    icon_type = StringProperty("")
    icon_color = ColorProperty([0.95, 0.95, 0.97, 1])
    # Spessore tratto come frazione del lato (0..1). Se 0 -> auto.
    stroke = NumericProperty(0.0)
    # Padding interno come frazione (0..0.4) del lato.
    padding_factor = NumericProperty(0.08)

    def __init__(self, **kw):
        super().__init__(**kw)
        self.bind(
            pos=self._redraw, size=self._redraw,
            icon_type=self._redraw, icon_color=self._redraw,
            stroke=self._redraw, padding_factor=self._redraw,
        )

    def _redraw(self, *_):
        self.canvas.clear()
        if not self.icon_type or self.width <= 0 or self.height <= 0:
            return
        method = getattr(self, f"_draw_{self.icon_type}", None)
        if not method:
            return
        with self.canvas:
            Color(*self.icon_color)
            method()

    def _box(self):
        """Restituisce (cx, cy, side, lw) del box quadrato centrato."""
        pad = max(0.0, min(0.4, float(self.padding_factor)))
        side = min(self.width, self.height) * (1.0 - 2 * pad)
        cx = self.x + self.width / 2.0
        cy = self.y + self.height / 2.0
        lw = float(self.stroke) if self.stroke > 0 else max(1.6, side * 0.055)
        return cx, cy, side, lw

    def _draw_dialpad(self):
        cx, cy, side, _lw = self._box()
        # 4 righe (3-3-3-1) x 3 colonne. Spaziatura uniforme.
        cell = min(side / 3.4, side / 2.4)
        dot_r = cell * 0.27
        rows_y = [
            cy + 1.5 * cell,
            cy + 0.5 * cell,
            cy - 0.5 * cell,
            cy - 1.5 * cell,
        ]
        cols_x = [cx - cell, cx, cx + cell]
        positions = [(x, rows_y[r]) for r in range(3) for x in cols_x]
        positions.append((cx, rows_y[3]))
        for px, py in positions:
            Ellipse(pos=(px - dot_r, py - dot_r), size=(dot_r * 2, dot_r * 2))

    def _draw_face(self):
        cx, cy, side, lw = self._box()
        head_r = side * 0.18
        head_cy = cy + side * 0.20
        body_r = side * 0.40
        body_cy = cy - side * 0.06
        Line(circle=(cx, head_cy, head_r), width=lw, cap="round")
        # Spalle/busto: arco superiore (semicerchio aperto in basso)
        Line(circle=(cx, body_cy, body_r, 270, 90), width=lw, cap="round")

    def _draw_nfc(self):
        # Tre archi concentrici aperti verso destra (tipico simbolo onde
        # wireless / NFC) + piccolo dot centrale.
        cx, cy, side, lw = self._box()
        ccx = cx - side * 0.10
        for r_factor, sweep in ((0.42, 110), (0.30, 100), (0.18, 90)):
            r = side * r_factor
            Line(circle=(ccx, cy, r, 35, 35 + sweep), width=lw, cap="round")
            Line(circle=(ccx, cy, r, -35 - sweep, -35), width=lw, cap="round")
        dot_r = side * 0.05
        Ellipse(pos=(ccx - dot_r, cy - dot_r), size=(dot_r * 2, dot_r * 2))
