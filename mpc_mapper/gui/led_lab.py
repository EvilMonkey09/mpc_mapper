"""LED Lab: explore the APC mini mk2 LED codes live on the hardware."""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
                               QWidget)

from .. import apc
from ..apc import LedState
from .widgets import PaletteGrid


class LedLab(QWidget):
    """Controls column of the LED Lab page.

    The page shows its own APC drawing next to this column; clicking a pad or
    button there calls set_target(). Every action explains itself in the
    status line instead of silently doing nothing.
    """
    lab_mode_changed = Signal(bool)

    def __init__(self, device: apc.APCMini, selected: Callable[[], Optional[str]],
                 parent=None) -> None:
        super().__init__(parent)
        self.device = device
        self.selected = selected
        self.color = 21
        self.rgb = (255, 128, 0)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        # ---- status / target
        self.target_lbl = QLabel()
        self.target_lbl.setObjectName("CardTitle")
        self.target_lbl.setWordWrap(True)
        lay.addWidget(self.target_lbl)
        self.status = QLabel()
        self.status.setObjectName("Hint")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self.take = QCheckBox("Take over the LEDs (pauses grandMA3 feedback)")
        self.take.setToolTip("While this is on, the LEDs only show what you send from here.")
        self.take.toggled.connect(self.lab_mode_changed)
        lay.addWidget(self.take)

        # ---- palette colour
        box = QGroupBox("1  Palette colour")
        v = QVBoxLayout(box)
        self.grid = PaletteGrid(cell=22)
        self.grid.selected = self.color
        self.grid.picked.connect(self._pick)
        v.addWidget(self.grid)
        self.info = QLabel()
        self.info.setObjectName("Hint")
        v.addWidget(self.info)
        row = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems([m for m in apc.LED_MODES])
        self.mode.setCurrentIndex(apc.MODE_SOLID_100)
        self.mode.setToolTip("Behaviour = MIDI channel of the Note On message")
        self.mode.currentIndexChanged.connect(self._update_info)
        row.addWidget(self.mode, 1)
        b = QPushButton("Send to pad")
        b.setObjectName("Primary")
        b.clicked.connect(self._send_palette)
        row.addWidget(b)
        v.addLayout(row)
        lay.addWidget(box)

        # ---- true RGB
        box = QGroupBox("2  True RGB colour (pads only, static)")
        h = QHBoxLayout(box)
        self.rgb_btn = QPushButton("Pick colour…")
        self.rgb_btn.clicked.connect(self._pick_rgb)
        h.addWidget(self.rgb_btn, 1)
        b = QPushButton("Send to pad")
        b.clicked.connect(self._send_rgb)
        h.addWidget(b)
        lay.addWidget(box)

        # ---- track / scene buttons
        box = QGroupBox("3  Track / scene buttons")
        h = QHBoxLayout(box)
        for i, n in enumerate(apc.SINGLE_STATES):
            sb = QPushButton(n)
            sb.clicked.connect(lambda _=False, v=i: self._send_single(v))
            h.addWidget(sb)
        lay.addWidget(box)

        # ---- demos
        box = QGroupBox("Whole-device demos")
        g = QGridLayout(box)
        for i, (label, fn) in enumerate([
            ("Palette 0–63", lambda: self._palette_page(0)),
            ("Palette 64–127", lambda: self._palette_page(64)),
            ("Behaviours", self._modes_demo),
            ("RGB rainbow", self._rainbow),
            ("Buttons blink", self._buttons_blink),
            ("All off", self.device.clear_all),
        ]):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, f=fn: self._run_all(f))
            g.addWidget(btn, i // 2, i % 2)
        lay.addWidget(box)

        # ---- raw
        box = QGroupBox("Advanced: raw MIDI (hex)")
        r = QHBoxLayout(box)
        self.raw = QLineEdit("96 00 05")
        self.raw.setToolTip("e.g. '96 00 05' = Note On ch7 (0x96) pad 0 colour 5 (pulse)\n"
                            "'F0 47 7F 4F 24 00 08 00 00 01 7F 00 00 00 00 F7' = pad 0 red RGB")
        r.addWidget(self.raw, 1)
        sb = QPushButton("Send")
        sb.clicked.connect(self._send_raw)
        r.addWidget(sb)
        lay.addWidget(box)
        lay.addStretch(1)
        self._update_info()
        self.set_target(None)

    def set_target(self, control: Optional[str]) -> None:
        if control and apc.is_button(control):
            self.target_lbl.setText(f"Target: {apc.control_label(control)}")
        else:
            self.target_lbl.setText("Target: none")
        self._say("Click a pad or button on the drawing to choose where to send."
                  if not control else "")

    def _say(self, text: str, error: bool = False) -> None:
        if not text and not self.device.connected:
            text = "The APC is not connected – the LED Lab needs the real device."
            error = True
        color = "#ef5350" if error else ""
        self.status.setText(f"<span style='color:{color}'>{text}</span>" if color else text)

    def _ready(self, need: str) -> Optional[str]:
        """Return the target control, or explain why nothing can be sent."""
        if not self.device.connected:
            self._say("Connect the APC first (top left), then try again.", error=True)
            return None
        c = self._target()
        if c is None:
            self._say("Choose a pad or button on the drawing first.", error=True)
            return None
        if need == "pad" and not apc.is_rgb(c):
            self._say("Colours only work on the 64 pads – pick a pad.", error=True)
            return None
        if need == "single" and apc.is_rgb(c):
            self._say("Off/On/Blink is for the track and scene buttons – pick one of those.",
                      error=True)
            return None
        return c

    def _run_all(self, fn) -> None:
        if not self.device.connected:
            self._say("Connect the APC first (top left), then try again.", error=True)
            return
        self._run(fn)
        self._say("Sent to the whole device.")

    # ------------------------------------------------------------------ #
    def _run(self, fn) -> None:
        if not self.take.isChecked():
            self.take.setChecked(True)
        fn()

    def _pick(self, i: int) -> None:
        self.color = i
        self._update_info()

    def _update_info(self) -> None:
        r, g, b = apc.PALETTE[self.color]
        ch = self.mode.currentIndex()
        self.info.setText(
            f"Colour <b>{self.color}</b> · #{r:02X}{g:02X}{b:02X} · "
            f"MIDI <code>{0x90 | ch:02X} &lt;pad&gt; {self.color:02X}</code>")

    def _target(self) -> Optional[str]:
        c = self.selected()
        return c if c and apc.is_button(c) else None

    def _send_palette(self) -> None:
        c = self._ready("pad")
        if c:
            self._run(lambda: self.device.set_led(c, LedState(self.color, self.mode.currentIndex()),
                                                  force=True))
            self._say(f"Sent colour {self.color} to {apc.control_label(c)}.")

    def _pick_rgb(self) -> None:
        from PySide6.QtGui import QColor
        col = QColorDialog.getColor(QColor(*self.rgb), self, "Pad RGB colour")
        if col.isValid():
            self.rgb = (col.red(), col.green(), col.blue())
            fg = "#000" if sum(self.rgb) > 380 else "#fff"
            self.rgb_btn.setStyleSheet(f"background-color: rgb{self.rgb}; color: {fg};")
            self.rgb_btn.setText(f"#{self.rgb[0]:02X}{self.rgb[1]:02X}{self.rgb[2]:02X}")

    def _send_rgb(self) -> None:
        c = self._ready("pad")
        if c:
            self._run(lambda: self.device.set_led(c, LedState(rgb=self.rgb), force=True))
            self._say(f"Sent RGB colour to {apc.control_label(c)}.")

    def _send_single(self, v: int) -> None:
        c = self._ready("single")
        if c:
            self._run(lambda: self.device.set_led(c, LedState(v, 0), force=True))
            self._say(f"{apc.SINGLE_STATES[v]} sent to {apc.control_label(c)}.")

    def _palette_page(self, offset: int) -> None:
        for n in range(64):
            self.device.set_led(f"pad:{n}", LedState(offset + n, apc.MODE_SOLID_100), force=True)

    def _modes_demo(self) -> None:
        # bottom row solid 100%, then pulses, then blinks, using palette pick
        modes = [6, 3, 0, 7, 9, 10, 11, 15]
        for row in range(8):
            for col in range(8):
                self.device.set_led(apc.pad_id(row, col),
                                    LedState(self.color, modes[row]), force=True)

    def _rainbow(self) -> None:
        import colorsys
        for n in range(64):
            row, col = divmod(n, 8)
            h = (col / 8.0 + row / 64.0) % 1.0
            r, g, b = colorsys.hsv_to_rgb(h, 1.0, 1.0 - row * 0.08)
            self.device.set_led(f"pad:{n}", LedState(rgb=(int(r * 255), int(g * 255),
                                                          int(b * 255))), force=True)

    def _buttons_blink(self) -> None:
        for i in range(8):
            self.device.set_led(f"track:{i}", LedState(apc.SINGLE_BLINK, 0), force=True)
            self.device.set_led(f"scene:{i}", LedState(apc.SINGLE_BLINK, 0), force=True)

    def _send_raw(self) -> None:
        try:
            data = [int(x, 16) for x in self.raw.text().replace(",", " ").split()]
        except ValueError:
            self._say("That is not valid hex. Example: 96 00 05", error=True)
            return
        if not self.device.connected:
            self._say("Connect the APC first (top left), then try again.", error=True)
            return
        self._run(lambda: self.device.send_raw(data))
        self._say(f"Sent {len(data)} bytes.")
