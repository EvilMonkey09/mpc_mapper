"""Device test page: check every LED, motor and control of the APC mini mk2
and the X-Touch Compact.

1. Light & motor test: the app plays a sequence on the device, the user
   says whether everything lit up / moved.
2. Control test: every button, fader, encoder (and fader touch on the
   X-Touch) turns green on screen as soon as the app receives it.

While a test runs the engine is in test mode: nothing is sent to grandMA3
and the normal LED feedback is paused.

The "save test report" part is TEMPORARY (marked below) – it exists to
debug the X-Touch support remotely and can be removed once the hardware is
confirmed to work: delete the REPORT section and the report button.
"""
from __future__ import annotations

import datetime
import os
import platform
import sys
from typing import Callable, Optional

from PySide6.QtCore import QStandardPaths, Qt, QTimer
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

from .. import apc, controls, xtouch
from ..apc import LedState
from . import theme

STEP_MS = 60


def _short(control: str) -> str:
    """Compact chip text."""
    if xtouch.is_xtouch(control):
        k, i = xtouch.kind(control), xtouch.index(control)
        return {"fader": f"F{i + 1}" if i < 8 else "Main", "enc": f"E{i + 1}",
                "push": f"P{i + 1}", "btn": f"B{i + 1}",
                "ch": f"C{i + 1}" if i < 8 else "MainB",
                "tr": xtouch.TRANSPORT[i], "touch": f"T{i + 1}"}.get(k, control)
    k, _, i = control.partition(":")
    if k == "pad":
        n = int(i)
        return f"{n // 8 + 1}.{n % 8 + 1}"
    if k == "fader":
        return "M" if i == "8" else f"F{int(i) + 1}"
    if k == "track":
        return f"T{int(i) + 1}"
    if k == "scene":
        return f"S{int(i) + 1}"
    return "Shift"


