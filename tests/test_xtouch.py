"""X-Touch Compact support, tested without hardware.

Run with:  QT_QPA_PLATFORM=offscreen python -m pytest -q tests
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

mido = pytest.importorskip("mido")

from mpc_mapper import controls, xtouch  # noqa: E402
from mpc_mapper.xtouch import XTouchCompact, cc_in_to_control, led_note, note_in_to_control  # noqa: E402


# --------------------------------------------------------------------------- #
# MIDI map (Behringer QSG + Modality toolkit)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("note,control,layer", [
    (0, "xt.push:0", 0), (15, "xt.push:15", 0),
    (16, "xt.btn:0", 0), (23, "xt.btn:7", 0), (24, "xt.btn:8", 0), (39, "xt.btn:23", 0),
    (40, "xt.ch:0", 0), (47, "xt.ch:7", 0), (48, "xt.ch:8", 0),
    (49, "xt.tr:0", 0), (54, "xt.tr:5", 0),
    (55, "xtb.push:0", 1), (71, "xtb.btn:0", 1), (95, "xtb.ch:0", 1), (103, "xtb.ch:8", 1),
    (104, "xtb.tr:0", 1), (109, "xtb.tr:5", 1),
])
def test_note_map(note, control, layer):
    assert note_in_to_control(note) == (control, layer)


@pytest.mark.parametrize("cc,control,what,layer", [
    (1, "xt.fader:0", "value", 0), (8, "xt.fader:7", "value", 0), (9, "xt.fader:8", "value", 0),
    (10, "xt.enc:0", "value", 0), (17, "xt.enc:7", "value", 0), (18, "xt.enc:8", "value", 0),
    (25, "xt.enc:15", "value", 0),
    (101, "xt.fader:0", "touch", 0), (108, "xt.fader:7", "touch", 0), (109, "xt.fader:8", "touch", 0),
    (28, "xtb.fader:0", "value", 1), (36, "xtb.fader:8", "value", 1), (37, "xtb.enc:0", "value", 1),
    (52, "xtb.enc:15", "value", 1), (111, "xtb.fader:0", "touch", 1), (119, "xtb.fader:8", "touch", 1),
])
def test_cc_map(cc, control, what, layer):
    assert cc_in_to_control(cc) == (control, what, layer)


def test_pedals_are_ignored():
    for cc in (26, 27, 63, 64):
        assert cc_in_to_control(cc)[0] is None


def test_led_notes():
    assert led_note("xt.btn:0") == 0 and led_note("xt.btn:23") == 23
    assert led_note("xt.ch:0") == 24 and led_note("xt.ch:8") == 32
    assert led_note("xt.tr:0") == 33 and led_note("xt.tr:5") == 38
    assert led_note("xt.push:0") is None and led_note("xt.fader:0") is None


def test_ring_value():
    assert xtouch.ring_value(0) == 0
    assert xtouch.ring_value(1) == 1
    assert xtouch.ring_value(127) == 13
    assert 6 <= xtouch.ring_value(64) <= 7


def test_controls_facade():
    assert len(xtouch.ALL_CONTROLS) == 2 * (9 + 16 + 16 + 24 + 9 + 6)
    assert xtouch.layer("xtb.btn:3") == 1 and xtouch.with_layer("xtb.btn:3", 0) == "xt.btn:3"
    assert led_note("xtb.ch:8") == 32
    assert controls.is_value("xt.fader:3") and controls.is_value("xt.enc:12")
    assert controls.is_button("xt.btn:5") and controls.is_button("xt.push:2")
    assert controls.has_led("xt.tr:1") and not controls.has_led("xt.push:1")
    assert not controls.is_rgb("xt.btn:0") and controls.is_rgb("pad:0")
    assert controls.has_motor("xt.fader:0") and not controls.has_motor("fader:0")
    assert controls.is_value("fader:2") and controls.is_button("pad:3")


# --------------------------------------------------------------------------- #
# device driver with fake ports
# --------------------------------------------------------------------------- #
class FakeOut:
    def __init__(self):
        self.sent = []

    def send(self, msg):
        self.sent.append(msg)

    def close(self):
        pass


class FakeIn:
    def __init__(self, callback):
        self.callback = callback

    def close(self):
        pass


class FakePorts:
    def __init__(self):
        self.out = FakeOut()
        self.inp = None

    def open_input(self, name, callback=None):
        self.inp = FakeIn(callback)
        return self.inp

    def open_output(self, name):
        return self.out


@pytest.fixture
def dev(monkeypatch):
    ports = FakePorts()
    monkeypatch.setattr(xtouch, "_ports", ports)
    d = XTouchCompact()
    d.open("X-TOUCH COMPACT", "X-TOUCH COMPACT")
    d.ports = ports
    return d


def test_init_sets_standard_mode_layer_a_and_ring_mode(dev):
    sent = dev.ports.out.sent
    assert any(m.type == "control_change" and m.control == 127 and m.value == 0 for m in sent)
    assert any(m.type == "program_change" and m.program == 0 for m in sent)
    ring_modes = {m.control for m in sent if m.type == "control_change" and m.value == xtouch.RING_FAN}
    assert set(range(10, 26)) <= ring_modes


def test_default_output_goes_to_channel_1_and_2(dev):
    dev.ports.out.sent.clear()
    dev.set_led("xt.btn:3", 1)
    chans = sorted(m.channel for m in dev.ports.out.sent)
    assert chans == [0, 1]
    assert all(m.type == "note_on" and m.note == 3 and m.velocity == 1 for m in dev.ports.out.sent)


def test_fixed_output_channel(dev):
    dev.out_channel = 5
    dev.ports.out.sent.clear()
    dev.set_led("xt.tr:5", 2)
    assert [(m.channel, m.note, m.velocity) for m in dev.ports.out.sent] == [(4, 38, 2)]


def test_motor_fader_and_ring_messages(dev):
    dev.out_channel = 1
    dev.ports.out.sent.clear()
    assert dev.set_position("xt.fader:0", 100)
    assert dev.set_position("xt.fader:8", 50)
    assert dev.set_position("xt.enc:9", 127)
    got = [(m.control, m.value) for m in dev.ports.out.sent]
    assert got == [(1, 100), (9, 50), (35, 13)]


def test_input_callbacks_and_touch_blocks_motor(dev):
    events = []
    dev.on_button = lambda c, p: events.append(("btn", c, p))
    dev.on_value = lambda c, v: events.append(("val", c, v))
    dev.on_touch = lambda c, t: events.append(("touch", c, t))
    cb = dev.ports.inp.callback
    cb(mido.Message("note_on", note=16, velocity=127))
    cb(mido.Message("note_on", note=16, velocity=0))
    cb(mido.Message("control_change", control=101, value=127))
    cb(mido.Message("control_change", control=1, value=64))
    assert events == [("btn", "xt.btn:0", True), ("btn", "xt.btn:0", False),
                      ("touch", "xt.fader:0", True), ("val", "xt.fader:0", 64)]
    # touched -> motor must not move
    assert not dev.set_position("xt.fader:0", 10)
    cb(mido.Message("control_change", control=101, value=0))
    dev._user_moved["xt.fader:0"] = time.monotonic() - 5
    assert dev.set_position("xt.fader:0", 10)


def test_layer_b_is_its_own_layer(dev):
    layers, events = [], []
    dev.on_layer = lambda lay: layers.append(lay)
    dev.on_button = lambda c, p: events.append((c, p))
    dev.ports.out.sent.clear()
    dev.ports.inp.callback(mido.Message("note_on", note=71, velocity=127))
    assert layers == [1] and dev.active_layer == 1
    assert events == [("xtb.btn:0", True)]
    assert not any(m.type == "program_change" for m in dev.ports.out.sent)   # no forced switch back


def test_only_the_active_layer_reaches_the_unit(dev):
    dev.out_channel = 1
    dev.ports.out.sent.clear()
    dev.set_led("xtb.btn:3", 1)                 # layer B while A is active: remembered only
    dev.set_position("xtb.fader:2", 90)
    assert dev.ports.out.sent == []
    dev.select_layer(1)
    assert [(m.type, m.program) for m in dev.ports.out.sent] == [("program_change", 1)]
    dev.ports.out.sent.clear()
    dev.set_led("xtb.btn:3", 1, force=True)
    dev.set_position("xtb.fader:2", 90, force=True)
    got = [(m.type, getattr(m, "note", getattr(m, "control", None))) for m in dev.ports.out.sent]
    assert got == [("note_on", 3), ("control_change", 3)]


# --------------------------------------------------------------------------- #
# engine: X-Touch -> MA3 and MA3 -> LEDs / motors
# --------------------------------------------------------------------------- #
@pytest.fixture
def engine(monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QCoreApplication
    from mpc_mapper.engine import Engine
    from mpc_mapper.ma3 import ExecState
    from mpc_mapper.model import demo_mapping

    QCoreApplication.instance() or QCoreApplication([])
    ports = FakePorts()
    monkeypatch.setattr(xtouch, "_ports", ports)
    eng = Engine(demo_mapping())
    sent_cmds = []
    eng.ma3.command = lambda text: sent_cmds.append(text)
    eng.ma3.fader = lambda page, ex, v: sent_cmds.append(f"fader {page}.{ex} {v}")
    eng.ma3.key = lambda page, ex, down: sent_cmds.append(f"key {page}.{ex} {int(down)}")
    eng.ma3.current_page = 1
    eng.connect_xtouch("X-TOUCH COMPACT", "X-TOUCH COMPACT")
    eng.ports, eng.cmds, eng.ExecState = ports, sent_cmds, ExecState
    return eng


def test_button_presses_ma3_key(engine):
    engine.handle_button("xt.btn:0", True)       # standard: key of executor 401
    engine.handle_button("xt.btn:0", False)
    assert engine.cmds[-2:] == ["key 1.401 1", "key 1.401 0"]
    engine.handle_button("xt.ch:3", True)        # key under fader 4 = executor 104
    assert engine.cmds[-1] == "key 1.104 1"
    engine.handle_button("xtb.btn:0", True)      # layer B, first key = executor 410
    assert engine.cmds[-1] == "key 1.410 1"


def test_fader_sends_osc_fader(engine):
    engine.handle_fader("xt.fader:2", 127)       # standard: fader of executor 203
    engine._flush_faders()
    assert any(c.startswith("fader 1.203 100") for c in engine.cmds)


def test_feedback_lights_led_and_moves_motor(engine):
    engine.ma3.last_hello_rx = time.time()       # plugin alive
    st = engine.ExecState(1, 201)
    st.active, st.fader = True, 50.0
    engine.ma3.execs[(1, 201)] = st
    engine.ports.out.sent.clear()
    engine._on_exec(st)
    sent = engine.ports.out.sent
    # key 201 (third key row, column 1, LED note 16) lit
    assert any(m.type == "note_on" and m.note == 16 and m.velocity == 1 for m in sent)
    # fader 1 follows the executor master: 50 % -> 64
    assert any(m.type == "control_change" and m.control == 1 and m.value == 64 for m in sent)
    # encoder 1 belongs to executor 401, not 201: its ring must not move
    assert not any(m.type == "control_change" and m.control == 26 for m in sent)


def test_no_motor_move_while_touched(engine):
    engine.ma3.last_hello_rx = time.time()
    engine.xt.touched.add("xt.fader:0")
    st = engine.ExecState(1, 201)
    st.fader = 80.0
    engine.ma3.execs[(1, 201)] = st
    engine.ports.out.sent.clear()
    engine._on_exec(st)
    assert not any(m.type == "control_change" and m.control == 1 for m in engine.ports.out.sent)


def test_saved_mapping_roundtrip(tmp_path):
    from mpc_mapper.model import Mapping, demo_mapping
    m = demo_mapping()
    m.settings.xt_out_channel = 2
    p = tmp_path / "m.json"
    m.save(str(p))
    m2 = Mapping.load(str(p))
    assert m2.settings.xt_out_channel == 2
    assert "xt.fader:3" in m2.assignments and "xt.tr:5" in m2.assignments
    assert m2.assignments["xt.btn:0"].led.on_color == 1     # single-colour LED
    assert "xtb.fader:3" in m2.assignments


# --------------------------------------------------------------------------- #
# standard layouts: like the console, every executor once per device
# --------------------------------------------------------------------------- #
def _executors_per_control(m, dev):
    from mpc_mapper import controls as ctl
    out = {}
    for c, a in m.assignments.items():
        if ctl.device(c) == dev and a.uses_exec():
            out[c] = a.exec
    return out


def test_standard_apc_layout():
    from mpc_mapper.model import Mapping, standard_apc
    m = Mapping()
    standard_apc(m)
    a = m.assignments
    assert [a[f"pad:{56 + i}"].exec for i in range(8)] == list(range(291, 299))   # X1-X8
    assert [a[f"pad:{48 + i}"].exec for i in range(8)] == list(range(191, 199))   # X9-X16
    assert not any(f"pad:{i}" in a for i in range(32, 48))                        # rows 3-4 free
    assert a["pad:24"].exec == 401 and a["pad:16"].exec == 301
    assert a["pad:8"].exec == 201 and a["pad:0"].exec == 101
    assert [a[f"fader:{i}"].exec for i in range(8)] == list(range(201, 209))
    assert a["fader:8"].catalog_id == "master.grand"
    assert not any(c.startswith(("scene", "track")) for c in a)
    keys = [a[c].exec for c in a if not c.startswith("fader:")]
    assert len(keys) == len(set(keys)) == 48
    assert all(a[c].osc_key for c in a if not c.startswith("fader:"))


@pytest.mark.parametrize("p,o,x", [("xt.", 0, 291), ("xtb.", 9, 191)])
def test_standard_xtouch_layout(p, o, x):
    from mpc_mapper.model import Mapping, standard_xtouch
    m = Mapping()
    standard_xtouch(m)
    a = m.assignments
    assert [a[f"{p}enc:{i}"].exec for i in range(8)] == list(range(401 + o, 409 + o))
    assert [a[f"{p}btn:{i}"].exec for i in range(24)] == (
        list(range(401 + o, 409 + o)) + list(range(301 + o, 309 + o)) + list(range(201 + o, 209 + o)))
    assert [a[f"{p}fader:{i}"].exec for i in range(9)] == list(range(201 + o, 210 + o))
    assert [a[f"{p}ch:{i}"].exec for i in range(8)] == list(range(101 + o, 109 + o))
    assert a[f"{p}ch:8"].catalog_id == "xtouch.layer"
    assert [a[f"{p}push:{8 + i}"].exec for i in range(8)] == list(range(x, x + 8))
    assert [a[f"{p}tr:{i}"].catalog_id for i in (0, 1)] == ["page.prev", "page.next"]
    keys = [a[c].exec for c in a if c.startswith(p) and a[c].osc_key]
    assert len(keys) == len(set(keys))


def test_both_layouts_together_keep_each_other():
    from mpc_mapper.model import Mapping, standard_apc, standard_xtouch
    m = Mapping()
    standard_apc(m)
    n_apc = len(m.assignments)
    standard_xtouch(m)
    standard_apc(m)                                  # reloading APC keeps the X-Touch part
    xt = [c for c in m.assignments if c.startswith(("xt.", "xtb."))]
    assert any(c.startswith("xt.") for c in xt) and any(c.startswith("xtb.") for c in xt)
    assert len(m.assignments) - len(xt) == n_apc


# --------------------------------------------------------------------------- #
# grandMA3 connection diagnostics
# --------------------------------------------------------------------------- #
def test_return_test_and_heartbeat_are_told_apart():
    pytest.importorskip("pythonosc")
    from mpc_mapper.ma3 import MA3Link
    m = MA3Link()
    sent = []
    m.command = lambda c: sent.append(c)
    token = m.send_return_test(2)
    assert sent == [f'SendOSC 2 "/apc/hello,s,{token}"']
    m._h_any(("192.168.1.20", 8001), "/gma3/apc/hello", token)
    assert m.diag_ok_at and not m.plugin_alive and m.rx_count == 1
    assert m.last_rx_from == "192.168.1.20:8001"
    assert m.rx_prefix == "gma3"
    m._h_any(("192.168.1.20", 8001), "/gma3/apc/hello", "1.0")
    assert m.plugin_alive and m.plugin_version == "1.0"


def test_udp_round_trip_on_localhost():
    pytest.importorskip("pythonosc")
    import socket as _s
    from pythonosc.udp_client import SimpleUDPClient
    from mpc_mapper.ma3 import MA3Link
    with _s.socket(_s.AF_INET, _s.SOCK_DGRAM) as tmp:
        tmp.bind(("127.0.0.1", 0))
        port = tmp.getsockname()[1]
    m = MA3Link()
    m.start("127.0.0.1", 9, port, "gma3")
    try:
        assert m.listening and not m.bind_error
        SimpleUDPClient("127.0.0.1", port).send_message("/gma3/apc/hello", "1.0")
        for _ in range(50):
            if m.rx_count:
                break
            time.sleep(0.05)
        assert m.rx_count == 1 and m.plugin_alive
    finally:
        m.stop()


def test_busy_port_is_reported():
    pytest.importorskip("pythonosc")
    import socket as _s
    from mpc_mapper.ma3 import MA3Link
    blocker = _s.socket(_s.AF_INET, _s.SOCK_DGRAM)
    blocker.bind(("0.0.0.0", 0))
    port = blocker.getsockname()[1]
    m = MA3Link()
    try:
        with pytest.raises(OSError):
            m.start("127.0.0.1", 9, port, "gma3")
        assert m.bind_error and not m.listening
    finally:
        blocker.close()
        m.stop()


# --------------------------------------------------------------------------- #
# MAIN key switches the layer (the unit's LAYER keys send nothing)
# --------------------------------------------------------------------------- #
def test_main_key_switches_layer(engine):
    import mido
    assert engine.mapping.assignments["xt.ch:8"].catalog_id == "xtouch.layer"
    assert engine.mapping.assignments["xtb.ch:8"].catalog_id == "xtouch.layer"
    layers = []
    engine.layer_changed.connect(layers.append)
    engine.ports.out.sent.clear()
    n = len(engine.cmds)
    # press MAIN on layer A (note 48) -> unit and app go to layer B
    engine.xt._on_midi(mido.Message("note_on", note=48, velocity=127))
    assert engine.xt.active_layer == 1 and layers == [1]
    assert any(m.type == "program_change" and m.program == 1 for m in engine.ports.out.sent)
    assert len(engine.cmds) == n                 # nothing sent to MA3
    # the release still carries the layer-A note: must not switch back
    engine.xt._on_midi(mido.Message("note_off", note=48, velocity=0))
    assert engine.xt.active_layer == 1
    # press MAIN on layer B (note 103) -> back to layer A
    engine.xt._on_midi(mido.Message("note_on", note=103, velocity=127))
    engine.xt._on_midi(mido.Message("note_off", note=103, velocity=0))
    assert engine.xt.active_layer == 0 and layers == [1, 0]


def test_layer_switch_sends_that_layers_fader_values(engine):
    engine.ma3.last_hello_rx = time.time()
    for ex, lvl in ((201, 100.0), (210, 0.0)):
        st = engine.ExecState(1, ex)
        st.fader = lvl
        engine.ma3.execs[(1, ex)] = st
    engine.refresh_motors(force=True)
    engine.ports.out.sent.clear()
    engine.handle_button("xt.ch:8", True)
    cc1 = [m.value for m in engine.ports.out.sent if m.type == "control_change" and m.control == 1]
    assert cc1 and cc1[-1] == 0                  # fader 1 now shows executor 210
