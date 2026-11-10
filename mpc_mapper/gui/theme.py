"""Dark "lighting desk" theme for the whole application.

Fusion style + a dark QPalette carries most widgets; the stylesheet below adds
the finishing touches (cards, buttons, tabs, tree, inputs). Arrow images for
combo/spin boxes are rendered once with QPainter into the cache directory,
because Qt stylesheets can only reference image files.
"""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QPointF, QStandardPaths, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPixmap, QPolygonF
from PySide6.QtWidgets import QApplication

# --------------------------------------------------------------------------- #
# colour tokens
# --------------------------------------------------------------------------- #
BG = "#15171b"          # window background
PANEL = "#1c1f24"       # cards / panels
RAISED = "#252930"      # inputs, buttons
HOVER = "#2e333b"
BORDER = "#323842"
BORDER_STRONG = "#424955"
TEXT = "#e7e9ec"
MUTED = "#8d939d"
FAINT = "#5c626c"
ACCENT = "#3d9bff"      # selection, primary buttons (matches the APC drawing)
ACCENT_HOVER = "#5aabff"
OK = "#3ecf6e"
WARN = "#f0b429"
ERR = "#ef5350"

MOD_KEY = "⌘" if sys.platform == "darwin" else "Ctrl"


def _arrow_dir() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.CacheLocation) or os.path.expanduser("~")
    d = os.path.join(base, "theme")
    os.makedirs(d, exist_ok=True)
    return d


def _arrow(path: str, up: bool, color: str) -> None:
    pm = QPixmap(20, 20)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    pts = [QPointF(5, 13), QPointF(15, 13), QPointF(10, 7)] if up else \
          [QPointF(5, 7), QPointF(15, 7), QPointF(10, 13)]
    p.drawPolygon(QPolygonF(pts))
    p.end()
    pm.save(path, "PNG")


def _arrows() -> dict[str, str]:
    d = _arrow_dir()
    out = {}
    for name, up, col in (("down", False, MUTED), ("up", True, MUTED),
                          ("down_dis", False, FAINT), ("up_dis", True, FAINT)):
        path = os.path.join(d, f"arrow_{name}.png")
        try:
            _arrow(path, up, col)
        except Exception:  # pragma: no cover - cache dir not writable
            pass
        out[name] = path.replace("\\", "/")
    return out


def _palette() -> QPalette:
    pal = QPalette()
    c = QColor
    for role, col in (
        (QPalette.Window, BG), (QPalette.WindowText, TEXT),
        (QPalette.Base, RAISED), (QPalette.AlternateBase, PANEL),
        (QPalette.ToolTipBase, "#2a2f37"), (QPalette.ToolTipText, TEXT),
        (QPalette.PlaceholderText, FAINT),
        (QPalette.Text, TEXT), (QPalette.Button, RAISED), (QPalette.ButtonText, TEXT),
        (QPalette.BrightText, "#ffffff"), (QPalette.Highlight, ACCENT),
        (QPalette.HighlightedText, "#ffffff"), (QPalette.Link, ACCENT),
        (QPalette.Light, HOVER), (QPalette.Midlight, BORDER), (QPalette.Mid, BORDER),
        (QPalette.Dark, "#0e0f12"), (QPalette.Shadow, "#000000"),
    ):
        pal.setColor(role, c(col))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, c(FAINT))
    return pal


