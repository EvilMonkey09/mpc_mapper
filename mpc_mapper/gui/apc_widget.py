"""Interactive drawing of the APC mini mk2.

* Drop a grandMA3 control from the catalogue onto a pad/button/fader.
* Drag one control onto another to move the assignment (hold Ctrl to copy).
* Click selects; Shift+click (or right-click > Simulate) fires the control
  as if pressed on the hardware; Shift+drag on a fader moves it.
* Pads are painted with the LED state the engine actually sends.
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QMimeData, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QDrag, QLinearGradient, QPainter,
                           QPen)
from PySide6.QtWidgets import QMenu, QWidget

from .. import apc, controls
from ..apc import LedState
from ..model import Mapping
from . import theme
from .widgets import qcolor, text_color_for, ui_font

MIME_CATALOG = "application/x-ma3-catalog"
MIME_CONTROL = "application/x-apc-control"

# logical geometry (scaled to widget), laid out like the real APC mini mk2:
# 8x8 rectangular pads, soft keys (scene launch) on the right with their
# labels, round-cornered red track keys under the grid, 9 faders at the bottom.
PAD_W, PAD_H, GAP_X, GAP_Y = 60.0, 38.0, 10.0, 10.0
X0, Y0 = 42.0, 92.0
GRID_W = 8 * PAD_W + 7 * GAP_X
GRID_H = 8 * PAD_H + 7 * GAP_Y
SCENE_X = X0 + GRID_W + 30
SCENE_S = 26.0                       # soft key size
TRACK_Y = Y0 + GRID_H + 36
TRACK_W, TRACK_H = 26.0, 16.0
FADER_Y = TRACK_Y + TRACK_H + 34
FADER_H = 190.0
W = SCENE_X + SCENE_S + 96
H = FADER_Y + FADER_H + 34
EDGE = 9.0                           # red side edges

SCENE_LABELS = ["CLIP STOP", "SOLO", "MUTE", "REC ARM", "SELECT", "DRUM", "NOTE",
                "STOP ALL CLIPS"]
TRACK_LABELS = ["VOLUME", "PAN", "SEND", "DEVICE", "▲", "▼", "◀", "▶"]
AKAI_RED = "#e2231a"


def _col_x(i: int) -> float:
    return X0 + i * (PAD_W + GAP_X)


def _col_cx(i: int) -> float:
    return _col_x(i) + PAD_W / 2


def _row_y(row_from_top: int) -> float:
    return Y0 + row_from_top * (PAD_H + GAP_Y)


def control_rect(control: str) -> QRectF:
    kind, _, idx = control.partition(":")
    if kind == "pad":
        n = int(idx)
        row, col = divmod(n, 8)
        return QRectF(_col_x(col), _row_y(7 - row), PAD_W, PAD_H)
    if kind == "scene":
        n = int(idx)  # 0 = top
        return QRectF(SCENE_X, _row_y(n) + (PAD_H - SCENE_S) / 2, SCENE_S, SCENE_S)
    if kind == "track":
        return QRectF(_col_cx(int(idx)) - TRACK_W / 2, TRACK_Y, TRACK_W, TRACK_H)
    if kind == "shift":
        return QRectF(SCENE_X, TRACK_Y, SCENE_S, TRACK_H)
    if kind == "fader":
        n = int(idx)
        cx = SCENE_X + SCENE_S / 2 if n == 8 else _col_cx(n)
        return QRectF(cx - 24, FADER_Y, 48, FADER_H)
    return QRectF()


class APCWidget(QWidget):
    """Interactive device drawing. Subclasses (X-Touch) override the
    geometry (LW/LH, controls(), ctrl_rect()) and paint_device()."""
    LW, LH = W, H
    selected = Signal(str)
    catalog_dropped = Signal(str, str)      # catalog_id, control
    control_moved = Signal(str, str, bool)  # src, dst, copy
    simulate_button = Signal(str, bool)
    simulate_fader = Signal(str, int)
    clear_requested = Signal(str)

    def __init__(self, mapping: Mapping, parent=None) -> None:
        super().__init__(parent)
        self.mapping = mapping
        self.leds: dict[str, LedState] = {}
        self.fader_values: dict[str, int] = {}
        self.touched: set[str] = set()
        self.hw_pressed: set[str] = set()
        self.selected_control: Optional[str] = None
        self.drop_hover: Optional[str] = None
        self.accepts: Callable[[str, str], bool] = lambda cat, ctrl: True
        self._press_pos: Optional[QPointF] = None
        self._press_ctrl: Optional[str] = None
        self._sim_down: Optional[str] = None
        self._blink = False
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setMinimumSize(int(self.LW * 0.5), int(self.LH * 0.5))
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(250)

    # ------------------------------------------------------------------ #
    def _tick(self) -> None:
        self._blink = not self._blink
        if any(s.animated for s in self.leds.values()) or any(
                s.color == apc.SINGLE_BLINK for c, s in self.leds.items() if not controls.is_rgb(c)):
            self.update()

    def set_led(self, control: str, state: LedState) -> None:
        self.leds[control] = state
        self.update()

    def set_touch(self, control: str, touched: bool) -> None:
        (self.touched.add if touched else self.touched.discard)(control)
        self.update()

    # overridable geometry / classification
    def controls(self) -> list[str]:
        return apc.ALL_CONTROLS

    def ctrl_rect(self, control: str) -> QRectF:
        return control_rect(control)

    @staticmethod
    def is_value(control: str) -> bool:
        return controls.is_value(control)

    def hw_event(self, control: str, value) -> None:
        if control not in self.controls():
            return
        if self.is_value(control):
            self.fader_values[control] = int(value)
        elif value:
            self.hw_pressed.add(control)
        else:
            self.hw_pressed.discard(control)
        self.update()

    def select(self, control: Optional[str]) -> None:
        self.selected_control = control
        self.update()
        if control:
            self.selected.emit(control)

    # ---------------- geometry ----------------
    def _scale(self) -> tuple[float, float, float]:
        s = min(self.width() / self.LW, self.height() / self.LH)
        ox = (self.width() - self.LW * s) / 2
        oy = (self.height() - self.LH * s) / 2
        return s, ox, oy

    def _to_logical(self, p: QPointF) -> QPointF:
        s, ox, oy = self._scale()
        return QPointF((p.x() - ox) / s, (p.y() - oy) / s)

    def control_at(self, p: QPointF) -> Optional[str]:
        lp = self._to_logical(p)
        for c in self.controls():
            if self.ctrl_rect(c).adjusted(-3, -3, 3, 3).contains(lp):
                return c
        return None

    # ---------------- painting ----------------
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(theme.BG))
        s, ox, oy = self._scale()
        p.translate(ox, oy)
        p.scale(s, s)
        self.paint_device(p)

    def paint_device(self, p: QPainter) -> None:
        # body: black with red side edges
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(AKAI_RED))
        p.drawRoundedRect(QRectF(0, 2, W, H - 4), 10, 10)
        body = QRectF(EDGE, 2, W - 2 * EDGE, H - 4)
        grad = QLinearGradient(0, 0, 0, H)
        grad.setColorAt(0, QColor("#1d1e21"))
        grad.setColorAt(1, QColor("#141517"))
        p.setBrush(QBrush(grad))
        p.drawRect(body)
        # logos
        p.setPen(QColor("#f2f2f2"))
        p.setFont(ui_font(20, bold=True))
        p.drawText(QRectF(X0, 22, 160, 30), Qt.AlignLeft | Qt.AlignVCenter, "AKAI")
        p.setFont(ui_font(6, bold=True))
        p.drawText(QRectF(X0 + 1, 50, 160, 12), Qt.AlignLeft | Qt.AlignVCenter, "PROFESSIONAL")
        p.setFont(ui_font(17, bold=True))
        right = QRectF(_col_x(5), 26, GRID_W - _col_x(5) + X0, 30)
        p.drawText(right, Qt.AlignRight | Qt.AlignVCenter, "APC")
        p.setFont(ui_font(14))
        fm_w = 46
        p.drawText(QRectF(right.right() + 2, 28, fm_w, 30), Qt.AlignLeft | Qt.AlignVCenter, "mini")
        p.setPen(QColor("#7d8087"))
        p.setFont(ui_font(8))
        p.drawText(QRectF(X0 + 150, 64, GRID_W - 150, 16), Qt.AlignRight | Qt.AlignVCenter,
                   f"Shift+click = simulate · drag = move · {theme.MOD_KEY}+drag = copy")
        # soft-keys header + vertical "SCENE LAUNCH"
        p.setPen(QColor("#d8d8d8"))
        p.setFont(ui_font(6, bold=True))
        p.drawText(QRectF(SCENE_X + SCENE_S + 8, Y0 - 24, 80, 20), Qt.AlignLeft | Qt.AlignVCenter,
                   "SOFT\nKEYS")
        # "FADER CTRL" bracket over the first four track keys
        p.setPen(QPen(QColor("#9a9da3"), 1))
        by = TRACK_Y - 12
        p.drawLine(QPointF(_col_cx(0), by), QPointF(_col_cx(3), by))
        for i in (0, 3):
            p.drawLine(QPointF(_col_cx(i), by), QPointF(_col_cx(i), by + 4))
        p.setFont(ui_font(6, bold=True))
        p.setPen(QColor("#d8d8d8"))
        mid = (_col_cx(1) + _col_cx(2)) / 2
        p.fillRect(QRectF(mid - 28, by - 6, 56, 12), QColor("#18191c"))
        p.drawText(QRectF(mid - 28, by - 7, 56, 12), Qt.AlignCenter, "FADER CTRL")

        for c in apc.ALL_CONTROLS:
            kind = apc.control_kind(c)
            if kind == "pad":
                self._paint_pad(p, c)
            elif kind == "fader":
                self._paint_fader(p, c)
            else:
                self._paint_button(p, c)

    def _outline(self, p: QPainter, c: str, rect: QRectF, radius: float) -> None:
        if c == self.drop_hover:
            p.setPen(QPen(QColor("#ffd23f"), 3, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect.adjusted(-4, -4, 4, 4), radius + 2, radius + 2)
        if c == self.selected_control:
            p.setPen(QPen(QColor("#3fa9ff"), 3))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect.adjusted(-4, -4, 4, 4), radius + 2, radius + 2)
        if c in self.hw_pressed:
            p.setPen(QPen(QColor("white"), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), radius, radius)

    def _label(self, c: str) -> str:
        a = self.mapping.assignments.get(c)
        return a.name if a else ""

    def _paint_pad(self, p: QPainter, c: str) -> None:
        rect = self.ctrl_rect(c)
        st = self.leds.get(c, LedState(0))
        rgb = st.display_rgb()
        if st.animated and self._blink:
            if st.mode >= 11:   # blink -> off phase
                rgb = (0, 0, 0)
            else:               # pulse -> dim phase
                rgb = tuple(int(v * 0.35) for v in rgb)
        lit = max(rgb) > 8
        if lit:                                   # soft glow around a lit pad
            glow = qcolor(rgb)
            glow.setAlpha(70)
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawRoundedRect(rect.adjusted(-3, -3, 3, 3), 6, 6)
        base = qcolor(rgb) if lit else QColor("#3a3c41")
        g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        g.setColorAt(0, base.lighter(118))
        g.setColorAt(1, base.darker(112))
        p.setPen(QPen(QColor("#0b0b0c"), 1.2))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(rect, 3.5, 3.5)
        text = self._label(c)
        if text:
            p.setPen(text_color_for(rgb) if lit else QColor("#d0d0d0"))
            p.setFont(ui_font(7))
            p.drawText(rect.adjusted(3, 2, -3, -2), Qt.AlignCenter | Qt.TextWordWrap, text)
        self._outline(p, c, rect, 4)

    def _paint_button(self, p: QPainter, c: str) -> None:
        rect = self.ctrl_rect(c)
        kind, _, idx = c.partition(":")
        st = self.leds.get(c, LedState(0, 0))
        on = st.color == apc.SINGLE_ON or (st.color == apc.SINGLE_BLINK and not self._blink)
        if kind == "track":
            col = QColor("#ff3b30") if on else QColor("#d9a2a6")
            glow = QColor(255, 59, 48, 90)
        elif kind == "scene":
            col = QColor("#36e85a") if on else QColor("#9fa2a8")
            glow = QColor(54, 232, 90, 90)
        else:
            col, glow = QColor("#9fa2a8"), None
        if on and glow is not None:
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawRoundedRect(rect.adjusted(-3, -3, 3, 3), 5, 5)
        g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        g.setColorAt(0, col.lighter(110))
        g.setColorAt(1, col.darker(115))
        p.setPen(QPen(QColor("#0b0b0c"), 1.2))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(rect, 3, 3)
        # label: the assignment if there is one, else the printed name
        text = self._label(c)
        printed = (SCENE_LABELS[int(idx)] if kind == "scene" else
                   TRACK_LABELS[int(idx)] if kind == "track" else "SHIFT")
        p.setPen(QColor("#e6e6e6") if text else QColor("#8d9096"))
        p.setFont(ui_font(6, bold=not text))
        if kind == "scene":
            box = QRectF(rect.right() + 7, rect.top() - 4, 78, rect.height() + 8)
            p.drawText(box, Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, text or printed)
        else:
            box = QRectF(rect.center().x() - 34, rect.bottom() + 2, 68, 22)
            p.drawText(box, Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, text or printed)
        self._outline(p, c, rect, 3)

    def _paint_fader(self, p: QPainter, c: str) -> None:
        rect = self.ctrl_rect(c)
        well = QRectF(rect.center().x() - 17, rect.top(), 34, rect.height())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#0b0c0d"))
        p.drawRoundedRect(well, 4, 4)
        slot = QRectF(rect.center().x() - 2.5, rect.top() + 14, 5, rect.height() - 28)
        p.setBrush(QColor("#000000"))
        p.drawRoundedRect(slot, 2.5, 2.5)
        v = self.fader_values.get(c, 0) / 127.0
        cy = slot.bottom() - v * slot.height()
        cap = QRectF(rect.center().x() - 15, cy - 9, 30, 18)
        g = QLinearGradient(cap.topLeft(), cap.bottomLeft())
        g.setColorAt(0, QColor("#2a2b2e"))
        g.setColorAt(0.35, QColor("#e9ebee"))   # chrome stripe like the real caps
        g.setColorAt(0.65, QColor("#9ea2a8"))
        g.setColorAt(1, QColor("#1e1f22"))
        p.setBrush(QBrush(g))
        p.setPen(QPen(QColor("#050505"), 1))
        p.drawRoundedRect(cap, 3, 3)
        text = self._label(c) or ("Master" if c == "fader:8" else "")
        if text:
            p.setPen(QColor("#d8d8d8"))
            p.setFont(ui_font(7))
            p.drawText(QRectF(rect.left() - 10, rect.bottom() + 3, rect.width() + 20, 26),
                       Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, text)
        self._outline(p, c, rect, 6)

    # ---------------- mouse ----------------
    def mousePressEvent(self, e) -> None:
        c = self.control_at(e.position())
        if e.button() == Qt.RightButton:
            if c:
                self._context_menu(c, e.globalPosition().toPoint())
            return
        if e.button() != Qt.LeftButton:
            return
        if c and e.modifiers() & Qt.ShiftModifier:
            if self.is_value(c):
                self._sim_down = c
                self._sim_fader_to(c, e.position())
            else:
                self._sim_down = c
                self.simulate_button.emit(c, True)
            return
        self._press_pos = e.position()
        self._press_ctrl = c
        self.select(c)

    def _sim_fader_to(self, c: str, pos: QPointF) -> None:
        rect = self.ctrl_rect(c)
        lp = self._to_logical(pos)
        top, bot = rect.top() + 8, rect.bottom() - 8
        v = int(round(max(0.0, min(1.0, (bot - lp.y()) / (bot - top))) * 127))
        self.simulate_fader.emit(c, v)

    def mouseMoveEvent(self, e) -> None:
        if self._sim_down and self.is_value(self._sim_down):
            self._sim_fader_to(self._sim_down, e.position())
            return
        if (self._press_ctrl and self._press_pos is not None and e.buttons() & Qt.LeftButton
                and (e.position() - self._press_pos).manhattanLength() > 8
                and self._press_ctrl in self.mapping.assignments):
            drag = QDrag(self)
            md = QMimeData()
            md.setData(MIME_CONTROL, self._press_ctrl.encode())
            drag.setMimeData(md)
            self._press_ctrl = None
            drag.exec(Qt.MoveAction | Qt.CopyAction)

    def mouseReleaseEvent(self, e) -> None:
        if self._sim_down:
            if not self.is_value(self._sim_down):
                self.simulate_button.emit(self._sim_down, False)
            self._sim_down = None
        self._press_ctrl = None
        self._press_pos = None

    def _context_menu(self, c: str, gpos) -> None:
        self.select(c)
        m = QMenu(self)
        if controls.is_button(c):
            act = m.addAction("Simulate press")
            act.triggered.connect(lambda: (self.simulate_button.emit(c, True),
                                           QTimer.singleShot(150, lambda: self.simulate_button.emit(c, False))))
        clr = m.addAction("Clear assignment")
        clr.setEnabled(c in self.mapping.assignments)
        clr.triggered.connect(lambda: self.clear_requested.emit(c))
        m.exec(gpos)

    # ---------------- drag & drop ----------------
    def _drop_ok(self, e) -> Optional[str]:
        c = self.control_at(e.position())
        if not c:
            return None
        md = e.mimeData()
        if md.hasFormat(MIME_CATALOG):
            cat = bytes(md.data(MIME_CATALOG)).decode()
            return c if self.accepts(cat, c) else None
        if md.hasFormat(MIME_CONTROL):
            src = bytes(md.data(MIME_CONTROL)).decode()
            if src == c:
                return None
            same = self.is_value(src) == self.is_value(c)
            return c if same else None
        return None

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasFormat(MIME_CATALOG) or e.mimeData().hasFormat(MIME_CONTROL):
            e.acceptProposedAction()

    def dragMoveEvent(self, e) -> None:
        c = self._drop_ok(e)
        if c != self.drop_hover:
            self.drop_hover = c
            self.update()
        if c:
            if e.mimeData().hasFormat(MIME_CONTROL):
                e.setDropAction(Qt.CopyAction if e.modifiers() & Qt.ControlModifier
                                else Qt.MoveAction)
                e.accept()
            else:
                e.acceptProposedAction()
        else:
            e.ignore()

    def dragLeaveEvent(self, _e) -> None:
        self.drop_hover = None
        self.update()

    def dropEvent(self, e) -> None:
        c = self._drop_ok(e)
        self.drop_hover = None
        self.update()
        if not c:
            e.ignore()
            return
        md = e.mimeData()
        if md.hasFormat(MIME_CATALOG):
            self.catalog_dropped.emit(bytes(md.data(MIME_CATALOG)).decode(), c)
        else:
            src = bytes(md.data(MIME_CONTROL)).decode()
            copy = bool(e.modifiers() & Qt.ControlModifier)
            self.control_moved.emit(src, c, copy)
        e.acceptProposedAction()
        self.select(c)
