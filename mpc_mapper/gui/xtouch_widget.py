"""Interactive drawing of the Behringer X-Touch Compact.

Same interaction as the APC drawing (drag commands onto controls, click to
edit, Shift+click / Shift+drag to simulate); the motor faders and encoder
rings show the positions the app sends to the hardware.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen

from .. import xtouch
from ..apc import LedState
from . import theme
from .apc_widget import APCWidget
from .widgets import ui_font

# logical geometry
SW, X0 = 78.0, 40.0                  # channel strip width, left margin
ENC_Y, ENC_R = 92.0, 24.0
BTN_Y, BTN_H, BTN_GAP = 146.0, 30.0, 10.0
FADER_Y, FADER_H = 276.0, 226.0
CH_Y = FADER_Y + FADER_H + 14
MAIN_X = X0 + 8 * SW + 26
RX = X0 + 9 * SW + 56                # right block
LW = RX + 290
LH = CH_Y + 30 + 40
ORANGE = QColor("#ff9a1f")
ORANGE_DIM = QColor("#4a3420")


def _cx(i: int) -> float:
    return X0 + i * SW + SW / 2


def _enc_center(i: int) -> QPointF:
    if i < 8:
        return QPointF(_cx(i), ENC_Y)
    k = i - 8
    return QPointF(RX + 40 + (k % 2) * 126, ENC_Y + (k // 2) * 86)


def control_rect(control: str) -> QRectF:
    k, i = xtouch.kind(control), xtouch.index(control)
    if k == "enc":
        c = _enc_center(i)
        return QRectF(c.x() - ENC_R - 4, c.y() - ENC_R - 4, 2 * ENC_R + 8, 2 * ENC_R + 8)
    if k == "push":
        c = _enc_center(i)
        return QRectF(c.x() - 24, c.y() + ENC_R + 10, 48, 14)
    if k == "btn":
        row, col = divmod(i, 8)
        return QRectF(_cx(col) - 28, BTN_Y + row * (BTN_H + BTN_GAP), 56, BTN_H)
    if k == "fader":
        x = MAIN_X if i == 8 else _cx(i) - 26
        return QRectF(x, FADER_Y, 52, FADER_H)
    if k == "ch":
        x = MAIN_X - 2 if i == 8 else _cx(i) - 28
        return QRectF(x, CH_Y, 56, 30)
    if k == "tr":
        row, col = divmod(i, 2)
        return QRectF(RX + 10 + col * 126, FADER_Y + 136 + row * 44, 100, 32)
    return QRectF()


class XTouchWidget(APCWidget):
    LW, LH = LW, LH

    def controls(self) -> list[str]:
        return xtouch.ALL_CONTROLS

    def ctrl_rect(self, control: str) -> QRectF:
        return control_rect(control)

    # ---------------- painting ----------------
    def paint_device(self, p: QPainter) -> None:
        body = QRectF(6, 6, LW - 12, LH - 12)
        grad = QLinearGradient(0, 0, 0, LH)
        grad.setColorAt(0, QColor("#2c2e33"))
        grad.setColorAt(1, QColor("#1f2125"))
        p.setPen(QPen(QColor("#45484f"), 2))
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(body, 16, 16)
        p.setPen(QColor("#c8c8c8"))
        p.setFont(ui_font(13, bold=True))
        p.drawText(QRectF(X0 - 10, 14, 400, 26), Qt.AlignLeft | Qt.AlignVCenter,
                   "behringer  X-TOUCH COMPACT")
        p.setPen(QColor("#8a8d94"))
        p.setFont(ui_font(9))
        p.drawText(QRectF(LW - 470, 14, 440, 26), Qt.AlignRight | Qt.AlignVCenter,
                   f"Shift+click = simulate · drag = move · {theme.MOD_KEY}+drag = copy")
        p.setFont(ui_font(8))
        p.drawText(QRectF(MAIN_X - 10, FADER_Y - 26, 72, 20), Qt.AlignCenter, "MAIN")
        p.drawText(QRectF(RX + 10, FADER_Y + 112, 226, 20), Qt.AlignCenter, "TRANSPORT")
        for c in xtouch.ALL_CONTROLS:
            k = xtouch.kind(c)
            if k == "enc":
                self._paint_encoder(p, c)
            elif k == "fader":
                self._paint_xfader(p, c)
            else:
                self._paint_xbutton(p, c)

    def _paint_encoder(self, p: QPainter, c: str) -> None:
        center = _enc_center(xtouch.index(c))
        lit = xtouch.ring_value(self.fader_values.get(c, 0))
        for n in range(13):                      # 13 LEDs, 225° .. -45°
            ang = math.radians(225 - n * 22.5)
            pt = QPointF(center.x() + math.cos(ang) * (ENC_R + 1),
                         center.y() - math.sin(ang) * (ENC_R + 1))
            p.setPen(Qt.NoPen)
            p.setBrush(ORANGE if n < lit else QColor("#3a2c22"))
            p.drawEllipse(pt, 2.6, 2.6)
        p.setPen(QPen(QColor("#111"), 1.5))
        g = QLinearGradient(center.x(), center.y() - ENC_R, center.x(), center.y() + ENC_R)
        g.setColorAt(0, QColor("#4b4e55"))
        g.setColorAt(1, QColor("#2a2c30"))
        p.setBrush(QBrush(g))
        p.drawEllipse(center, ENC_R - 7, ENC_R - 7)
        # pointer
        v = self.fader_values.get(c, 0) / 127.0
        ang = math.radians(225 - v * 270)
        p.setPen(QPen(QColor("#e8e8e8"), 2))
        p.drawLine(center, QPointF(center.x() + math.cos(ang) * (ENC_R - 10),
                                   center.y() - math.sin(ang) * (ENC_R - 10)))
        text = self._label(c)
        if text:
            p.setPen(QColor("#d8d8d8"))
            p.setFont(ui_font(8))
            if xtouch.index(c) < 8:
                box = QRectF(center.x() - 38, center.y() - ENC_R - 22, 76, 16)
            else:                                  # right block: label beside the knob
                box = QRectF(center.x() + ENC_R + 6, center.y() - 14, 64, 28)
            p.drawText(box, Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap if xtouch.index(c) >= 8
                       else Qt.AlignCenter, text)
        self._outline(p, c, self.ctrl_rect(c), ENC_R)

    def _paint_xbutton(self, p: QPainter, c: str) -> None:
        rect = self.ctrl_rect(c)
        k = xtouch.kind(c)
        st = self.leds.get(c, LedState(0, 0))
        on = st.color == 1 or (st.color == 2 and not self._blink)
        if k == "push":
            col = QColor("#5a5d64") if c in self.hw_pressed else QColor("#34363b")
        else:
            col = ORANGE if on else ORANGE_DIM
        p.setPen(QPen(QColor("#111"), 1.5))
        p.setBrush(col)
        p.drawRoundedRect(rect, 4, 4)
        text = self._label(c)
        if not text and k == "tr":
            text = xtouch.TRANSPORT[xtouch.index(c)]
        if not text and k == "push":
            text = "push"
        if text:
            p.setPen(QColor("#1a1206") if on and k != "push" else QColor("#d8d8d8"))
            p.setFont(ui_font(8))
            p.drawText(rect.adjusted(2, 0, -2, 0), Qt.AlignCenter | Qt.TextWordWrap, text)
        self._outline(p, c, rect, 4)

    def _paint_xfader(self, p: QPainter, c: str) -> None:
        rect = self.ctrl_rect(c)
        slot = QRectF(rect.center().x() - 4, rect.top() + 10, 8, rect.height() - 20)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#0d0e10"))
        p.drawRoundedRect(slot, 4, 4)
        v = self.fader_values.get(c, 0) / 127.0
        cy = slot.bottom() - v * slot.height()
        cap = QRectF(rect.center().x() - 20, cy - 12, 40, 24)
        g = QLinearGradient(cap.topLeft(), cap.bottomLeft())
        g.setColorAt(0, QColor("#d0d2d6"))
        g.setColorAt(1, QColor("#7d8087"))
        p.setBrush(QBrush(g))
        touched = c in self.touched
        p.setPen(QPen(QColor(theme.ACCENT) if touched else QColor("#111"), 2 if touched else 1))
        p.drawRoundedRect(cap, 3, 3)
        p.setPen(QPen(QColor("#222"), 2))
        p.drawLine(QPointF(cap.left() + 4, cy), QPointF(cap.right() - 4, cy))
        text = self._label(c)
        if text:
            p.setPen(QColor("#d8d8d8"))
            p.setFont(ui_font(8))
            p.drawText(QRectF(rect.left() - 10, rect.top() - 18, rect.width() + 20, 16),
                       Qt.AlignCenter, text)
        self._outline(p, c, rect, 6)
