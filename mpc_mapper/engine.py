"""Runtime bridge: controller events -> MA3 actions, MA3 feedback -> LEDs / motor faders."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from . import apc, controls, xtouch
from .apc import APCMini, LedState
from .ma3 import ExecState, MA3Link
from .model import Assignment, Mapping


class Engine(QObject):
    # cross-thread signals (MIDI / OSC threads -> GUI thread)
    _sig_button = Signal(str, bool)
    _sig_fader = Signal(str, int)
    _sig_exec = Signal(object)
    _sig_page = Signal(int)
    _sig_log = Signal(str, str, str)
    _sig_touch = Signal(str, bool)
    _sig_layer = Signal()

    # public signals for the GUI
    led_changed = Signal(str, object)        # control, LedState
    control_event = Signal(str, object)      # control, pressed(bool) / value(int)
    log = Signal(str, str, str)              # source, direction, text
    page_changed = Signal(int)
    status_changed = Signal()
    fader_sync = Signal(list)                # fader positions from intro reply
    position_changed = Signal(str, int)      # motor fader / encoder ring sent (raw 0-127)
    touch_changed = Signal(str, bool)

    def __init__(self, mapping: Mapping, parent=None) -> None:
        super().__init__(parent)
        self.mapping = mapping
        self.apc = APCMini()
        self.xt = xtouch.XTouchCompact()
        self.xt.out_channel = mapping.settings.xt_out_channel
        self.ma3 = MA3Link()
        self.latched: dict[str, bool] = {}
        self.pressed: set[str] = set()
        self.lab_mode = False          # LED lab takes over the LEDs
        self.test_mode = False         # device test: no MA3 output, no LED feedback
        self._pending_fader: dict[str, float] = {}
        self._last_fader: dict[str, float] = {}

        self._sig_button.connect(self.handle_button)
        self._sig_fader.connect(self.handle_fader)
        self._sig_exec.connect(self._on_exec)
        self._sig_page.connect(self._on_page)
        self._sig_log.connect(self.log)
        self._sig_touch.connect(self._on_touch)
        self._sig_layer.connect(lambda: self.refresh_all_leds(force=True))

        self.apc.on_button = lambda c, p: self._sig_button.emit(c, p)
        self.apc.on_fader = lambda c, v: self._sig_fader.emit(c, v)
        self.apc.on_led = lambda c, s: self.led_changed.emit(c, s)
        self.apc.on_raw = lambda d, t: self._sig_log.emit("midi", d, t)
        self.apc.on_fader_sync = lambda vals: self.fader_sync.emit(list(vals))
        self.xt.on_button = lambda c, p: self._sig_button.emit(c, p)
        self.xt.on_value = lambda c, v: self._sig_fader.emit(c, v)
        self.xt.on_touch = lambda c, t: self._sig_touch.emit(c, t)
        self.xt.on_led = lambda c, s: self.led_changed.emit(c, LedState(s, 0))
        self.xt.on_motor = lambda c, v: self.position_changed.emit(c, v)
        self.xt.on_layer_b = lambda: self._sig_layer.emit()
        self.xt.on_raw = lambda d, t: self._sig_log.emit("midi", d, t)
        self.ma3.on_exec = lambda st: self._sig_exec.emit(st)
        self.ma3.on_page = lambda p: self._sig_page.emit(p)
        self.ma3.on_log = lambda d, t: self._sig_log.emit("osc", d, t)

        self._fader_timer = QTimer(self)
        self._fader_timer.timeout.connect(self._flush_faders)
        self._fader_timer.start(int(1000 / max(5.0, mapping.settings.fader_rate_hz)))

        self._watch_timer = QTimer(self)
        self._watch_timer.timeout.connect(self.status_changed)
        self._watch_timer.start(1000)

    # ------------------------------------------------------------------ #
    # connections
    # ------------------------------------------------------------------ #
    def connect_midi(self, in_name: Optional[str], out_name: Optional[str]) -> None:
        self.apc.open(in_name or None, out_name or None)
        self.mapping.settings.midi_in = in_name or ""
        self.mapping.settings.midi_out = out_name or ""
        self.refresh_all_leds(force=True)
        self.status_changed.emit()

    def disconnect_midi(self) -> None:
        self.apc.close()
        self.pressed = {c for c in self.pressed if xtouch.is_xtouch(c)}
        self.status_changed.emit()

    def connect_xtouch(self, in_name: Optional[str], out_name: Optional[str]) -> None:
        self.xt.out_channel = self.mapping.settings.xt_out_channel
        self.xt.open(in_name or None, out_name or None)
        self.mapping.settings.xt_in = in_name or ""
        self.mapping.settings.xt_out = out_name or ""
        self.refresh_all_leds(force=True)
        self.status_changed.emit()

    def disconnect_xtouch(self) -> None:
        self.xt.close()
        self.pressed = {c for c in self.pressed if not xtouch.is_xtouch(c)}
        self.status_changed.emit()

    def connect_ma3(self) -> None:
        s = self.mapping.settings
        self.ma3.start(s.ma3_host, s.ma3_port, s.listen_port, s.osc_prefix)
        self.status_changed.emit()

    def shutdown(self) -> None:
        for dev in (self.apc, self.xt):
            try:
                dev.clear_all()
            except Exception:
                pass
            dev.close()
        self.ma3.stop()

    # ------------------------------------------------------------------ #
    # input handling
    # ------------------------------------------------------------------ #
    @Slot(str, bool)
    def handle_button(self, control: str, pressed: bool) -> None:
        self.control_event.emit(control, pressed)
        if self.test_mode:
            return
        if pressed:
            self.pressed.add(control)
        else:
            self.pressed.discard(control)
        a = self.mapping.assignments.get(control)
        if a is not None:
            page = self.ma3.current_page
            if a.osc_key:
                self.ma3.key(a.eff_page(page), a.exec, pressed)
            else:
                tpl = a.press_cmd if pressed else a.release_cmd
                if tpl:
                    self.ma3.command(a.render(tpl, page))
            if pressed and a.led.source == "latch":
                self.latched[control] = not self.latched.get(control, False)
        if not self.lab_mode:
            self.update_led(control)

    @Slot(str, int)
    def handle_fader(self, control: str, raw: int) -> None:
        self.control_event.emit(control, raw)
        if xtouch.kind(control) == "enc":
            self.xt.set_position(control, raw, force=True)   # ring shows the turn
        if self.test_mode:
            return
        value = round(raw * 100.0 / 127.0, 1)
        last = self._pending_fader.get(control, self._last_fader.get(control))
        db = self.mapping.settings.fader_deadband
        if last is not None and db and abs(value - last) < db and raw not in (0, 127):
            return
        self._pending_fader[control] = value

    def _flush_faders(self) -> None:
        if not self._pending_fader:
            return
        pending, self._pending_fader = self._pending_fader, {}
        page = self.ma3.current_page
        for control, value in pending.items():
            self._last_fader[control] = value
            a = self.mapping.assignments.get(control)
            if a is None:
                continue
            try:
                if a.osc_fader:
                    self.ma3.fader(a.eff_page(page), a.exec, value)
                elif a.value_cmd:
                    self.ma3.command(a.render(a.value_cmd, page, value))
            except Exception as e:  # never lose the other faders of this tick
                self.log.emit("osc", "err", f"{control}: {e}")

    # ------------------------------------------------------------------ #
    # feedback
    # ------------------------------------------------------------------ #
    @Slot(object)
    def _on_exec(self, st: ExecState) -> None:
        if self.lab_mode:
            return
        page = self.ma3.current_page
        for control, a in self.mapping.assignments.items():
            if a.eff_page(page) == st.page and a.exec == st.exec:
                self.update_led(control)
                self.update_motor(control)
        self.status_changed.emit()

    @Slot(str, bool)
    def _on_touch(self, control: str, touched: bool) -> None:
        self.touch_changed.emit(control, touched)
        if not touched:
            # fader released: go to the console value if it differs
            QTimer.singleShot(int(xtouch.XTouchCompact.MOTOR_HOLD_S * 1000) + 50,
                              lambda: self.update_motor(control))

    @staticmethod
    def follows_ma3(a: Assignment) -> bool:
        """Only the executor master level is reported by the MA3 plugin."""
        return a.uses_exec() and (a.osc_fader or "FaderMaster" in a.value_cmd)

    def update_motor(self, control: str, force: bool = False) -> None:
        """Move a motor fader / encoder ring to the executor level in MA3."""
        if (self.test_mode or not controls.has_motor(control)
                or not self.mapping.settings.xt_follow):
            return
        a = self.mapping.assignments.get(control)
        if a is None or not self.follows_ma3(a):
            return
        st = self.ma3.state(a.eff_page(self.ma3.current_page), a.exec)
        if not self.ma3.plugin_alive:
            return
        self.xt.set_position(control, round(st.fader * 127 / 100), force=force)

    def refresh_motors(self, force: bool = False) -> None:
        for c in xtouch.ALL_CONTROLS:
            self.update_motor(c, force=force)

    @Slot(int)
    def _on_page(self, page: int) -> None:
        self.page_changed.emit(page)
        if not self.lab_mode:
            self.refresh_all_leds()
        self.refresh_motors()

    def is_on(self, control: str, a: Assignment) -> bool:
        src = a.led.source
        page = self.ma3.current_page
        if src == "press":
            return control in self.pressed
        if src == "latch":
            return self.latched.get(control, False)
        if src == "exec_active":
            return self.ma3.state(a.eff_page(page), a.exec).active
        if src == "exec_fader":
            return self.ma3.state(a.eff_page(page), a.exec).fader > 0.5
        if src == "page":
            return page == (a.page or 1)
        return False

    def compute_led(self, control: str) -> LedState:
        a = self.mapping.assignments.get(control)
        rgb_pad = controls.is_rgb(control)
        if a is None:
            return LedState(0, apc.MODE_SOLID_100 if rgb_pad else 0)
        on = self.is_on(control, a)
        cfg = a.led
        if rgb_pad and cfg.use_ma3_color:
            st = self.ma3.state(a.eff_page(self.ma3.current_page), a.exec)
            if st.rgb is not None:
                if on:
                    if cfg.on_mode == apc.MODE_SOLID_100:
                        return LedState(rgb=st.rgb)
                    # animated: SysEx can't blink, use nearest palette colour
                    return LedState(apc.nearest_palette_index(st.rgb), cfg.on_mode)
                dim = tuple(int(c * cfg.ma3_dim) for c in st.rgb)
                return LedState(rgb=dim)  # type: ignore[arg-type]
        if on:
            return LedState(cfg.on_color, cfg.on_mode if rgb_pad else 0)
        return LedState(cfg.off_color, cfg.off_mode if rgb_pad else 0)

    def update_led(self, control: str, force: bool = False) -> None:
        if self.test_mode:
            return
        if xtouch.is_xtouch(control):
            # the LED lab is for the APC; X-Touch LEDs always show the state
            if xtouch.has_led(control):
                self.xt.set_led(control, self.compute_led(control).color, force=force)
            return
        if self.lab_mode:
            return
        if apc.is_button(control):
            self.apc.set_led(control, self.compute_led(control), force=force)

    def refresh_all_leds(self, force: bool = False) -> None:
        for c in controls.ALL_CONTROLS:
            self.update_led(c, force=force)
        self.refresh_motors(force=force)

    def set_test_mode(self, on: bool) -> None:
        self.test_mode = on
        if not on:
            self.refresh_all_leds(force=True)

    def set_lab_mode(self, on: bool) -> None:
        self.lab_mode = on
        if not on:
            self.refresh_all_leds(force=True)

    def apply_settings(self) -> None:
        self._fader_timer.setInterval(int(1000 / max(5.0, self.mapping.settings.fader_rate_hz)))

    def assignment_replaced(self, control: str) -> None:
        self.latched.pop(control, None)
        self.update_led(control)
        self.update_motor(control, force=True)

    def mapping_changed(self) -> None:
        self.apply_settings()
        self.refresh_all_leds()
        self.sync_watch_list()

    def sync_watch_list(self) -> None:
        """Tell the MA3 plugin which executors to report (page 0 = current)."""
        items = sorted({(a.page, a.exec) for a in self.mapping.assignments.values()
                        if a.uses_exec()})
        text = " ".join(f"{p}.{e}" for p, e in items)
        self.ma3.command(f'SetUserVariable "APC_WATCH" "{text}"')
