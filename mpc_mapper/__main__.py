import os
import sys
import traceback

from PySide6.QtWidgets import QApplication

from .gui import theme
from .gui.main_window import MainWindow


def main() -> int:
    if sys.platform == "win32":
        # Own taskbar entry/icon instead of being grouped under python.exe.
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MPCMapper.MPCMapper")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("MPC Mapper")
    app.setOrganizationName("MPCMapper")
    theme.apply(app)
    w = MainWindow()
    w.fit_to_screen()
    w.show()
    log = os.environ.get("MPC_MAPPER_SELFTEST")
    if log:
        # CI self-test: any uncaught error (also inside Qt callbacks) fails the
        # test; otherwise close again after a few seconds.
        def hook(*exc):
            with open(log, "w", encoding="utf-8") as f:
                traceback.print_exception(*exc, file=f)
            os._exit(5)
        sys.excepthook = hook
        from PySide6.QtCore import QTimer
        QTimer.singleShot(5000, app.quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
