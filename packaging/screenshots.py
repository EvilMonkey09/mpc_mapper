"""Render screenshots of the main window (used by the CI build).

Usage: python packaging/screenshots.py <output folder>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from mpc_mapper.gui import theme  # noqa: E402
from mpc_mapper.gui.main_window import MainWindow  # noqa: E402

out = sys.argv[1] if len(sys.argv) > 1 else "shots"
os.makedirs(out, exist_ok=True)

app = QApplication(sys.argv)
app.setApplicationName("MPC Mapper")
theme.apply(app)
w = MainWindow()
w.resize(1450, 950)
w.show()


def shoot() -> None:
    try:
        _shoot()
    except Exception:
        import traceback
        traceback.print_exc()
        app.exit(1)


def _shoot() -> None:
    w.grab().save(os.path.join(out, "fenster.png"))
    w.diagram.selected_control = "pad:56"
    w.inspector.set_control("pad:56")
    w.diagram.update()
    app.processEvents()
    w.grab().save(os.path.join(out, "auswahl.png"))
    # X-Touch drawing with a selected fader
    w.dev_group.button(1).click()
    w.xdiagram.select("xt.fader:0")
    for i in range(8):
        w.xdiagram.hw_event(f"xt.fader:{i}", 20 + i * 12)
        w.xdiagram.hw_event(f"xt.enc:{i}", 16 * i)
    w.engine.led_changed.emit("xt.btn:0", __import__("mpc_mapper.apc", fromlist=["x"]).LedState(1, 0))
    app.processEvents()
    w.grab().save(os.path.join(out, "xtouch.png"))
    w.dev_group.button(2).click()
    app.processEvents()
    w.grab().save(os.path.join(out, "xtouch-b.png"))
    w.dev_group.button(0).click()
    for i, name in ((1, "led-lab.png"), (2, "geraetetest.png"), (3, "log.png"), (4, "setup.png")):
        w.nav_group.button(i).click()
        if i == 1:
            w.lab_diagram.selected_control = "pad:56"
            w.lab.set_target("pad:56")
            w.lab_diagram.update()
        if i == 2:
            w.device_test.dev_group.button(1).click()
            w.device_test._choose_device(1)
            for c in ("xt.btn:0", "xt.btn:1", "xt.fader:0", "xt.tr:5", "xt.touch:0"):
                w.device_test._mark(c)
        app.processEvents()
        w.grab().save(os.path.join(out, name))
    w.nav_group.button(0).click()
    w.resize(1280, 780)
    app.processEvents()
    w.grab().save(os.path.join(out, "klein.png"))
    w.resize(1024, 680)
    app.processEvents()
    w.grab().save(os.path.join(out, "sehr-klein.png"))
    ms = w.minimumSizeHint()
    print("minimum size hint:", ms.width(), "x", ms.height(),
          "| actual after resize(1024, 680):", w.width(), "x", w.height())
    print("screenshots saved to", out)
    app.quit()


QTimer.singleShot(4000, shoot)
QTimer.singleShot(90000, lambda: (print('timeout'), app.exit(2)))
sys.exit(app.exec())
