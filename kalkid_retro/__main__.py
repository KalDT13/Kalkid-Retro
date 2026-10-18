"""Point d'entrée : python -m kalkid_retro"""

from __future__ import annotations

import sys

from PySide6.QtCore import QLockFile, QDir
from PySide6.QtWidgets import QApplication, QMessageBox

from . import APP_NAME
from .config import Config
from .controller import Controller
from .theme import STYLESHEET, make_icon
from .ui import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLESHEET)
    app.setWindowIcon(make_icon())

    # une seule instance à la fois (sinon les raccourcis seraient interceptés deux fois)
    lock = QLockFile(QDir.temp().filePath("kalkid_retro.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None, APP_NAME, "Kalkid Rétro est déjà lancé (voir la zone de notification).")
        return 0

    config = Config()
    controller = Controller(config)
    window = MainWindow(controller)
    controller.start()

    hidden = "--hidden" in sys.argv or config.get("settings", "start_hidden", default=False)
    if not hidden:
        window.show()

    code = app.exec()
    controller.shutdown()
    lock.unlock()
    return code


if __name__ == "__main__":
    sys.exit(main())
