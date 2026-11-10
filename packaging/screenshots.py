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
    w.grab().save(os.path.join(out, "fenster.png"))
    w.diagram.selected_control = "pad:56"
    w.inspector.set_control("pad:56")
    w.diagram.update()
    w.tabs.setCurrentIndex(w.tabs.indexOf(w.lab))
    app.processEvents()
    w.grab().save(os.path.join(out, "auswahl.png"))
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
sys.exit(app.exec())