class DeviceTest(QWidget):
    def __init__(self, engine, parent=None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.device = "apc"
        self._steps: list[tuple[str, Callable[[], None]]] = []
        self._step_i = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._next_step)
        self.results: dict[str, dict] = {"apc": {}, "xtouch": {}}
        self.seen: dict[str, set] = {}
        self.fader_range: dict[str, list[int]] = {}
        self.chips: dict[str, QLabel] = {}
        self.input_running = False
        self.midi_log: list[str] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        # ---- device choice
        top = QHBoxLayout()
        nav = QFrame()
        nav.setObjectName("Nav")
        nl = QHBoxLayout(nav)
        nl.setContentsMargins(4, 4, 4, 4)
        self.dev_group = QButtonGroup(self)
        for i, text in enumerate(("APC mini mk2", "X-Touch Compact")):
            b = QPushButton(text)
            b.setObjectName("Seg")
            b.setCheckable(True)
            self.dev_group.addButton(b, i)
            nl.addWidget(b)
        self.dev_group.button(0).setChecked(True)
        self.dev_group.idClicked.connect(self._choose_device)
        top.addWidget(nav)
        self.status = QLabel()
        self.status.setObjectName("Hint")
        self.status.setWordWrap(True)
        top.addWidget(self.status, 1)
        outer.addLayout(top)

        # ---- 1: output
        box = QGroupBox("1  Lights and motors")
        v = QVBoxLayout(box)
        self.out_hint = QLabel()
        self.out_hint.setWordWrap(True)
        v.addWidget(self.out_hint)
        row = QHBoxLayout()
        self.out_btn = QPushButton("Run light test")
        self.out_btn.setObjectName("Primary")
        self.out_btn.clicked.connect(self._run_output)
        row.addWidget(self.out_btn)
        self.out_progress = QLabel()
        self.out_progress.setObjectName("Hint")
        row.addWidget(self.out_progress, 1)
        v.addLayout(row)
        ask = QHBoxLayout()
        self.ok_btn = QPushButton("Everything worked")
        self.ok_btn.clicked.connect(lambda: self._answer(True))
        self.bad_btn = QPushButton("Something was missing")
        self.bad_btn.setObjectName("Danger")
        self.bad_btn.clicked.connect(lambda: self._answer(False))
        self.note = QLineEdit()
        self.note.setPlaceholderText("What was missing? e.g. fader 3 did not move")
        ask.addWidget(self.ok_btn)
        ask.addWidget(self.bad_btn)
        ask.addWidget(self.note, 1)
        v.addLayout(ask)
        outer.addWidget(box)

        # ---- 2: input
        box = QGroupBox("2  Buttons, faders and encoders")
        v = QVBoxLayout(box)
        self.in_hint = QLabel()
        self.in_hint.setWordWrap(True)
        v.addWidget(self.in_hint)
        row = QHBoxLayout()
        self.in_btn = QPushButton("Start control test")
        self.in_btn.setObjectName("Primary")
        self.in_btn.clicked.connect(self._toggle_input)
        row.addWidget(self.in_btn)
        self.in_progress = QLabel()
        row.addWidget(self.in_progress, 1)
        v.addLayout(row)
        self.chip_box = QWidget()
        self.chip_grid = QGridLayout(self.chip_box)
        self.chip_grid.setSpacing(4)
        self.chip_grid.setContentsMargins(0, 4, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self.chip_box)
        v.addWidget(scroll, 1)
        outer.addWidget(box, 1)

        # ---- REPORT (TEMPORARY, remove when the X-Touch is confirmed)
        rrow = QHBoxLayout()
        self.report_btn = QPushButton("Save test report")
        self.report_btn.setToolTip("Writes a text file with all results and MIDI messages "
                                   "to Documents/MPC Mapper (temporary debugging aid)")
        self.report_btn.clicked.connect(self.save_report)
        rrow.addWidget(self.report_btn)
        self.report_lbl = QLabel()
        self.report_lbl.setObjectName("Hint")
        self.report_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        rrow.addWidget(self.report_lbl, 1)
        outer.addLayout(rrow)
        # ---- /REPORT

        engine.control_event.connect(self._on_event)
        engine.touch_changed.connect(self._on_touch)
        engine.log.connect(self._on_log)
        engine.status_changed.connect(self._update_status)
        self._choose_device(0)

    # ------------------------------------------------------------------ #
    def _dev(self):
        return self.engine.xt if self.device == "xtouch" else self.engine.apc

    def _name(self) -> str:
        return "X-Touch Compact" if self.device == "xtouch" else "APC mini mk2"

    def _choose_device(self, i: int) -> None:
        self._stop_all()
        self.device = "xtouch" if i == 1 else "apc"
        if self.device == "apc":
            self.out_hint.setText("All 64 pads light up in red, green, blue and white, then the "
                                  "track and scene buttons light and blink. Watch the APC.")
        else:
            self.out_hint.setText("Every button lights up one after another, then all blink. "
                                  "Each motor fader moves up and down, then each encoder ring "
                                  "fills up. Watch the X-Touch – keep your hands off the faders.")
        extra = (" Also touch each fader cap once (touch sensor)."
                 if self.device == "xtouch" else "")
        self.in_hint.setText("Press every button once, move every fader all the way up and "
                             "down" + (" and turn every encoder both ways" if self.device ==
                                       "xtouch" else "") + "." + extra +
                             " Each control turns green when it arrives.")
        self._build_chips()
        self._update_status()

    def _targets(self) -> list[str]:
        if self.device == "apc":
            return list(apc.ALL_CONTROLS)
        return list(xtouch.ALL_CONTROLS) + [f"xt.touch:{i}" for i in range(9)]

    def _build_chips(self) -> None:
        while self.chip_grid.count():
            w = self.chip_grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.chips.clear()
        cols = 16 if self.device == "xtouch" else 18
        for n, c in enumerate(self._targets()):
            lb = QLabel(_short(c))
            lb.setAlignment(Qt.AlignCenter)
            lb.setMinimumWidth(40)
            lb.setToolTip(controls.label(c) if not c.startswith("xt.touch")
                          else f"X-Touch fader {int(c[-1]) + 1} touch" if c[-1] != "8"
                          else "X-Touch main fader touch")
            self.chips[c] = lb
            self._paint_chip(c, False)
            self.chip_grid.addWidget(lb, n // cols, n % cols)
        self.seen[self.device] = set()
        self.fader_range.clear()
        self._update_progress()

    def _paint_chip(self, c: str, ok: bool, partial: bool = False) -> None:
        bg = theme.OK if ok else ("#6b5a1e" if partial else theme.RAISED)
        fg = "#08130c" if ok else theme.TEXT
        self.chips[c].setStyleSheet(f"background:{bg}; color:{fg}; border-radius:5px; "
                                    "padding:3px 4px; font-size:11px;")

    def _update_status(self) -> None:
        if not self._dev().connected:
            self.status.setText(f"<span style='color:{theme.ERR}'>The {self._name()} is not "
                                "connected. Connect it at the top first.</span>")
        else:
            self.status.setText(f"{self._name()} connected. While a test runs, nothing is sent "
                                "to grandMA3.")

    def _need_device(self) -> bool:
        if self._dev().connected:
            return True
        self._update_status()
        return False

    # ---------------- output test ----------------
    def _run_output(self) -> None:
        if not self._need_device():
            return
        self._stop_input()
        self.engine.set_test_mode(True)
        self._steps = self._apc_steps() if self.device == "apc" else self._xt_steps()
        self._step_i = 0
        self.out_btn.setEnabled(False)
        self._timer.start(STEP_MS)

    def _next_step(self) -> None:
        if self._step_i >= len(self._steps):
            self._timer.stop()
            self.out_btn.setEnabled(True)
            self.out_btn.setText("Run light test again")
            self.out_progress.setText("Done. Did everything light up and move?")
            self.engine.set_test_mode(False)
            return
        text, fn = self._steps[self._step_i]
        self._step_i += 1
        try:
            fn()
        except Exception as e:  # keep going, but note it
            self.midi_log.append(f"step error: {text}: {e}")
        self.out_progress.setText(f"{text}  ({self._step_i}/{len(self._steps)})")

    def _apc_steps(self) -> list:
        a = self.engine.apc
        steps = []
        for name, color in (("red", 5), ("green", 21), ("blue", 45), ("white", 3)):
            def all_pads(c=color):
                for n in range(64):
                    a.set_led(f"pad:{n}", LedState(c, apc.MODE_SOLID_100), force=True)
            steps.append((f"All pads {name}", all_pads))
            steps += [(f"All pads {name}", lambda: None)] * 8      # hold
        for n in range(64):                                         # walk once
            steps.append(("Pads one by one", lambda n=n: (
                a.set_led(f"pad:{n}", LedState(53, apc.MODE_SOLID_100), force=True))))
        for state, label in ((apc.SINGLE_ON, "on"), (apc.SINGLE_BLINK, "blinking")):
            def btns(s=state):
                for i in range(8):
                    a.set_led(f"track:{i}", LedState(s, 0), force=True)
                    a.set_led(f"scene:{i}", LedState(s, 0), force=True)
            steps.append((f"Track and scene buttons {label}", btns))
            steps += [(f"Track and scene buttons {label}", lambda: None)] * 15
        steps.append(("All off", a.clear_all))
        return steps

    def _xt_steps(self) -> list:
        x = self.engine.xt
        steps = []
        led_ctrls = [c for c in xtouch.ALL_CONTROLS if xtouch.has_led(c)]
        for c in led_ctrls:
            steps.append(("Buttons one by one", lambda c=c: x.set_led(c, 1, force=True)))
        def blink():
            for c in led_ctrls:
                x.set_led(c, 2, force=True)
        steps.append(("All buttons blinking", blink))
        steps += [("All buttons blinking", lambda: None)] * 20
        def off():
            for c in led_ctrls:
                x.set_led(c, 0, force=True)
        steps.append(("Buttons off", off))
        for i in range(9):
            f = f"xt.fader:{i}"
            name = "Main fader" if i == 8 else f"Fader {i + 1}"
            for v in (127, 127, 127, 0, 0, 0, 64):
                steps += [(f"{name} moves", lambda f=f, v=v: x.set_position(f, v, force=True))]
        for i in range(16):
            e = f"xt.enc:{i}"
            for v in range(0, 128, 16):
                steps.append((f"Encoder ring {i + 1}", lambda e=e, v=v: x.set_position(e, v, force=True)))
            steps.append((f"Encoder ring {i + 1}", lambda e=e: x.set_position(e, 127, force=True)))
        def rings_off():
            for i in range(16):
                x.set_position(f"xt.enc:{i}", 0, force=True)
        steps.append(("Rings off", rings_off))
        return steps

    def _answer(self, ok: bool) -> None:
        self.results[self.device]["output_ok"] = ok
        self.results[self.device]["output_note"] = self.note.text().strip()
        self.out_progress.setText("Thanks – noted." if ok else
                                  "Noted. Add what was missing in the text field if you can.")
        self.save_report(auto=True)  # REPORT (TEMPORARY)

    # ---------------- input test ----------------
    def _toggle_input(self) -> None:
        if self.input_running:
            self._stop_input()
            return
        if not self._need_device():
            return
        self._build_chips()
        self.input_running = True
        self.engine.set_test_mode(True)
        self.in_btn.setText("Stop control test")
        self.in_btn.setObjectName("")
        self.in_btn.style().unpolish(self.in_btn)
        self.in_btn.style().polish(self.in_btn)

    def _stop_input(self) -> None:
        if not self.input_running:
            return
        self.input_running = False
        self.engine.set_test_mode(False)
        self.in_btn.setText("Start control test")
        self.in_btn.setObjectName("Primary")
        self.in_btn.style().unpolish(self.in_btn)
        self.in_btn.style().polish(self.in_btn)
        seen = self.seen.get(self.device, set())
        self.results[self.device]["inputs_seen"] = sorted(seen)
        self.results[self.device]["inputs_missing"] = [c for c in self._targets() if c not in seen]
        self.save_report(auto=True)  # REPORT (TEMPORARY)

    def _stop_all(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self.out_btn.setEnabled(True)
            self.engine.set_test_mode(False)
        self._stop_input()

    def _mark(self, c: str) -> None:
        seen = self.seen.setdefault(self.device, set())
        if c in self.chips and c not in seen:
            seen.add(c)
            self._paint_chip(c, True)
            self._update_progress()

    def _on_event(self, control: str, value) -> None:
        if not self.input_running or control not in self.chips:
            return
        if controls.is_value(control):
            rng = self.fader_range.setdefault(control, [127, 0])
            rng[0], rng[1] = min(rng[0], int(value)), max(rng[1], int(value))
            full = rng[0] <= 8 and rng[1] >= 119
            if xtouch.kind(control) == "enc":
                full = rng[1] - rng[0] >= 20          # turned noticeably
            if full:
                self._mark(control)
            else:
                self._paint_chip(control, False, partial=True)
        elif value:
            self._mark(control)

    def _on_touch(self, control: str, touched: bool) -> None:
        if self.input_running and touched:
            self._mark(f"xt.touch:{xtouch.index(control)}")

    def _update_progress(self) -> None:
        total = len(self.chips)
        n = len(self.seen.get(self.device, set()))
        color = theme.OK if n == total and total else theme.TEXT
        self.in_progress.setText(f"<span style='color:{color}'><b>{n}</b> of {total} "
                                 "controls received</span>"
                                 + ("  – all done!" if n == total and total else ""))

    def _on_log(self, src: str, direction: str, text: str) -> None:
        if src == "midi" and (self.input_running or self._timer.isActive()):
            self.midi_log.append(f"{datetime.datetime.now():%H:%M:%S.%f}"[:-3]
                                 + f" {direction:3} {text}")
            del self.midi_log[:-3000]

    # ================================================================== #
    # REPORT (TEMPORARY) – remove this section together with report_btn
    # once the X-Touch Compact support is confirmed on real hardware.
    # ================================================================== #
    def report_text(self) -> str:
        s = self.engine.mapping.settings
        lines = [
            "MPC Mapper device test report",
            f"time: {datetime.datetime.now():%Y-%m-%d %H:%M:%S}",
            f"system: {platform.platform()} / Python {sys.version.split()[0]}",
            f"APC ports: in={self.engine.apc.in_name!r} out={self.engine.apc.out_name!r}",
            f"X-Touch ports: in={self.engine.xt.in_name!r} out={self.engine.xt.out_name!r} "
            f"out_channel={s.xt_out_channel} (0 = ch 1+2)",
            f"available MIDI ports: {apc.list_ports()}",
            "",
        ]
        for dev in ("apc", "xtouch"):
            r = self.results.get(dev) or {}
            if not r and not self.seen.get(dev):
                continue
            lines.append(f"== {dev}")
            lines.append(f"light/motor test ok: {r.get('output_ok')}  note: {r.get('output_note', '')}")
            seen = sorted(self.seen.get(dev, set()))
            lines.append(f"controls received ({len(seen)}): {' '.join(seen)}")
            if "inputs_missing" in r:
                lines.append(f"controls missing ({len(r['inputs_missing'])}): "
                             f"{' '.join(r['inputs_missing'])}")
            lines.append("")
        lines.append("== MIDI messages during the tests (last 3000)")
        lines += self.midi_log
        return "\n".join(lines) + "\n"

    def save_report(self, auto: bool = False) -> Optional[str]:
        docs = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) \
            or os.path.expanduser("~")
        folder = os.path.join(docs, "MPC Mapper")
        try:
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, "device-test-report.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.report_text())
        except OSError as e:
            self.report_lbl.setText(f"Could not save the report: {e}")
            return None
        self.report_lbl.setText(f"Report saved: {path}" + ("  (automatically)" if auto else ""))
        return path
    # ---- /REPORT
