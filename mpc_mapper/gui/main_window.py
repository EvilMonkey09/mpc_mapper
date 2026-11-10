"""Main application window."""
from __future__ import annotations

import copy
import os
import sys
from typing import Optional

from PySide6.QtCore import QSettings, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QAbstractSpinBox, QButtonGroup, QCheckBox, QComboBox, QFileDialog,
                               QGridLayout,
                               QFormLayout, QFrame, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
                               QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter,
                               QStackedWidget, QTextBrowser, QVBoxLayout, QWidget,
                               QWidgetAction)

from .. import apc, controls
from ..engine import Engine
from ..model import (CATALOG_BY_ID, Mapping, assignment_from_catalog, demo_mapping,
                     standard_apc, standard_xtouch)
from .apc_widget import APCWidget
from .xtouch_widget import XTouchWidget
from .catalog import CatalogPanel
from .inspector import Inspector
from .device_test import DeviceTest
from .led_lab import LedLab
from .ma3_check import MA3Check
from . import theme
from .widgets import mono_font

MA3_SETUP_HTML = """
<h3>grandMA3 setup (one time)</h3>
<ol>
<li><b>Menu → In &amp; Out → OSC</b>. Turn on <b>Enable Input</b> and <b>Enable Output</b>.</li>
<li>Line 1 — <i>commands from this app</i>: Destination IP = this computer,
    Port = <b>MA3 port</b> (default 8000), Prefix = <b>gma3</b> (same as the app),
    <b>Receive</b> = Yes, <b>Receive Command</b> = Yes. Fader Range 100.</li>
<li>Line 2 — <i>feedback to this app</i>: Destination IP = this computer,
    Port = <b>Listen port</b> (default 8001), <b>Send</b> = Yes and
    <b>Send Command</b> = Yes, Receive off.<br>
    MA3 uses one port per line for both directions, which is why two lines are
    needed when the app and MA3 run on the same machine.</li>
<li>Import the plugin <code>ma3_plugin/APC_Feedback.xml</code> (+ .lua) into the
    Plugins pool and run it once (or use <i>MA3 → Start feedback plugin</i>).
    It reports executor on/off, fader level and appearance colour, and the
    current page, via <code>SendOSC 2 …</code>. Edit <code>OSC_LINE</code> at the top
    of the Lua file if your feedback line is not line 2.</li>
<li>Press <i>MA3 → Send watch list</i> (done automatically on connect) so the
    plugin knows which executors to report.</li>
</ol>
<p>Status bar shows <b>MA3 ●</b> green when feedback packets arrive.</p>
<h3>APC tips</h3>
<ul>
<li>Shift + Scene 6/7 on the hardware switches the APC into Drum/Note mode — the pads
    then stop sending on the control port. Press Shift + Scene 5 (Session) to get back.</li>
<li>Pad colours: <i>palette</i> (128 fixed colours, can pulse/blink) or <i>true RGB</i>
    via SysEx (static only). "Use MA3 appearance colour" uses true RGB when solid and
    falls back to the nearest palette colour when an animated mode is chosen.</li>
</ul>
"""


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MPC Mapper — APC mini mk2 / X-Touch Compact → grandMA3")
        self.qs = QSettings("MPCMapper", "MPCMapper")
        self.path: Optional[str] = None
        self.dirty = False

        mapping = self._initial_mapping()
        self.mapping = mapping
        self.engine = Engine(mapping, self)

        # ---------------- central widgets ----------------
        self.catalog = CatalogPanel()
        self.diagram = APCWidget(mapping)
        self.diagram.accepts = self.catalog.accepts
        self.inspector = Inspector(mapping)
        self.inspector.setMinimumWidth(320)

        top = QSplitter(Qt.Horizontal)
        top.setChildrenCollapsible(False)
        top.addWidget(self.catalog)
        # middle: switch between the device drawings
        self.xdiagram = XTouchWidget(mapping, layer=0)
        self.xdiagram_b = XTouchWidget(mapping, layer=1)
        for d in (self.xdiagram, self.xdiagram_b):
            d.accepts = self.catalog.accepts
        self.device_stack = QStackedWidget()
        self.device_stack.addWidget(self.diagram)
        self.device_stack.addWidget(self.xdiagram)
        self.device_stack.addWidget(self.xdiagram_b)
        dev_nav = QFrame()
        dev_nav.setObjectName("Nav")
        dl = QHBoxLayout(dev_nav)
        dl.setContentsMargins(4, 4, 4, 4)
        dl.setSpacing(4)
        self.dev_group = QButtonGroup(self)
        for i, (text, tip) in enumerate((
                ("APC mini mk2", ""),
                ("X-Touch · Layer A", "X-Touch Compact, layer A (executors 1-9)"),
                ("X-Touch · Layer B", "X-Touch Compact, layer B (executors 10-18)"))):
            b = QPushButton(text)
            b.setObjectName("Seg")
            b.setCheckable(True)
            if tip:
                b.setToolTip(tip)
            self.dev_group.addButton(b, i)
            dl.addWidget(b)
        self.dev_group.button(0).setChecked(True)
        self.dev_group.idClicked.connect(self._show_device)
        middle = QWidget()
        ml = QVBoxLayout(middle)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(8)
        dev_row = QHBoxLayout()
        dev_row.addStretch(1)
        dev_row.addWidget(dev_nav)
        dev_row.addStretch(1)
        ml.addLayout(dev_row)
        ml.addWidget(self.device_stack, 1)
        top.addWidget(middle)
        # the inspector is tall: scroll instead of being cut off on small screens
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(self.inspector)
        scroll.setMinimumWidth(340)
        top.addWidget(scroll)
        top.setStretchFactor(1, 1)
        top.setSizes([270, 760, 360])

        # ---------------- pages ----------------
        # 1) Mapping: the main workspace, full height
        mapping_page = top

        # 2) LED Lab: own drawing to pick a target + controls column
        self.lab = LedLab(self.engine.apc, lambda: self.lab_diagram.selected_control)
        self.lab_diagram = APCWidget(mapping)
        self.lab_diagram.setAcceptDrops(False)
        self.lab_diagram.selected.connect(self.lab.set_target)
        lab_scroll = QScrollArea()
        lab_scroll.setWidgetResizable(True)
        lab_scroll.setFrameShape(QFrame.NoFrame)
        lab_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lab_scroll.setWidget(self.lab)
        lab_scroll.setMinimumWidth(400)
        lab_scroll.setMaximumWidth(520)
        lab_page = QSplitter(Qt.Horizontal)
        lab_page.setChildrenCollapsible(False)
        lab_page.addWidget(self.lab_diagram)
        lab_page.addWidget(lab_scroll)
        lab_page.setStretchFactor(0, 1)

        # 3) Device test (APC + X-Touch)
        self.device_test = DeviceTest(self.engine)

        # 4) Log
        log_page = self._make_log()

        # 4) Setup help
        help_text = QTextBrowser()
        help_text.setOpenExternalLinks(True)
        help_text.setHtml(MA3_SETUP_HTML)
        self.ma3_check = MA3Check(self.engine, lambda: self._connect_ma3())
        check_scroll = QScrollArea()
        check_scroll.setWidgetResizable(True)
        check_scroll.setFrameShape(QFrame.NoFrame)
        check_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        check_scroll.setWidget(self.ma3_check)
        help_ = QSplitter(Qt.Horizontal)
        help_.setChildrenCollapsible(False)
        help_.addWidget(check_scroll)
        help_.addWidget(help_text)
        help_.setStretchFactor(0, 3)
        help_.setStretchFactor(1, 2)

        self.pages = QStackedWidget()
        for w in (mapping_page, lab_page, self.device_test, log_page, help_):
            self.pages.addWidget(w)
        self.tabs = self.pages          # kept for older code paths / screenshots

        # navigation (segmented buttons)
        nav = QFrame()
        nav.setObjectName("Nav")
        nl = QHBoxLayout(nav)
        nl.setContentsMargins(4, 4, 4, 4)
        nl.setSpacing(4)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        shortcut_mod = "⌘" if sys.platform == "darwin" else "Ctrl"
        for i, (text, tip) in enumerate([
            ("Mapping", "Assign grandMA3 commands to the APC and the X-Touch"),
            ("LED Lab", "Try colours and effects on the real APC"),
            ("Device test", "Check every LED, motor fader and control of your controllers"),
            ("Log", "See every MIDI and OSC message"),
            ("Setup & check", "Check the grandMA3 connection and see how to set it up"),
        ]):
            b = QPushButton(text)
            b.setObjectName("Seg")
            b.setCheckable(True)
            b.setToolTip(f"{tip}  ({shortcut_mod}+{i + 1})")
            b.setShortcut(QKeySequence(f"Ctrl+{i + 1}"))
            self.nav_group.addButton(b, i)
            nl.addWidget(b)
        self.nav_group.button(0).setChecked(True)
        self.nav_group.idClicked.connect(self.pages.setCurrentIndex)
        nav_row = QHBoxLayout()
        nav_row.setContentsMargins(0, 0, 0, 0)
        nav_row.addWidget(nav)
        nav_row.addStretch(1)

        self.hsplit = top
        central = QWidget()
        cl = QVBoxLayout(central)
        cl.setContentsMargins(12, 10, 12, 6)
        cl.setSpacing(10)
        cl.addLayout(nav_row)
        cl.addWidget(self.pages, 1)
        self.setCentralWidget(central)

        self._make_toolbar()
        self._make_menu()
        self._make_status()

        # ---------------- wiring ----------------
        self.engine.led_changed.connect(self.diagram.set_led)
        self.engine.led_changed.connect(self.lab_diagram.set_led)
        self.engine.control_event.connect(self.diagram.hw_event)
        self.engine.control_event.connect(self.lab_diagram.hw_event)
        self.engine.fader_sync.connect(self._fader_sync)
        self.engine.log.connect(self._log)
        self.engine.status_changed.connect(self._update_status)
        self.engine.page_changed.connect(lambda _p: self._update_status())
        self.engine.layer_changed.connect(self._on_xt_layer)
        for xd in (self.xdiagram, self.xdiagram_b):
            self.engine.led_changed.connect(xd.set_led)
            self.engine.control_event.connect(xd.hw_event)
            self.engine.position_changed.connect(xd.hw_event)
            self.engine.touch_changed.connect(xd.set_touch)
        for d in (self.diagram, self.xdiagram, self.xdiagram_b):
            d.selected.connect(self.inspector.set_control)
            d.selected.connect(self._on_select)
            d.catalog_dropped.connect(self._on_catalog_drop)
            d.control_moved.connect(self._on_move)
            d.simulate_button.connect(self.engine.handle_button)
            d.simulate_fader.connect(self.engine.handle_fader)
            d.clear_requested.connect(self._clear)
        self.inspector.changed.connect(self._on_inspector_change)
        self.inspector.cleared.connect(self._clear)
        self.lab.lab_mode_changed.connect(self.engine.set_lab_mode)

        self.engine.refresh_all_leds(force=True)
        QTimer.singleShot(0, self._autoconnect)

    # ------------------------------------------------------------------ #
    # setup helpers
    # ------------------------------------------------------------------ #
    def _initial_mapping(self) -> Mapping:
        last = self.qs.value("last_file", "")
        if last and os.path.exists(last):
            try:
                m = Mapping.load(last)
                self.path = last
                return m
            except Exception as e:
                print(f"MPC Mapper: could not load {last}: {e}")
        return demo_mapping()

    @staticmethod
    def _field(label: str, w: QWidget) -> QWidget:
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        lb = QLabel(label)
        lb.setObjectName("Hint")
        h.addWidget(lb)
        h.addWidget(w)
        return box

    @staticmethod
    def _card(title: str) -> tuple[QFrame, QHBoxLayout, QLabel]:
        card = QFrame()
        card.setObjectName("Card")
        h = QHBoxLayout(card)
        h.setContentsMargins(12, 6, 8, 6)
        h.setSpacing(10)
        dot = QLabel()
        dot.setTextFormat(Qt.RichText)
        h.addWidget(dot)
        t = QLabel(title)
        t.setObjectName("CardTitle")
        h.addWidget(t)
        return card, h, dot

    def _make_toolbar(self) -> None:
        """Connection header: one card for the APC, one for grandMA3.

        A plain widget (not a QToolBar) so nothing is ever hidden behind an
        overflow arrow; the port combos shrink when the window gets narrow.
        """
        s = self.mapping.settings
        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 4)
        hl.setSpacing(10)

        # ---- controllers card: one row per device. Each row has one port
        # combo; the matching output port is picked automatically (same name),
        # which is what both devices use on every platform.
        card = QFrame()
        card.setObjectName("Card")
        grid = QGridLayout(card)
        grid.setContentsMargins(12, 6, 8, 6)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)

        def device_row(row: int, title: str, tip: str):
            dot = QLabel()
            dot.setTextFormat(Qt.RichText)
            name = QLabel(title)
            name.setObjectName("CardTitle")
            cin, cout = QComboBox(), QComboBox()
            cin.setToolTip(tip)
            cin.setMinimumWidth(110)
            cin.setMaximumWidth(260)
            cin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            cin.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            cin.setMinimumContentsLength(10)
            cout.setVisible(False)
            cin.currentIndexChanged.connect(lambda _i, a=cin, b=cout: self._pair_out(a, b))
            btn = QPushButton("Connect")
            btn.setMinimumWidth(100)
            grid.addWidget(dot, row, 0)
            grid.addWidget(name, row, 1)
            grid.addWidget(cin, row, 2)
            grid.addWidget(btn, row, 3)
            return dot, cin, cout, btn

        (self.dot_apc, self.midi_in, self.midi_out,
         self.midi_btn) = device_row(0, "APC mini mk2", "MIDI port of the APC (its \"Control\" port)")
        (self.dot_xt, self.xt_in, self.xt_out,
         self.xt_btn) = device_row(1, "X-Touch Compact", "MIDI port of the X-Touch Compact")
        self.midi_btn.clicked.connect(self._toggle_midi)
        self.xt_btn.clicked.connect(self._toggle_xtouch)
        rb = QPushButton("↻")
        rb.setObjectName("Icon")
        rb.setToolTip("Rescan MIDI ports (after plugging in a controller)")
        rb.clicked.connect(self._scan_ports)
        grid.addWidget(rb, 0, 4, 2, 1)
        grid.setColumnStretch(2, 1)
        hl.addWidget(card, 5)

        # ---- MA3 card
        card, h, self.dot_ma3 = self._card("grandMA3")
        self.host = QLineEdit(s.ma3_host)
        self.host.setPlaceholderText("192.168.1.10")
        self.host.setToolTip("IP address of the grandMA3 console or onPC")
        self.host.setMinimumWidth(110)
        self.host.setMaximumWidth(170)
        self.host.returnPressed.connect(self._connect_ma3)
        h.addWidget(self._field("Console IP", self.host), 1)

        # rarely changed: ports + prefix live in a small popup
        self.port = QSpinBox()
        self.port.setToolTip("OSC port the console receives commands on (OSC line 1)")
        self.listen = QSpinBox()
        self.listen.setToolTip("Port this app listens on for feedback (OSC line 2)")
        for sp, v in ((self.port, s.ma3_port), (self.listen, s.listen_port)):
            sp.setRange(1, 65535)
            sp.setValue(v)
            sp.setButtonSymbols(QAbstractSpinBox.NoButtons)
            sp.setObjectName("Compact")
            sp.setFixedWidth(90)
        self.prefix = QLineEdit(s.osc_prefix)
        self.prefix.setToolTip("OSC prefix set on line 1 in MA3")
        self.prefix.setFixedWidth(90)
        pop = QWidget()
        pop.setObjectName("Popup")
        form = QFormLayout(pop)
        form.setContentsMargins(14, 12, 14, 12)
        form.setSpacing(8)
        title = QLabel("OSC settings")
        title.setObjectName("CardTitle")
        form.addRow(title)
        form.addRow("Send port (line 1)", self.port)
        form.addRow("Listen port (line 2)", self.listen)
        form.addRow("Prefix", self.prefix)
        hint = QLabel("Defaults: 8000 · 8001 · gma3")
        hint.setObjectName("Hint")
        form.addRow(hint)
        menu = QMenu(self)
        wa = QWidgetAction(menu)
        wa.setDefaultWidget(pop)
        menu.addAction(wa)
        self.osc_btn = QPushButton("Ports")
        self.osc_btn.setObjectName("Menu")
        self.osc_btn.setToolTip("OSC ports and prefix")
        self.osc_btn.setMenu(menu)
        h.addWidget(self.osc_btn)

        self.ma3_btn = QPushButton("Connect")
        self.ma3_btn.setObjectName("Primary")
        self.ma3_btn.setMinimumWidth(100)
        self.ma3_btn.clicked.connect(self._connect_ma3)
        h.addWidget(self.ma3_btn)
        hl.addWidget(card, 4)

        self.centralWidget().layout().insertWidget(0, header)
        self._scan_ports()

    def _make_menu(self) -> None:
        mb = self.menuBar()
        f = mb.addMenu("&File")
        for text, key, fn in [
            ("New (empty)", QKeySequence.New, self._new),
            ("Open…", QKeySequence.Open, self._open),
            ("Save", QKeySequence.Save, self._save),
            ("Save as…", QKeySequence.SaveAs, self._save_as),
            (None, None, None),
            ("Quit", QKeySequence.Quit, self.close),
        ]:
            if text is None:
                f.addSeparator()
                continue
            a = QAction(text, self)
            if key is not None:
                a.setShortcut(key)
            a.triggered.connect(fn)
            f.addAction(a)
            if text == "New (empty)":
                std = f.addMenu("Load standard layout (like the MA3 console)")
                for label, which in (("APC mini mk2", "apc"), ("X-Touch Compact", "xtouch"),
                                     ("Both", "both")):
                    sa = QAction(label, self)
                    sa.triggered.connect(lambda _=False, w=which: self._load_standard(w))
                    std.addAction(sa)
        m = mb.addMenu("&MA3")
        for text, fn in [
            ("Send watch list", self.engine.sync_watch_list),
            ("Start feedback plugin", lambda: self.engine.ma3.command('Plugin "APC_Feedback"')),
            ("Send command…", self._send_cmd),
        ]:
            a = QAction(text, self)
            a.triggered.connect(fn)
            m.addAction(a)
        d = mb.addMenu("&Device")
        a = QAction("Re-send all LEDs", self)
        a.triggered.connect(lambda: self.engine.refresh_all_leds(force=True))
        d.addAction(a)
        a = QAction("Sync fader positions (intro SysEx)", self)
        a.triggered.connect(self.engine.apc.send_intro)
        d.addAction(a)

    def _make_status(self) -> None:
        sb = self.statusBar()
        sb.setSizeGripEnabled(False)
        self.st_midi = QLabel()
        self.st_ma3 = QLabel()
        self.st_page = QLabel()
        sb.addWidget(self.st_midi)
        sb.addWidget(self.st_ma3)
        sb.addPermanentWidget(self.st_page)
        self._update_status()

    def _make_log(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        h = QHBoxLayout()
        hint = QLabel("Every message between this app, the controllers (MIDI) and grandMA3 (OSC).")
        hint.setObjectName("Hint")
        h.addWidget(hint, 1)
        self.log_midi = QCheckBox("MIDI")
        self.log_midi.setChecked(False)
        self.log_midi.setToolTip("Show messages to and from the APC and the X-Touch")
        self.log_osc = QCheckBox("OSC")
        self.log_osc.setChecked(True)
        self.log_osc.setToolTip("Show messages to and from grandMA3")
        clear = QPushButton("Clear")
        h.addWidget(self.log_midi)
        h.addWidget(self.log_osc)
        h.addWidget(clear)
        v.addLayout(h)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(3000)
        self.log_view.setFont(mono_font(11 if sys.platform == "darwin" else 9))
        self.log_view.setPlaceholderText("Nothing yet. Press a pad (or Shift+click one on the "
                                         "Mapping page) to see the messages here.")
        clear.clicked.connect(self.log_view.clear)
        v.addWidget(self.log_view)
        return w

    # ------------------------------------------------------------------ #
    # connection
    # ------------------------------------------------------------------ #
    @staticmethod
    def _guess_xtouch(names: list[str]) -> Optional[str]:
        cands = [n for n in names if "touch" in n.lower() and "one" not in n.lower()]
        for n in cands:
            if "compact" in n.lower() and not apc._is_secondary_port(n):
                return n
        return cands[0] if cands else None

    @staticmethod
    def _pair_out(cin: QComboBox, cout: QComboBox) -> None:
        """Pick the output port that belongs to the chosen input port."""
        name = cin.currentData() or ""
        if not name:
            cout.setCurrentIndex(0)
            return
        i = cout.findData(name)
        if i < 0:
            base = apc.port_base_name(name).lower()
            for j in range(cout.count()):
                d = cout.itemData(j) or ""
                if d and apc.port_base_name(d).lower() == base:
                    i = j
                    break
        cout.setCurrentIndex(max(0, i))

    def _scan_ports(self) -> None:
        ins, outs = apc.list_ports()
        s = self.mapping.settings
        xt_names = {self._guess_xtouch(ins), self._guess_xtouch(outs)}
        for combo, names, saved, guess in (
                (self.midi_out, outs, s.midi_out, apc.guess_port),
                (self.midi_in, ins, s.midi_in, apc.guess_port),
                (self.xt_out, outs, s.xt_out, self._guess_xtouch),
                (self.xt_in, ins, s.xt_in, self._guess_xtouch)):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("—", "")
            for n in names:
                combo.addItem(n, n)
            pick = apc.match_port(saved, names) or guess(
                [n for n in names if n not in xt_names] if guess is apc.guess_port else names)
            if pick:
                combo.setCurrentIndex(combo.findData(pick))
            combo.blockSignals(False)
        # output follows input unless a saved output was found
        if not apc.match_port(s.midi_out, outs):
            self._pair_out(self.midi_in, self.midi_out)
        if not apc.match_port(s.xt_out, outs):
            self._pair_out(self.xt_in, self.xt_out)

    def _toggle_xtouch(self) -> None:
        if self.engine.xt.connected:
            self.engine.disconnect_xtouch()
        else:
            try:
                self.engine.connect_xtouch(self.xt_in.currentData(), self.xt_out.currentData())
            except Exception as e:
                hint = ("\n\nA MIDI port can only be used by one program at a time on "
                        "Windows. Close other software using the X-Touch and try again."
                        if sys.platform == "win32" else "")
                QMessageBox.warning(self, "MIDI", f"Could not open the X-Touch:\n{e}{hint}")
        self._update_status()

    def _toggle_midi(self) -> None:
        if self.engine.apc.connected:
            self.engine.disconnect_midi()
        else:
            try:
                self.engine.connect_midi(self.midi_in.currentData(), self.midi_out.currentData())
            except Exception as e:
                hint = ("\n\nOn Windows a MIDI port can only be used by one program at a "
                        "time. Close other software using the APC (DAW, MIDI monitor, "
                        "grandMA3 onPC MIDI input) and try again."
                        if sys.platform == "win32" else "")
                QMessageBox.warning(self, "MIDI", f"Could not open MIDI ports:\n{e}{hint}")
        self._update_status()

    def _connect_ma3(self) -> None:
        s = self.mapping.settings
        s.ma3_host = self.host.text().strip()
        s.ma3_port = self.port.value()
        s.listen_port = self.listen.value()
        s.osc_prefix = self.prefix.text().strip().strip("/")
        try:
            self.engine.connect_ma3()
        except OSError as e:
            QMessageBox.warning(self, "OSC", f"Could not open listen port {s.listen_port}:\n{e}")
            return
        self.engine.sync_watch_list()
        self.ma3_btn.setText("Reconnect")
        self._update_status()

    def _autoconnect(self) -> None:
        if self.midi_in.currentData() or self.midi_out.currentData():
            try:
                self.engine.connect_midi(self.midi_in.currentData(), self.midi_out.currentData())
            except Exception as e:
                self._log("midi", "err", f"auto-connect failed: {e}")
        if self.xt_in.currentData() or self.xt_out.currentData():
            try:
                self.engine.connect_xtouch(self.xt_in.currentData(), self.xt_out.currentData())
            except Exception as e:
                self._log("midi", "err", f"X-Touch auto-connect failed: {e}")
        self._connect_ma3()

    def _update_status(self) -> None:
        a = self.engine.apc
        if a.connected:
            self.dot_apc.setText(theme.dot(theme.OK))
            self.dot_apc.setToolTip("APC connected")
            self.st_midi.setText(f"{theme.dot(theme.OK, 8)} APC connected")
            self.midi_btn.setText("Disconnect")
            self.midi_btn.setObjectName("")
        else:
            self.dot_apc.setText(theme.dot(theme.ERR))
            self.dot_apc.setToolTip("APC not connected")
            self.st_midi.setText(f"{theme.dot(theme.ERR, 8)} APC not connected  "
                                 f"<span style='color:{theme.FAINT}'>· Shift+click the drawing "
                                 "to simulate</span>")
            self.midi_btn.setText("Connect")
            self.midi_btn.setObjectName("Primary")
        x = self.engine.xt
        self.dot_xt.setText(theme.dot(theme.OK if x.connected else theme.FAINT))
        self.dot_xt.setToolTip("X-Touch connected" if x.connected else "X-Touch not connected")
        self.xt_btn.setText("Disconnect" if x.connected else "Connect")
        self.xt_btn.setObjectName("" if x.connected or not self.xt_in.currentData() else "Primary")
        if x.connected:
            self.st_midi.setText(self.st_midi.text() + f"  {theme.dot(theme.OK, 8)} X-Touch")
        for b in (self.midi_btn, self.xt_btn):
            b.style().unpolish(b)
            b.style().polish(b)
        m = self.engine.ma3
        if m.client is None:
            col, text = theme.ERR, "MA3 not connected"
        elif m.plugin_alive:
            col = theme.OK
            text = f"MA3 feedback {('v' + m.plugin_version) if m.plugin_version else ''}"
        else:
            col = theme.WARN
            text = (f"MA3 → {m.host}:{m.port}  <span style='color:{theme.FAINT}'>· no feedback "
                    f"on :{m.listen_port} – open “Setup & check” to find out why</span>")
        self.dot_ma3.setText(theme.dot(col))
        self.dot_ma3.setToolTip("Feedback plugin answers" if col == theme.OK else
                                "Sending commands, no feedback yet" if col == theme.WARN else
                                "Not connected")
        self.st_ma3.setText(f"{theme.dot(col, 8)} {text}")
        self.st_page.setText(f"Page <b>{m.current_page}</b>")
        if hasattr(self, "lab"):
            self.lab.set_target(self.lab_diagram.selected_control)

    def _show_device(self, i: int) -> None:
        self.device_stack.setCurrentIndex(i)
        # showing an X-Touch layer also switches the unit to that layer
        if i in (1, 2) and self.engine.xt.connected and self.engine.xt.active_layer != i - 1:
            self.engine.xt.select_layer(i - 1)

    def _on_xt_layer(self, lay: int) -> None:
        """The X-Touch changed layer: show that layer if an X-Touch page is open."""
        i = 2 if lay else 1
        if self.device_stack.currentIndex() in (1, 2) and self.device_stack.currentIndex() != i:
            self.dev_group.button(i).setChecked(True)
            self.device_stack.setCurrentIndex(i)

    def _on_select(self, control: str) -> None:
        for d in (self.diagram, self.xdiagram, self.xdiagram_b):
            if control not in d.controls() and d.selected_control:
                d.selected_control = None
                d.update()

    def _fader_sync(self, values: list) -> None:
        for i, v in enumerate(values):
            self.diagram.hw_event(f"fader:{i}", v)
            self.lab_diagram.hw_event(f"fader:{i}", v)

    # ------------------------------------------------------------------ #
    # editing
    # ------------------------------------------------------------------ #
    def _changed(self, control: Optional[str] = None, replaced: bool = False) -> None:
        self.dirty = True
        self._title()
        if control:
            if replaced:
                self.engine.assignment_replaced(control)
            else:
                self.engine.update_led(control)
        self.diagram.update()

    def _on_catalog_drop(self, catalog_id: str, control: str) -> None:
        item = CATALOG_BY_ID[catalog_id]
        page, ex = self.catalog.resolve(catalog_id, control)
        self.mapping.assignments[control] = assignment_from_catalog(item, control, page, ex)
        self._changed(control, replaced=True)
        self.engine.sync_watch_list()
        self.inspector.set_control(control)

    def _on_move(self, src: str, dst: str, copy_: bool) -> None:
        a = self.mapping.assignments.get(src)
        if a is None:
            return
        new = copy.deepcopy(a)
        if controls.is_rgb(src) != controls.is_rgb(dst):  # pad <-> single colour button
            new.led.off_color, new.led.on_color = (
                (apc.SINGLE_OFF, apc.SINGLE_ON) if not controls.is_rgb(dst) else (1, 21))
            new.led.off_mode = new.led.on_mode = apc.MODE_SOLID_100
            new.led.use_ma3_color = False
        self.mapping.assignments[dst] = new
        if not copy_:
            del self.mapping.assignments[src]
            self.engine.assignment_replaced(src)
        self._changed(dst, replaced=True)
        self.inspector.set_control(dst)

    def _clear(self, control: str) -> None:
        if self.mapping.assignments.pop(control, None) is not None:
            self._changed(control, replaced=True)
            self.inspector.set_control(control)
            self.engine.sync_watch_list()

    def _on_inspector_change(self, control: str) -> None:
        self._changed(control)
        self._watch_debounce()

    def _watch_debounce(self) -> None:
        if not hasattr(self, "_wd"):
            self._wd = QTimer(self)
            self._wd.setSingleShot(True)
            self._wd.timeout.connect(self.engine.sync_watch_list)
        self._wd.start(800)

    def _send_cmd(self) -> None:
        text, ok = QInputDialog.getText(self, "Send command", "grandMA3 command line:")
        if ok and text:
            self.engine.ma3.command(text)

    def _log(self, src: str, direction: str, text: str) -> None:
        if src == "midi" and not self.log_midi.isChecked():
            return
        if src == "osc" and not self.log_osc.isChecked():
            return
        arrow = {"in": "←", "out": "→"}.get(direction, "!")
        self.log_view.appendPlainText(f"{src.upper():4} {arrow} {text}")

    # ------------------------------------------------------------------ #
    # files
    # ------------------------------------------------------------------ #
    def _title(self) -> None:
        name = os.path.basename(self.path) if self.path else "untitled"
        self.setWindowTitle(f"MPC Mapper — {name}{' *' if self.dirty else ''}")

    def _replace_mapping(self, m: Mapping, path: Optional[str]) -> None:
        # New/demo keep the live connection settings; a loaded file brings its own.
        # The Mapping object itself is shared with engine/widgets, so mutate it.
        self.mapping.assignments = m.assignments
        if path is not None:
            old = self.mapping.settings
            self.mapping.settings = s = m.settings
            self.host.setText(s.ma3_host)
            self.port.setValue(s.ma3_port)
            self.listen.setValue(s.listen_port)
            self.prefix.setText(s.osc_prefix)
            self._scan_ports()
            if (old.ma3_host, old.ma3_port, old.listen_port, old.osc_prefix) != (
                    s.ma3_host, s.ma3_port, s.listen_port, s.osc_prefix):
                self._connect_ma3()
            if (old.midi_in, old.midi_out) != (s.midi_in, s.midi_out) and (s.midi_in or s.midi_out):
                try:
                    self.engine.connect_midi(self.midi_in.currentData(), self.midi_out.currentData())
                except Exception as e:
                    self._log("midi", "err", f"connect failed: {e}")
            if (old.xt_in, old.xt_out) != (s.xt_in, s.xt_out) and (s.xt_in or s.xt_out):
                try:
                    self.engine.connect_xtouch(self.xt_in.currentData(), self.xt_out.currentData())
                except Exception as e:
                    self._log("midi", "err", f"X-Touch connect failed: {e}")
        self.path = path
        self.dirty = False
        self.engine.latched.clear()
        self.engine.mapping_changed()
        self.inspector.set_control(self.diagram.selected_control or self.xdiagram.selected_control
                                   or self.xdiagram_b.selected_control)
        self.diagram.update()
        self._title()

    def _maybe_save(self) -> bool:
        if not self.dirty:
            return True
        r = QMessageBox.question(self, "Unsaved changes", "Save changes to the mapping?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Cancel:
            return False
        if r == QMessageBox.Save:
            return self._save()
        return True

    def _new(self) -> None:
        if self._maybe_save():
            self._replace_mapping(Mapping(), None)

    def _load_standard(self, which: str) -> None:
        """Replace one device's assignments with its console-like standard layout."""
        devs = {"apc": ["apc"], "xtouch": ["xtouch"], "both": ["apc", "xtouch"]}[which]
        names = {"apc": "APC mini mk2", "xtouch": "X-Touch Compact"}
        used = [c for c in self.mapping.assignments if controls.device(c) in devs]
        if used:
            r = QMessageBox.question(
                self, "Load standard layout",
                f"Replace the current {' and '.join(names[d] for d in devs)} assignments "
                "with the standard layout?\n\nIt places the executors like on the grandMA3 "
                "console; every key does what it is set to in MA3.")
            if r != QMessageBox.Yes:
                return
        before = set(self.mapping.assignments)
        if "apc" in devs:
            standard_apc(self.mapping)
        if "xtouch" in devs:
            standard_xtouch(self.mapping)
        for c in before | set(self.mapping.assignments):
            if controls.device(c) in devs:
                self.engine.assignment_replaced(c)
        self.engine.sync_watch_list()
        self.dirty = True
        self._title()
        for d in (self.diagram, self.xdiagram, self.xdiagram_b):
            d.update()
        self.inspector.set_control(self.diagram.selected_control or self.xdiagram.selected_control
                                   or self.xdiagram_b.selected_control)

    def _demo(self) -> None:
        if self._maybe_save():
            self._replace_mapping(demo_mapping(), None)
            self.dirty = True
            self._title()

    def _open(self) -> None:
        if not self._maybe_save():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open mapping", self._dir(), "Mapping (*.json)")
        if path:
            try:
                self._replace_mapping(Mapping.load(path), path)
                self.qs.setValue("last_file", path)
            except Exception as e:
                QMessageBox.warning(self, "Open", f"Could not load {path}:\n{e}")

    def _dir(self) -> str:
        if self.path:
            return os.path.dirname(self.path)
        here = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "mappings")
        if not getattr(sys, "frozen", False) and os.access(here, os.W_OK):
            return here          # running from the source folder
        docs = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) \
            or os.path.expanduser("~")
        d = os.path.join(docs, "MPC Mapper")
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            return docs
        return d

    def _save(self) -> bool:
        if not self.path:
            return self._save_as()
        self._sync_settings()
        try:
            self.mapping.save(self.path)
        except OSError as e:
            QMessageBox.warning(self, "Save", f"Could not save {self.path}:\n{e}")
            return False
        self.qs.setValue("last_file", self.path)
        self.dirty = False
        self._title()
        return True

    def _save_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, "Save mapping",
                                              os.path.join(self._dir(), "mapping.json"),
                                              "Mapping (*.json)")
        if not path:
            return False
        if not path.endswith(".json"):
            path += ".json"
        self.path = path
        return self._save()

    def _sync_settings(self) -> None:
        s = self.mapping.settings
        s.ma3_host = self.host.text().strip()
        s.ma3_port = self.port.value()
        s.listen_port = self.listen.value()
        s.osc_prefix = self.prefix.text().strip().strip("/")
        s.midi_in = self.midi_in.currentData() or ""
        s.midi_out = self.midi_out.currentData() or ""
        s.xt_in = self.xt_in.currentData() or ""
        s.xt_out = self.xt_out.currentData() or ""

    def fit_to_screen(self) -> None:
        """Restore the last window size/position, or pick one that fits the screen."""
        geo = self.qs.value("window_geometry")
        if geo is not None and self.restoreGeometry(geo):
            return
        scr = self.screen().availableGeometry()
        w = min(1450, int(scr.width() * 0.94))
        h = min(950, int(scr.height() * 0.92))
        self.resize(w, h)
        self.move(scr.x() + (scr.width() - w) // 2, scr.y() + (scr.height() - h) // 2)

    def closeEvent(self, e) -> None:
        if not self._maybe_save():
            e.ignore()
            return
        self.qs.setValue("window_geometry", self.saveGeometry())
        self.engine.shutdown()
        e.accept()
