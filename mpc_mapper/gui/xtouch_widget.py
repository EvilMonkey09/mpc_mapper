"""Interactive drawing of the Behringer X-Touch Compact, laid out like the
real unit:

  encoders 1-8 ........ top row, LED ring around each knob
  3 button rows ....... below the encoders
  8 faders + MAIN ..... middle; MAIN sits in the centre column under the
                        status panel (behringer logo, USB/MIDI/FOOT/MODE)
  channel buttons ..... bottom row, one under each fader (+ MAIN)
  encoders 9-16 ....... right block, 2 columns x 4 rows
  transport ........... right, under the encoders: rew/fwd, loop/rec, stop/play
  layer A / B ......... bottom right (not used by the app, drawn for reference)

Encoder rotation and encoder push are separate controls: the outer knob is
the rotation, the small centre cap is the push.

Same interaction as the APC drawing (drag commands onto controls, click to
edit, Shift+click / Shift+drag to simulate); motor faders and encoder rings
show the positions the app sends to the hardware.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen, QPolygonF

from .. import xtouch
from ..apc import LedState
from . import theme
from .apc_widget import APCWidget
from .widgets import ui_font

# ---------------------------------------------------------------- geometry
LW, LH = 1000.0, 724.0
CHEEK = 22.0                        # silver side panels
STRIP_W, LEFT_X = 75.0, 46.0        # channel strips 1-8
ENC_Y, ENC_R = 74.0, 24.0
BTN_Y, BTN_W, BTN_H, BTN_PITCH = 132.0, 42.0, 30.0, 42.0
FADER_TOP, FADER_BOT = 282.0, 628.0
CH_Y, CH_H = 652.0, 32.0
CENTER_X = LEFT_X + 8 * STRIP_W + 46          # MAIN column centre
RIGHT_C = (CENTER_X + 108, CENTER_X + 206)    # right block column centres
RENC_Y0, RENC_DY = 74.0, 76.0
TR_Y0, TR_DY = 402.0, 64.0

ORANGE = QColor("#ffa21f")
ORANGE_GLOW = QColor(255, 162, 31, 90)
KEY_OFF = QColor("#d4d6da")         # unlit keys look white-ish like the real unit
KEY_TEXT = QColor("#2a2b2e")
PANEL = QColor("#141518")
STRIP = QColor("#0e0f11")


def _cx(i: int) -> float:
    return LEFT_X + STRIP_W / 2 + i * STRIP_W


def _enc_center(i: int) -> QPointF:
    if i < 8:
        return QPointF(_cx(i), ENC_Y)
    k = i - 8
    return QPointF(RIGHT_C[k % 2], RENC_Y0 + (k // 2) * RENC_DY)


def control_rect(control: str) -> QRectF:
    k, i = xtouch.kind(control), xtouch.index(control)
    if k == "enc":
        c = _enc_center(i)
        r = ENC_R + 9
        return QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
    if k == "push":
        c = _enc_center(i)
        r = ENC_R * 0.42
        return QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
    if k == "btn":
        row, col = divmod(i, 8)
        return QRectF(_cx(col) - BTN_W / 2, BTN_Y + row * BTN_PITCH, BTN_W, BTN_H)
    if k == "fader":
        x = CENTER_X if i == 8 else _cx(i)
        return QRectF(x - 30, FADER_TOP, 60, FADER_BOT - FADER_TOP)
    if k == "ch":
        x = CENTER_X if i == 8 else _cx(i)
        return QRectF(x - BTN_W / 2, CH_Y, BTN_W, CH_H)
    if k == "tr":
        row, col = divmod(i, 2)
        return QRectF(RIGHT_C[col] - 24, TR_Y0 + row * TR_DY, 48, 34)
    return QRectF()


# hit-test order: the push cap lies inside the encoder, so test it first
_HIT_ORDER = ([c for c in xtouch.ALL_CONTROLS if xtouch.kind(c) == "push"]
              + [c for c in xtouch.ALL_CONTROLS if xtouch.kind(c) != "push"])


class XTouchWidget(APCWidget):
    LW, LH = LW, LH

    def controls(self) -> list[str]:
        return _HIT_ORDER

    def ctrl_rect(self, control: str) -> QRectF:
        return control_rect(control)

    # ---------------- painting ----------------
    def paint_device(self, p: QPainter) -> None:
        self._paint_body(p)
        for c in xtouch.ALL_CONTROLS:
            k = xtouch.kind(c)
            if k == "enc":
                self._paint_encoder(p, c)
            elif k == "fader":
                self._paint_xfader(p, c)
            elif k != "push":
                self._paint_key(p, c)
        for c in xtouch.ALL_CONTROLS:          # push caps on top of the knobs
            if xtouch.kind(c) == "push":
                self._paint_push(p, c)

    def _paint_body(self, p: QPainter) -> None:
        # silver cheeks
        cheek = QLinearGradient(0, 0, CHEEK * 2, 0)
        cheek.setColorAt(0, QColor("#8d9095"))
        cheek.setColorAt(0.5, QColor("#e3e5e8"))
        cheek.setColorAt(1, QColor("#9a9da2"))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(cheek))
        p.drawRoundedRect(QRectF(0, 4, CHEEK * 2, LH - 8), 12, 12)
        cheek2 = QLinearGradient(LW - CHEEK * 2, 0, LW, 0)
        cheek2.setColorAt(0, QColor("#9a9da2"))
        cheek2.setColorAt(0.5, QColor("#e3e5e8"))
        cheek2.setColorAt(1, QColor("#8d9095"))
        p.setBrush(QBrush(cheek2))
        p.drawRoundedRect(QRectF(LW - CHEEK * 2, 4, CHEEK * 2, LH - 8), 12, 12)
        # black top panel
        g = QLinearGradient(0, 0, 0, LH)
        g.setColorAt(0, QColor("#24262a"))
        g.setColorAt(1, QColor("#17181b"))
        p.setBrush(QBrush(g))
        p.setPen(QPen(QColor("#3a3d43"), 1.5))
        p.drawRoundedRect(QRectF(CHEEK, 6, LW - 2 * CHEEK, LH - 12), 8, 8)
        # section panels
        p.setPen(Qt.NoPen)
        p.setBrush(PANEL)
        p.drawRoundedRect(QRectF(LEFT_X - 8, 34, 8 * STRIP_W + 16, 232), 6, 6)     # enc + rows
        p.drawRoundedRect(QRectF(RIGHT_C[0] - 46, 34, 190, 300), 6, 6)             # right encs
        p.drawRoundedRect(QRectF(RIGHT_C[0] - 46, TR_Y0 - 30, 190, 3 * TR_DY + 22), 6, 6)
        p.drawRoundedRect(QRectF(LEFT_X - 8, CH_Y - 8, 8 * STRIP_W + 16, CH_H + 16), 6, 6)
        p.drawRoundedRect(QRectF(CENTER_X - 32, CH_Y - 8, 64, CH_H + 16), 6, 6)
        p.drawRoundedRect(QRectF(RIGHT_C[0] - 46, CH_Y - 8, 190, CH_H + 16), 6, 6)
        # status panel with logo (centre column)
        sp = QRectF(CENTER_X - 34, 34, 68, 232)
        p.setBrush(QColor("#3c3f45"))
        p.drawRoundedRect(sp, 5, 5)
        self._logo(p, QPointF(CENTER_X, 60))
        p.setPen(QColor("#e8e8e8"))
        p.setFont(ui_font(7, bold=True))
        p.drawText(QRectF(sp.left(), 80, sp.width(), 14), Qt.AlignCenter, "behringer")
        y = 108
        for title, leds in (("INTERFACE", [("USB", "#2f80ff")]),
                            ("MIDI", [("IN", "#e53935"), ("OUT", "#43a047")]),
                            ("FOOT", [("SW", ORANGE.name()), ("EXP", ORANGE.name())]),
                            ("MODE", [("MC", "#5a5d64")])):
            p.setPen(QColor("#f0f0f0"))
            p.setFont(ui_font(6, bold=True))
            p.drawText(QRectF(sp.left() + 6, y, sp.width(), 12), Qt.AlignLeft, title)
            y += 13
            for name, col in leds:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(col).darker(170))
                p.drawRoundedRect(QRectF(sp.left() + 8, y + 2, 10, 6), 2, 2)
                p.setPen(QColor("#d0d0d0"))
                p.setFont(ui_font(6))
                p.drawText(QRectF(sp.left() + 22, y - 1, 40, 12), Qt.AlignLeft, name)
                y += 11
            y += 6
        # model name over the faders, like the print on the unit
        p.setPen(QColor("#e8e8e8"))
        p.setFont(ui_font(13, bold=True))
        p.drawText(QRectF(_cx(3) - 40, 250, 140, 24), Qt.AlignLeft | Qt.AlignVCenter, "X TOUCH")
        p.setFont(ui_font(7))
        p.drawText(QRectF(_cx(3) + 54, 254, 80, 18), Qt.AlignLeft | Qt.AlignVCenter, "COMPACT")
        p.setPen(QColor("#c8c8c8"))
        p.setFont(ui_font(7, bold=True))
        p.drawText(QRectF(RIGHT_C[0] - 46, TR_Y0 - 26, 190, 14), Qt.AlignCenter,
                   "USB • MIDI • CONTROLLER")
        # usage hint + numbers
        p.setPen(QColor("#8a8d94"))
        p.setFont(ui_font(8))
        p.drawText(QRectF(LEFT_X, 8, 8 * STRIP_W + 200, 16), Qt.AlignLeft | Qt.AlignVCenter,
                   f"Shift+click = simulate · drag = move · {theme.MOD_KEY}+drag = copy · "
                   "knob centre = push")
        p.setFont(ui_font(7, bold=True))
        for i in range(16):
            c = _enc_center(i)
            p.setPen(QColor("#d8d8d8"))
            p.drawText(QRectF(c.x() - ENC_R - 16, c.y() + ENC_R - 4, 14, 12), Qt.AlignCenter,
                       str(i + 1))
        for i in range(9):
            x = CENTER_X if i == 8 else _cx(i)
            label = "MAIN" if i == 8 else str(i + 1)
            w = 30.0 if i == 8 else 12.0
            r = QRectF(x - 28, FADER_BOT + 4, w, 11)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#d8d8d8"))
            p.drawRoundedRect(r, 2, 2)
            p.setPen(QColor("#111"))
            p.setFont(ui_font(6, bold=True))
            p.drawText(r, Qt.AlignCenter, label)
        # layer A / B (not used by the app)
        for j, txt in enumerate(("◀ A", "B ▶")):
            r = QRectF(RIGHT_C[j] - 20, CH_Y, 40, CH_H - 8)
            p.setPen(QPen(QColor("#111"), 1))
            p.setBrush(QColor("#6b6e74"))
            p.drawRoundedRect(r, 4, 4)
            p.setPen(QColor("#bfc2c7"))
            p.setFont(ui_font(6, bold=True))
            p.drawText(QRectF(r.left() - 4, r.bottom() + 1, r.width() + 8, 10), Qt.AlignCenter, txt)

    @staticmethod
    def _logo(p: QPainter, c: QPointF) -> None:
        tri = QPolygonF([QPointF(c.x(), c.y() - 14), QPointF(c.x() - 14, c.y() + 10),
                         QPointF(c.x() + 14, c.y() + 10)])
        p.setPen(QPen(QColor("#f0f0f0"), 2))
        p.setBrush(Qt.NoBrush)
        p.drawPolygon(tri)
        p.setFont(ui_font(10, bold=True))
        p.drawText(QRectF(c.x() - 10, c.y() - 8, 20, 18), Qt.AlignCenter, "b")

    def _paint_encoder(self, p: QPainter, c: str) -> None:
        center = _enc_center(xtouch.index(c))
        lit = xtouch.ring_value(self.fader_values.get(c, 0))
        for n in range(13):                      # 13 ring LEDs from 7 to 5 o'clock
            ang = math.radians(225 - n * 22.5)
            pt = QPointF(center.x() + math.cos(ang) * (ENC_R + 5),
                         center.y() - math.sin(ang) * (ENC_R + 5))
            if n < lit:
                p.setPen(Qt.NoPen)
                p.setBrush(ORANGE_GLOW)
                p.drawEllipse(pt, 4.5, 4.5)
            p.setPen(Qt.NoPen)
            p.setBrush(ORANGE if n < lit else QColor("#3d2e22"))
            p.drawRoundedRect(QRectF(pt.x() - 2.2, pt.y() - 2.2, 4.4, 4.4), 1, 1)
        # knob with ribbed edge
        p.setPen(QPen(QColor("#050505"), 1.5))
        g = QLinearGradient(center.x(), center.y() - ENC_R, center.x(), center.y() + ENC_R)
        g.setColorAt(0, QColor("#3c3f45"))
        g.setColorAt(1, QColor("#121315"))
        p.setBrush(QBrush(g))
        p.drawEllipse(center, ENC_R - 4, ENC_R - 4)
        p.setPen(QPen(QColor("#2a2c30"), 1))
        for n in range(24):
            a = math.radians(n * 15)
            r1, r2 = ENC_R - 8, ENC_R - 5
            p.drawLine(QPointF(center.x() + math.cos(a) * r1, center.y() + math.sin(a) * r1),
                       QPointF(center.x() + math.cos(a) * r2, center.y() + math.sin(a) * r2))
        # pointer
        v = self.fader_values.get(c, 0) / 127.0
        ang = math.radians(225 - v * 270)
        p.setPen(QPen(QColor("#f2f2f2"), 2.2))
        p.drawLine(QPointF(center.x() + math.cos(ang) * (ENC_R * 0.5),
                           center.y() - math.sin(ang) * (ENC_R * 0.5)),
                   QPointF(center.x() + math.cos(ang) * (ENC_R - 6),
                           center.y() - math.sin(ang) * (ENC_R - 6)))
        text = self._label(c)
        if text:
            p.setPen(QColor("#d8d8d8"))
            p.setFont(ui_font(7))
            if xtouch.index(c) < 8:
                box = QRectF(center.x() - 37, center.y() - ENC_R - 24, 74, 14)
            else:                                # right block: label under the knob
                box = QRectF(center.x() - 46, center.y() + ENC_R + 8, 92, 14)
            p.drawText(box, Qt.AlignCenter, text)
        self._outline(p, c, self.ctrl_rect(c), ENC_R + 9)

    def _paint_push(self, p: QPainter, c: str) -> None:
        rect = self.ctrl_rect(c)
        pressed = c in self.hw_pressed
        assigned = c in self.mapping.assignments
        p.setPen(QPen(QColor("#050505"), 1))
        p.setBrush(QColor("#5a5d64") if pressed else QColor("#1b1c1f"))
        p.drawEllipse(rect)
        if assigned:                            # small dot = push is assigned
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.ACCENT))
            p.drawEllipse(rect.center(), 2.5, 2.5)
        self._outline(p, c, rect, rect.width() / 2)

    def _paint_key(self, p: QPainter, c: str) -> None:
        rect = self.ctrl_rect(c)
        k = xtouch.kind(c)
        st = self.leds.get(c, LedState(0, 0))
        on = st.color == 1 or (st.color == 2 and not self._blink)
        if on:
            p.setPen(Qt.NoPen)
            p.setBrush(ORANGE_GLOW)
            p.drawRoundedRect(rect.adjusted(-4, -4, 4, 4), 7, 7)
        g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        base = ORANGE if on else KEY_OFF
        g.setColorAt(0, base.lighter(112))
        g.setColorAt(1, base.darker(108))
        p.setPen(QPen(QColor("#0a0a0a"), 1.5))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(rect, 4, 4)
        if k == "tr":
            self._transport_icon(p, xtouch.index(c), rect)
        text = self._label(c)
        if text:
            p.setPen(KEY_TEXT)
            p.setFont(ui_font(6))
            inner = rect.adjusted(2, 1, -2, -1)
            if k == "tr":
                inner = rect.adjusted(2, rect.height() / 2, -2, -1)
            p.drawText(inner, Qt.AlignCenter | Qt.TextWordWrap, text)
        self._outline(p, c, rect, 4)

    @staticmethod
    def _transport_icon(p: QPainter, i: int, rect: QRectF) -> None:
        cx, cy = rect.center().x(), rect.top() + 9
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2a2b2e"))
        if i in (0, 1):                          # rew / fwd
            d = -1 if i == 0 else 1
            for off in (-4, 4):
                x = cx + off * d
                p.drawPolygon(QPolygonF([QPointF(x - 4 * d, cy - 4), QPointF(x + 4 * d, cy),
                                         QPointF(x - 4 * d, cy + 4)]))
        elif i == 2:                              # loop
            p.setPen(QColor("#2a2b2e"))
            p.setFont(ui_font(6, bold=True))
            p.drawText(QRectF(rect.left(), cy - 6, rect.width(), 12), Qt.AlignCenter, "LOOP")
        elif i == 3:                              # rec
            p.setBrush(QColor("#c62828"))
            p.drawEllipse(QPointF(cx, cy), 4.5, 4.5)
        elif i == 4:                              # stop
            p.drawRect(QRectF(cx - 4, cy - 4, 8, 8))
        else:                                     # play
            p.drawPolygon(QPolygonF([QPointF(cx - 4, cy - 5), QPointF(cx + 5, cy),
                                     QPointF(cx - 4, cy + 5)]))

    def _paint_xfader(self, p: QPainter, c: str) -> None:
        rect = self.ctrl_rect(c)
        # strip panel
        p.setPen(Qt.NoPen)
        p.setBrush(STRIP)
        p.drawRoundedRect(rect.adjusted(-3, -6, 3, 4), 5, 5)
        slot = QRectF(rect.center().x() - 3, rect.top() + 16, 6, rect.height() - 40)
        # scale ticks
        p.setPen(QPen(QColor("#5c5f66"), 1))
        for n in range(11):
            y = slot.top() + n * slot.height() / 10
            w = 9 if n % 5 == 0 else 5
            p.drawLine(QPointF(slot.left() - 6 - w, y), QPointF(slot.left() - 6, y))
            p.drawLine(QPointF(slot.right() + 6, y), QPointF(slot.right() + 6 + w, y))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#000000"))
        p.drawRoundedRect(slot, 3, 3)
        # translucent cap like the real faders
        v = self.fader_values.get(c, 0) / 127.0
        cy = slot.bottom() - v * slot.height()
        cap = QRectF(rect.center().x() - 13, cy - 20, 26, 40)
        touched = c in self.touched
        g = QLinearGradient(cap.topLeft(), cap.bottomLeft())
        g.setColorAt(0, QColor("#f4f6f8"))
        g.setColorAt(0.45, QColor("#c3c7cd"))
        g.setColorAt(0.55, QColor("#9ea3aa"))
        g.setColorAt(1, QColor("#e2e5e9"))
        p.setBrush(QBrush(g))
        p.setPen(QPen(QColor(theme.ACCENT) if touched else QColor("#2a2c30"),
                      2.2 if touched else 1))
        p.drawRoundedRect(cap, 4, 4)
        p.setPen(QPen(QColor("#3a3d42"), 1.5))
        p.drawLine(QPointF(cap.left() + 3, cy), QPointF(cap.right() - 3, cy))
        text = self._label(c)
        if text:
            p.setPen(QColor("#d8d8d8"))
            p.setFont(ui_font(7))
            p.drawText(QRectF(rect.left() - 8, rect.top() - 4, rect.width() + 16, 14),
                       Qt.AlignCenter, text)
        self._outline(p, c, rect, 6)