def stylesheet(a: dict[str, str]) -> str:
    return f"""
* {{ outline: none; }}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget {{ color: {TEXT}; }}
QToolTip {{ background: #2a2f37; color: {TEXT}; border: 1px solid {BORDER_STRONG};
            padding: 6px 8px; border-radius: 6px; }}

/* ---------- cards ---------- */
QFrame#Card, QWidget#Card {{ background: {PANEL}; border: 1px solid {BORDER};
                             border-radius: 10px; }}
QLabel#SectionTitle {{ color: {MUTED}; font-weight: 600; letter-spacing: 1px; }}
QLabel#Hint {{ color: {MUTED}; }}
QLabel#CardTitle {{ font-weight: 600; }}

QGroupBox {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px;
             margin-top: 22px; padding: 12px 10px 10px 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left;
                    left: 4px; top: 2px; padding: 0 4px; color: {MUTED};
                    font-weight: 600; }}

/* ---------- buttons ---------- */
QPushButton {{ background: {RAISED}; border: 1px solid {BORDER_STRONG}; border-radius: 7px;
               padding: 6px 14px; min-height: 18px; }}
QPushButton:hover {{ background: {HOVER}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: {FAINT}; border-color: {BORDER}; }}
QPushButton#Primary {{ background: {ACCENT}; border: 1px solid {ACCENT}; color: white;
                       font-weight: 600; }}
QPushButton#Primary:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton#Danger {{ background: transparent; border: 1px solid {ERR}; color: {ERR}; }}
QPushButton#Danger:hover {{ background: rgba(239, 83, 80, 0.15); }}
QPushButton#Icon {{ padding: 6px 8px; min-width: 18px; }}
QPushButton#Menu {{ padding-right: 28px; }}
QPushButton#Menu::menu-indicator {{ subcontrol-origin: padding; subcontrol-position: center right;
                                   right: 8px; image: url("{a['down']}"); width: 12px; height: 12px; }}
QWidget#Popup {{ background: {PANEL}; }}
QFrame#Nav {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 9px; }}
QPushButton#Seg {{ background: transparent; border: none; border-radius: 6px;
                   padding: 6px 16px; color: {MUTED}; font-weight: 600; }}
QPushButton#Seg:hover {{ color: {TEXT}; background: {HOVER}; }}
QPushButton#Seg:checked {{ background: {RAISED}; color: {TEXT};
                           border: 1px solid {BORDER_STRONG}; }}

/* ---------- inputs ---------- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextBrowser {{
    background: {RAISED}; border: 1px solid {BORDER_STRONG}; border-radius: 7px;
    padding: 5px 8px; selection-background-color: {ACCENT}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {ACCENT}; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ color: {FAINT}; }}
QPlainTextEdit, QTextBrowser {{ background: {PANEL}; border-radius: 8px; padding: 8px; }}

QComboBox {{ padding-right: 26px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right;
                        width: 24px; border: none; }}
QComboBox::down-arrow {{ image: url("{a['down']}"); width: 14px; height: 14px; }}
QComboBox::down-arrow:disabled {{ image: url("{a['down_dis']}"); }}
QComboBox QAbstractItemView {{ background: {RAISED}; border: 1px solid {BORDER_STRONG};
                               border-radius: 6px; padding: 4px;
                               selection-background-color: {ACCENT}; }}

QSpinBox, QDoubleSpinBox {{ padding-right: 22px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border;
    subcontrol-position: top right; width: 20px; border: none; margin: 2px 2px 0 0; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border;
    subcontrol-position: bottom right; width: 20px; border: none; margin: 0 2px 2px 0; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {HOVER}; border-radius: 4px; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url("{a['up']}"); width: 12px; height: 12px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url("{a['down']}"); width: 12px; height: 12px; }}
QSpinBox#Compact, QSpinBox#Compact:focus {{ padding-right: 8px; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px;
                        border: 1px solid {BORDER_STRONG}; background: {RAISED}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

/* ---------- catalogue tree ---------- */
QTreeView {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px;
             padding: 4px; show-decoration-selected: 1; }}
QTreeView::item {{ padding: 4px 4px; border-radius: 6px; }}
QTreeView::item:hover {{ background: {HOVER}; }}
QTreeView::item:selected {{ background: {ACCENT}; color: white; }}
QTreeView::branch {{ background: transparent; }}

/* ---------- tabs ---------- */
QTabWidget::pane {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px;
                    top: -1px; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 7px 16px;
                margin-right: 2px; border-bottom: 2px solid transparent; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}

/* ---------- toolbar / status / menus ---------- */
QToolBar {{ background: {BG}; border: none; border-bottom: 1px solid {BORDER};
            padding: 8px 10px; spacing: 10px; }}
QStatusBar {{ background: {BG}; border-top: 1px solid {BORDER}; color: {MUTED}; }}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ padding: 2px 10px; }}
QMenuBar {{ background: {BG}; }}
QMenuBar::item:selected {{ background: {HOVER}; border-radius: 4px; }}
QMenu {{ background: {PANEL}; border: 1px solid {BORDER_STRONG}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 5px; }}
QMenu::item:selected {{ background: {ACCENT}; color: white; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}

/* ---------- splitters & scrollbars ---------- */
QSplitter::handle {{ background: {BG}; }}
QSplitter::handle:horizontal {{ width: 8px; }}
QSplitter::handle:vertical {{ height: 8px; }}
QSplitter::handle:hover {{ background: {BORDER}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: {BORDER_STRONG}; border-radius: 4px; min-height: 30px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: {FAINT}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""


def dot(color: str, size: int = 10) -> str:
    """Rich-text status dot."""
    return f"<span style='color:{color}; font-size:{size + 4}px'>●</span>"


def app_icon() -> QIcon:
    """The app icon shipped next to the package (used when running from source)."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for p in (os.path.join(here, "assets", "icon.png"),
              os.path.join(getattr(sys, "_MEIPASS", ""), "mpc_mapper", "assets", "icon.png")):
        if os.path.exists(p):
            return QIcon(p)
    return QIcon()


def apply(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setPalette(_palette())
    f = QFont(app.font())
    if sys.platform != "darwin":   # macOS already uses a good 13 pt system font
        f.setPointSizeF(max(f.pointSizeF(), 9.5))
        app.setFont(f)
    app.setStyleSheet(stylesheet(_arrows()))
    icon = app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
