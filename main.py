"""Digimon TCG Lab — entrypoint.

Local-first desktop app: no server, no login, no per-user account system.
Each installation keeps its own SQLite database under %LOCALAPPDATA%.
"""
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from core.paths import USER_DB_PATH, USER_SETTINGS_PATH, ensure_app_data_seeded, APP_ASSETS_DIR


def _is_first_run() -> bool:
    return not USER_DB_PATH.exists() and not USER_SETTINGS_PATH.exists()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Digimon TCG Lab")
    app.setOrganizationName("DigimonTCGLab")

    icon_path = APP_ASSETS_DIR / "app_icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    style_path = APP_ASSETS_DIR / "style.qss"
    if style_path.exists():
        app.setStyleSheet(style_path.read_text(encoding="utf-8"))

    first_run = _is_first_run()

    if first_run:
        from app.ui.splash import FirstRunDialog
        splash = FirstRunDialog()
        splash.show()
        app.processEvents()

        def step1():
            ensure_app_data_seeded()
            splash.mark_done(2)
            QTimer.singleShot(200, step2)

        def step2():
            from core.database import Database
            Database()
            splash.mark_done(0)
            QTimer.singleShot(200, step3)

        def step3():
            from core.settings_manager import SettingsManager
            s = SettingsManager()
            s.set("first_run_complete", True)
            splash.mark_done(1)
            splash.finish()

        QTimer.singleShot(150, step1)
        if splash.exec() == splash.DialogCode.Rejected:
            sys.exit(0)
    else:
        ensure_app_data_seeded()

    from app.ui.main_window import MainWindow
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
