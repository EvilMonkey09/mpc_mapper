"""grandMA3 connection check: step-by-step traffic lights that tell what is
wrong when commands or feedback do not get through.

The key test is the *return test*: the app sends MA3 the command
    SendOSC <line> "/apc/hello,s,diag-xxxx"
over OSC line 1. If that message comes back, MA3 received and executed our
command (line 1 OK) and its answer reached us (line <line>, IP, port and
firewall OK). What is left after that can only be the plugin.
"""
from __future__ import annotations

import sys
import time
from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QPlainTextEdit,
                               QPushButton, QSpinBox, QVBoxLayout, QWidget)

from . import theme
from .widgets import mono_font

OK, WARN, ERR, INFO = "ok", "warn", "err", "info"
_COL = {OK: theme.OK, WARN: theme.WARN, ERR: theme.ERR, INFO: theme.ACCENT}


class MA3Check(QWidget):
    def __init__(self, engine, connect: Callable[[], None], parent=None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.connect_ma3 = connect

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        title = QLabel("CONNECTION CHECK")
        title.setObjectName("SectionTitle")
        lay.addWidget(title)
        hint = QLabel("Finds out why commands or feedback don't get through. "
                      "Connect at the top first, then click Run check.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        row = QHBoxLayout()
        self.run_btn = QPushButton("Run check")
        self.run_btn.setObjectName("Primary")
        self.run_btn.clicked.connect(self.run)
        row.addWidget(self.run_btn)
        self.plugin_btn = QPushButton("Start feedback plugin")
        self.plugin_btn.setToolTip('Sends  Plugin "APC_Feedback"  to MA3')
        self.plugin_btn.clicked.connect(self._start_plugin)
        row.addWidget(self.plugin_btn)
        row.addStretch(1)
        lb = QLabel("Feedback line in MA3")
        lb.setObjectName("Hint")
        row.addWidget(lb)
        self.line = QSpinBox()
        self.line.setRange(1, 99)
        self.line.setValue(2)
        self.line.setToolTip("The OSC line in MA3 that sends feedback to this app "
                             "(OSC_LINE in the plugin, normally 2)")
        row.addWidget(self.line)
        lay.addLayout(row)

        card = QFrame()
        card.setObjectName("Card")
        self.grid = QGridLayout(card)
        self.grid.setContentsMargins(12, 10, 12, 10)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(10)
        self.rows: dict[str, tuple[QLabel, QLabel, QLabel]] = {}
        for i, (key, name) in enumerate([
            ("listen", "1  App listens for feedback"),
            ("ip", "2  IP address to enter in MA3"),
            ("rx", "3  Messages from MA3"),
            ("return", "4  Return test (MA3 answers)"),
            ("plugin", "5  Feedback plugin"),
            ("firewall", "Firewall"),
        ]):
            dot = QLabel()
            dot.setTextFormat(Qt.RichText)
            head = QLabel(name)
            head.setObjectName("CardTitle")
            detail = QLabel()
            detail.setWordWrap(True)
            detail.setTextFormat(Qt.RichText)
            detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.grid.addWidget(dot, i * 2, 0, Qt.AlignTop)
            self.grid.addWidget(head, i * 2, 1)
            self.grid.addWidget(detail, i * 2 + 1, 1)
            self.rows[key] = (dot, head, detail)
        self.grid.setColumnStretch(1, 1)
        lay.addWidget(card)

        lb = QLabel("Last messages received from MA3")
        lb.setObjectName("Hint")
        lay.addWidget(lb)
        self.recent = QPlainTextEdit()
        self.recent.setReadOnly(True)
        self.recent.setFont(mono_font(10 if sys.platform == "darwin" else 8))
        self.recent.setPlaceholderText("Nothing received yet.")
        self.recent.setMinimumHeight(120)
        lay.addWidget(self.recent, 1)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(1000)
        self.refresh()

    # ------------------------------------------------------------------ #
    def _set(self, key: str, state: str, text: str) -> None:
        dot, _head, detail = self.rows[key]
        dot.setText(theme.dot(_COL[state]))
        detail.setText(text)

    def run(self) -> None:
        m = self.engine.ma3
        if not m.listening:
            self.connect_ma3()
        if m.listening and m.client is not None:
            m.send_return_test(self.line.value())
        self.refresh()

    def _start_plugin(self) -> None:
        if not self.engine.ma3.listening:
            self.connect_ma3()
        self.engine.ma3.command('Plugin "APC_Feedback"')

    def refresh(self) -> None:
        if not self.isVisible():
            return
        m = self.engine.ma3
        s = self.engine.mapping.settings
        now = time.time()
        line = self.line.value()

        # 1 listening
        if m.listening:
            self._set("listen", OK, f"Listening on port <b>{m.listen_port}</b> on all network "
                                    "connections of this computer.")
        elif m.bind_error:
            self._set("listen", ERR,
                      f"Port <b>{s.listen_port}</b> is already in use ({m.bind_error}).<br>"
                      "Usually grandMA3 onPC on this computer uses it. Choose another listen "
                      "port under <b>Ports</b> at the top (e.g. 8002), click Connect, and enter "
                      f"the same port on MA3 OSC line {line}.")
        else:
            self._set("listen", WARN, "Not connected yet – click <b>Connect</b> in the "
                                      "grandMA3 box at the top.")

        # 2 IP
        host = s.ma3_host or "127.0.0.1"
        if host.startswith("127.") or host == "localhost":
            self._set("ip", INFO, "grandMA3 runs on this computer: enter <b>127.0.0.1</b> as "
                                  "Destination IP on both OSC lines in MA3.")
        else:
            ip = m.local_ip_for(host)
            if ip:
                self._set("ip", INFO,
                          f"In MA3 (Menu → In &amp; Out → OSC) enter <b>{ip}</b> as Destination "
                          f"IP on line 1 <i>and</i> line {line}. That is this computer's address "
                          f"on the network that reaches the console {host}.")
            else:
                self._set("ip", ERR, f"This computer has no network route to <b>{host}</b>. "
                                     "Check the cable / Wi-Fi and the console IP at the top.")

        # 3 messages
        if m.rx_count:
            ago = now - m.last_any_rx
            self._set("rx", OK if ago < 10 else WARN,
                      f"<b>{m.rx_count}</b> received, the last one {ago:.0f} s ago from "
                      f"<b>{m.last_rx_from}</b>.")
        else:
            self._set("rx", WARN if m.listening else INFO,
                      "Nothing received from MA3 yet. Run the return test (step 4) to find out "
                      "which side is wrong.")

        # 4 return test
        if not m.diag_sent_at:
            self._set("return", INFO, "Not run yet – click <b>Run check</b>.")
        elif m.diag_ok_at:
            self._set("return", OK, "MA3 executed our command and its answer arrived – "
                                    "commands <i>and</i> feedback work.")
        elif now - m.diag_sent_at < 4:
            self._set("return", INFO, "Waiting for MA3's answer …")
        else:
            ip = (m.local_ip_for(host) if not host.startswith("127.") else "127.0.0.1") or "?"
            self._set("return", ERR,
                      "No answer from MA3. Check in MA3 under Menu → In &amp; Out → OSC:<br>"
                      "• <b>Enable Input</b> and <b>Enable Output</b> are on<br>"
                      f"• Line 1: Destination IP <b>{ip}</b>, Port <b>{s.ma3_port}</b>, "
                      f"Prefix <b>{s.osc_prefix}</b>, Receive = Yes, <b>Receive Command = Yes</b><br>"
                      f"• Line {line}: Destination IP <b>{ip}</b>, Port <b>{s.listen_port}</b>, "
                      "Send = Yes, <b>Send Command = Yes</b><br>"
                      "• The console IP at the top is right, both are on the same network<br>"
                      "• The firewall lets MPC Mapper receive (see below)<br>"
                      "If MA3's command line history shows <i>SendOSC …</i>, line 1 works and "
                      f"the problem is line {line}, the IP or the firewall.")

        # 5 plugin
        if m.plugin_alive:
            self._set("plugin", OK, f"Running (version {m.plugin_version}). LEDs and motor "
                                    "faders follow the console.")
        elif m.diag_ok_at:
            self._set("plugin", ERR,
                      "The connection works, but the plugin is not sending. Click <b>Start "
                      "feedback plugin</b> (or run APC_Feedback in MA3's Plugins pool). If it "
                      f"stays red: OSC_LINE at the top of APC_Feedback.lua must be <b>{line}</b>, "
                      "and the plugin must be imported (see Setup help).")
        else:
            self._set("plugin", WARN, "No heartbeat from the plugin yet. Check steps 3 and 4 "
                                      "first.")

        # firewall
        if sys.platform == "win32":
            fw = ("Windows: <i>Windows-Sicherheit → Firewall- &amp; Netzwerkschutz → Zugriff von "
                  "App durch Firewall zulassen</i> → tick MPC Mapper for <b>Private and "
                  "Public</b>. A network set to <i>Public</i> blocks incoming feedback.")
        elif sys.platform == "darwin":
            fw = ("macOS: <i>System Settings → Network → Firewall → Options</i> → MPC Mapper: "
                  "<b>Allow incoming connections</b>.")
        else:
            fw = f"Allow incoming UDP on port {s.listen_port}."
        self._set("firewall", INFO, fw)

        # recent messages
        lines = [f"{t}  {src:<21}  {addr}  {args}" for t, src, addr, args in list(m.recent)]
        text = "\n".join(reversed(lines))
        if text != self.recent.toPlainText():
            self.recent.setPlainText(text)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self.refresh()
