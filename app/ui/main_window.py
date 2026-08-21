from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget

from app.ui.sidebar import Sidebar
from app.ui.header import Header
from core.database import Database
from core.data_repository import get_repository
from core.banlist_manager import BanListManager
from core.settings_manager import SettingsManager
from core.meta_analyzer import MetaAnalyzer
from core.update_manager import UpdateManager
from core.deckbuilder import DeckBuilder


class _DataUpdateWorker(QThread):
    """Runs the update check (and, if one is found, the download) off the
    main thread — network I/O only, no Qt widgets touched here, so this is
    safe to run concurrently with the UI."""
    finished_check = Signal(bool)  # True if an update was found and applied

    def __init__(self, updater, parent=None):
        super().__init__(parent)
        self.updater = updater

    def run(self):
        applied = False
        try:
            remote = self.updater.check_data_update()
            if remote:
                applied = self.updater.download_data_update(remote)
        except Exception:
            applied = False
        self.finished_check.emit(applied)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Digimon TCG Lab — Meta Analysis & Personal Ban List Manager")
        self.resize(1440, 900)
        self.setMinimumSize(1180, 700)

        # ---- Core services (shared across pages) ----
        self.db = Database()
        self.repo = get_repository()
        self.banlist = BanListManager(self.db)
        self.settings = SettingsManager()
        self.analyzer = MetaAnalyzer(self.repo)
        self.updater = UpdateManager()
        self.deckbuilder = DeckBuilder(self.db, self.repo, self.banlist)

        central = QWidget()
        central.setObjectName("centralArea")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.page_selected.connect(self.show_page)
        root.addWidget(self.sidebar)

        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(0)

        self.header = Header()
        right_col.addWidget(self.header)

        self.stack = QStackedWidget()
        self.stack.setContentsMargins(0, 0, 0, 0)
        right_col.addWidget(self.stack, 1)

        right_wrap = QWidget()
        right_wrap.setLayout(right_col)
        root.addWidget(right_wrap, 1)

        self.setCentralWidget(central)

        self.pages = {}
        self._page_order = [
            "overview", "meta", "collection", "analysis", "ban_list", "history",
        ]
        self._build_pages()
        self.show_page("overview")

        QTimer.singleShot(300, self._check_online_status)
        QTimer.singleShot(800, self._start_background_data_update_check)

    def _build_pages(self):
        from app.pages.overview import OverviewPage
        from app.pages.ban_list import BanListPage
        from app.pages.collection import CollectionPage
        from app.pages.meta import MetaPage
        from app.pages.analysis import AnalysisPage
        from app.pages.history import HistoryPage

        ctx = dict(
            repo=self.repo, banlist=self.banlist, settings=self.settings,
            analyzer=self.analyzer, db=self.db, updater=self.updater,
            deckbuilder=self.deckbuilder,
        )

        page_classes = {
            "overview": OverviewPage,
            "meta": MetaPage,
            "collection": CollectionPage,
            "analysis": AnalysisPage,
            "ban_list": BanListPage,
            "history": HistoryPage,
        }
        for key, cls in page_classes.items():
            page = cls(**ctx)
            if hasattr(page, "navigate_requested"):
                page.navigate_requested.connect(self.show_page)
            if hasattr(page, "data_updated"):
                page.data_updated.connect(self.refresh_all_pages)
            self.pages[key] = page
            self.stack.addWidget(page)

    def show_page(self, key: str):
        if key not in self.pages:
            return
        page = self.pages[key]
        self.stack.setCurrentWidget(page)
        if hasattr(page, "refresh"):
            page.refresh()
        self.header.set_page(key)
        self.sidebar.set_active(key)
        version = self.repo.version
        self.header.set_last_updated(version.get("meta_version", "--"))

    def _check_online_status(self):
        try:
            online = self.updater.is_online()
        except Exception:
            online = False
        self.header.set_status(online)

    def _start_background_data_update_check(self):
        self._update_worker = _DataUpdateWorker(self.updater, parent=self)
        self._update_worker.finished_check.connect(self._on_background_update_checked)
        self._update_worker.start()

    def _on_background_update_checked(self, applied: bool):
        if applied:
            self.refresh_all_pages()

    def refresh_all_pages(self):
        self.repo.reload()
        for page in self.pages.values():
            if hasattr(page, "refresh"):
                page.refresh()
        self.header.set_last_updated(self.repo.version.get("meta_version", "--"))
