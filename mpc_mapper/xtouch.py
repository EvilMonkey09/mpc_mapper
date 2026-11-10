"""Behringer X-Touch Compact (standard MIDI mode) protocol + MIDI I/O.

Sources for the MIDI map:
  * Behringer X-Touch Compact Quick Start Guide, "MIDI map" (layer A, ch 1)
    and "Rx MIDI data" tables.
  * Modality toolkit, behringer-x-touch-compact.desc.scd (tested on the
    hardware): https://github.com/ModalityTeam/Modality-toolkit

Transmit (device -> host), standard mode, layer A (layer B in brackets):
  * Encoder push ......... Note  0-7  (55-62)  top row, 8-15 (63-70) right block
  * Button rows 1-3 ...... Note 16-39 (71-94)  row r, column c -> 16 + 8r + c
  * Channel buttons ...... Note 40-47 (95-102), main button 48 (103)
  * Transport ............ Note 49-54 (104-109) rew fwd loop rec stop play
  * Faders ............... CC 1-8 (28-35), main fader CC 9 (36)
  * Encoders ............. CC 10-17 (37-44) top row, 18-25 (45-52) right block
  * Fader touch .......... CC 101-108 (111-118), main 109 (119); 127 = touched
  * Pedals ............... CC 26 expression, 27 foot switch (63, 64)

Receive (host -> device) on the unit's GLOBAL channel:
  * Button LEDs .......... Note 0-23 button rows, 24-31 channel buttons,
                           32 main button, 33-38 transport
                           velocity 0 = off, 1 = on, 2 = blink
  * Motor faders ......... CC 1-9, value 0-127
  * Encoder ring mode .... CC 10-17 / 18-25: 0 single, 1 pan, 2 fan, 3 spread, 4 trim
  * Encoder ring value ... CC 26-33 / 34-41: 0 off, 1-13 LED 1..13, 14-26 blinking,
                           27 all on, 28 all blinking
  * Operation mode ....... CC 127: 0 = standard, 1 = Mackie Control
  * Layer ................ Program Change 0 = A, 1 = B

The global channel is not documented as a fixed number (the Modality
description talks to the unit on channel 2), so by default every output
message is sent on channels 1 *and* 2; the setting xt_out_channel can pin
it to one channel.

The app only uses layer A. Messages from layer B are mapped onto the same
controls and the unit is switched back to layer A, because motor faders and
LEDs always show what was sent last, whatever layer is active.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from .apc import _ports, mido  # same MIDI backend as the APC (WinMM on Windows)

PREFIX = "xt."

# --------------------------------------------------------------------------- #
# control ids
#   xt.fader:<0-8>    8 = main fader
#   xt.enc:<0-15>     0-7 top row, 8-15 right block (rotation)
#   xt.push:<0-15>    encoder push buttons (no LED)
#   xt.btn:<0-23>     three button rows above the faders, row-major
#   xt.ch:<0-8>       button below each fader, 8 = main
#   xt.tr:<0-5>       transport: rew, fwd, loop, rec, stop, play
# --------------------------------------------------------------------------- #
TRANSPORT = ["Rew", "Fwd", "Loop", "Rec", "Stop", "Play"]

ALL_CONTROLS: list[str] = (
    [f"xt.fader:{i}" for i in range(9)]
    + [f"xt.enc:{i}" for i in range(16)]
    + [f"xt.push:{i}" for i in range(16)]
    + [f"xt.btn:{i}" for i in range(24)]
    + [f"xt.ch:{i}" for i in range(9)]
    + [f"xt.tr:{i}" for i in range(6)]
)
_ALL = set(ALL_CONTROLS)


def is_xtouch(control: str) -> bool:
    return control.startswith(PREFIX)


def kind(control: str) -> str:
    return control[len(PREFIX):].partition(":")[0] if is_xtouch(control) else ""


def index(control: str) -> int:
    return int(control.partition(":")[2])


def is_button(control: str) -> bool:
    return kind(control) in ("push", "btn", "ch", "tr")


def has_led(control: str) -> bool:
    return kind(control) in ("btn", "ch", "tr")


def is_value(control: str) -> bool:
    """Faders and encoders: controls that send a 0-127 value."""
    return kind(control) in ("fader", "enc")


def control_label(control: str) -> str:
    k, i = kind(control), index(control)
    if k == "fader":
        return "X-Touch main fader" if i == 8 else f"X-Touch fader {i + 1}"
    if k == "enc":
        return f"X-Touch encoder {i + 1}"
    if k == "push":
        return f"X-Touch encoder {i + 1} push"
    if k == "btn":
        return f"X-Touch button R{i // 8 + 1} C{i % 8 + 1}"
    if k == "ch":
        return "X-Touch main button" if i == 8 else f"X-Touch channel button {i + 1}"
    if k == "tr":
        return f"X-Touch {TRANSPORT[i]}"
    return control


# --------------------------------------------------------------------------- #
# MIDI map
# --------------------------------------------------------------------------- #
LAYER_B_NOTE_OFFSET = 55          # note n (layer A) = n + 55 in layer B
_FADER_CC = (1, 28)               # first CC of fader 1, per layer
_MAIN_FADER_CC = (9, 36)
_ENC_CC = (10, 37)                # 16 consecutive CCs per layer
_TOUCH_CC = (101, 111)            # 8 channel faders, main = +8


def note_in_to_control(note: int) -> tuple[Optional[str], int]:
    """(control, layer) for an incoming note number."""
    layer = 0
    if note >= LAYER_B_NOTE_OFFSET:
        note -= LAYER_B_NOTE_OFFSET
        layer = 1
    if 0 <= note <= 15:
        return f"xt.push:{note}", layer
    if 16 <= note <= 39:
        return f"xt.btn:{note - 16}", layer
    if 40 <= note <= 48:
        return f"xt.ch:{note - 40}", layer
    if 49 <= note <= 54:
        return f"xt.tr:{note - 49}", layer
    return None, layer


def cc_in_to_control(cc: int) -> tuple[Optional[str], str, int]:
    """(control, what, layer) for an incoming CC; what = value | touch."""
    for layer in (0, 1):
        if _FADER_CC[layer] <= cc < _FADER_CC[layer] + 8:
            return f"xt.fader:{cc - _FADER_CC[layer]}", "value", layer
        if cc == _MAIN_FADER_CC[layer]:
            return "xt.fader:8", "value", layer
        if _ENC_CC[layer] <= cc < _ENC_CC[layer] + 16:
            return f"xt.enc:{cc - _ENC_CC[layer]}", "value", layer
        if _TOUCH_CC[layer] <= cc <= _TOUCH_CC[layer] + 8:
            return f"xt.fader:{cc - _TOUCH_CC[layer]}", "touch", layer
    return None, "", 0


def led_note(control: str) -> Optional[int]:
    k, i = kind(control), index(control)
    if k == "btn":
        return i                  # 0-23
    if k == "ch":
        return 24 + i             # 24-31, main 32
    if k == "tr":
        return 33 + i             # 33-38
    return None


RING_SINGLE, RING_PAN, RING_FAN, RING_SPREAD, RING_TRIM = range(5)


def ring_value(raw: int) -> int:
    """0-127 -> ring value 0 (off) .. 13 (all 13 LEDs, fan mode)."""
    raw = max(0, min(127, int(raw)))
    return 0 if raw == 0 else max(1, round(raw * 13 / 127))


# --------------------------------------------------------------------------- #
# device
# --------------------------------------------------------------------------- #
class XTouchCompact:
    """MIDI I/O for the X-Touch Compact in standard mode.

    Callbacks (called on the MIDI thread):
      on_button(control, pressed)   push buttons and encoder pushes
      on_value(control, raw)        faders / encoders, raw 0-127
      on_touch(control, touched)    fader touch sensors
      on_led(control, state)        an LED state was sent (0/1/2)
      on_motor(control, raw)        a fader/ring position was sent
      on_layer_b()                  the user switched to layer B
      on_raw(direction, text)       logging
    """

    MOTOR_HOLD_S = 0.6     # don't move a fader the user moved this recently

    def __init__(self) -> None:
        self.inport = None
        self.outport = None
        self.in_name: Optional[str] = None
        self.out_name: Optional[str] = None
        self.out_channel = 0             # 0 = channels 1 and 2, else 1-16
        self._lock = threading.Lock()
        self.led: dict[str, int] = {}
        self.motor: dict[str, int] = {}
        self.touched: set[str] = set()
        self._user_moved: dict[str, float] = {}
        self.on_button: Optional[Callable[[str, bool], None]] = None
        self.on_value: Optional[Callable[[str, int], None]] = None
        self.on_touch: Optional[Callable[[str, bool], None]] = None
        self.on_led: Optional[Callable[[str, int], None]] = None
        self.on_motor: Optional[Callable[[str, int], None]] = None
        self.on_layer_b: Optional[Callable[[], None]] = None
        self.on_raw: Optional[Callable[[str, str], None]] = None

    # ---------------- connection ----------------
    @property
    def connected(self) -> bool:
        return self.outport is not None or self.inport is not None

    def open(self, in_name: Optional[str], out_name: Optional[str]) -> None:
        self.close()
        if _ports is None:
            raise RuntimeError("mido / python-rtmidi not installed")
        try:
            if in_name:
                self.inport = _ports.open_input(in_name, callback=self._on_midi)
                self.in_name = in_name
            if out_name:
                self.outport = _ports.open_output(out_name)
                self.out_name = out_name
        except Exception:
            self.close()
            raise
        self.init_device()

    def init_device(self) -> None:
        """Standard mode, layer A, encoder rings in 'fan' mode."""
        self._cc(127, 0)
        self._program(0)
        for i in range(16):
            self._cc((10 if i < 8 else 18) + i % 8, RING_FAN)

    def close(self) -> None:
        for p in (self.inport, self.outport):
            try:
                if p is not None:
                    p.close()
            except Exception:
                pass
        self.inport = self.outport = None
        self.in_name = self.out_name = None
        self.touched.clear()

    # ---------------- input ----------------
    def _on_midi(self, msg) -> None:
        if self.on_raw:
            self.on_raw("in", f"X-Touch {msg}")
        layer = 0
        if msg.type in ("note_on", "note_off"):
            ctrl, layer = note_in_to_control(msg.note)
            if ctrl and self.on_button:
                self.on_button(ctrl, msg.type == "note_on" and msg.velocity > 0)
        elif msg.type == "control_change":
            ctrl, what, layer = cc_in_to_control(msg.control)
            if ctrl and what == "touch":
                touched = msg.value >= 64
                (self.touched.add if touched else self.touched.discard)(ctrl)
                if self.on_touch:
                    self.on_touch(ctrl, touched)
            elif ctrl:
                self._user_moved[ctrl] = time.monotonic()
                self.motor[ctrl] = msg.value     # the fader is where the user put it
                if self.on_value:
                    self.on_value(ctrl, msg.value)
        if layer == 1:
            # we only use layer A: switch back and restore LEDs / faders
            self._program(0)
            if self.on_layer_b:
                self.on_layer_b()

    # ---------------- output ----------------
    def _channels(self) -> list[int]:
        return [0, 1] if self.out_channel == 0 else [max(1, min(16, self.out_channel)) - 1]

    def _send(self, msg) -> None:
        if self.on_raw:
            self.on_raw("out", f"X-Touch {msg}")
        if self.outport is None:
            return
        with self._lock:
            try:
                self.outport.send(msg)
            except Exception:
                pass

    def _cc(self, cc: int, value: int) -> None:
        if mido is None:
            return
        for ch in self._channels():
            self._send(mido.Message("control_change", channel=ch, control=cc,
                                    value=max(0, min(127, int(value)))))

    def _program(self, program: int) -> None:
        if mido is None:
            return
        for ch in self._channels():
            self._send(mido.Message("program_change", channel=ch, program=program))

    def set_led(self, control: str, state: int, force: bool = False) -> None:
        """state 0 = off, 1 = on, 2 = blink."""
        note = led_note(control)
        if note is None:
            return
        state = max(0, min(2, int(state)))
        if not force and self.led.get(control) == state:
            return
        self.led[control] = state
        if self.on_led:
            self.on_led(control, state)
        if mido is None:
            return
        for ch in self._channels():
            self._send(mido.Message("note_on", channel=ch, note=note, velocity=state))

    def can_move(self, control: str) -> bool:
        """False while the user touches or just moved this fader / encoder."""
        if control in self.touched:
            return False
        t = self._user_moved.get(control)
        return t is None or time.monotonic() - t > self.MOTOR_HOLD_S

    def set_position(self, control: str, raw: int, force: bool = False) -> bool:
        """Move a motor fader / set an encoder ring. Returns True if sent."""
        k, i = kind(control), index(control)
        if k not in ("fader", "enc"):
            return False
        raw = max(0, min(127, int(raw)))
        if not force and (self.motor.get(control) == raw or not self.can_move(control)):
            return False
        self.motor[control] = raw
        if self.on_motor:
            self.on_motor(control, raw)
        if k == "fader":
            self._cc(1 + i, raw)                       # main fader = CC 9
        else:
            self._cc((26 if i < 8 else 34) + i % 8, ring_value(raw))
        return True

    def resend_all(self) -> None:
        self.init_device()
        for c, s in list(self.led.items()):
            self.set_led(c, s, force=True)
        for c, v in list(self.motor.items()):
            self.set_position(c, v, force=True)

    def clear_all(self) -> None:
        for c in ALL_CONTROLS:
            if has_led(c):
                self.set_led(c, 0)
        for i in range(16):
            self.set_position(f"xt.enc:{i}", 0, force=True)
