from PySide6.QtCore import Qt, Signal, QSize, QTimer, QPoint
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, QComboBox,
    QScrollArea, QFrame, QLabel, QPushButton, QSplitter, QProgressBar,
    QInputDialog, QMessageBox
)

from app.components.card_widget import CardWidget, color_hex, CARD_COLOR_HEX
from app.components.image_loader import load_card_pixmap
from app.components.card_detail_dialog import CardDetailDialog
from app.components.card_hover_popup import get_hover_popup
from app.components.metric_bar import MetricInline, INDICATOR_FIELDS
from core.deckbuilder import MAIN_DECK_SIZE, DIGI_EGG_DECK_MAX
from core.banlist_manager import RESTRICTION_META

COLS_TARGET_WIDTH = 232
IMAGE_BATCH_SIZE = 40
WIDGET_BATCH_SIZE = 60
PAGE_SIZE = 120  # caps how many tiles are ever live at once, regardless of catalog size
SEARCH_DEBOUNCE_MS = 250
LEVEL_COLUMN_WIDTH = 176
DECK_TILE_IMG = QSize(74, 104)
STATUS_META = {
    "LEGAL": ("✅ Válido", "#22C55E"),
    "INCOMPLETO": ("⚠ Incomplete", "#EAB308"),
    "ILEGAL": ("❌ Ilegal", "#EF4444"),
}

# Official Digimon TCG card colors — same hex map CardWidget uses for its
# borders/dots, reused here for the filter chips so both stay visually
# consistent with a single source of truth (app.components.card_widget).
COLOR_CHIPS = [(name, hex_code) for name, hex_code in CARD_COLOR_HEX.items() if name != "Colorless"]

# Curated from the real printed effect text (main_effect/source_effect/
# alt_effect) already collected from digimoncard.io — these are literal
# substrings that appear on cards using them, not invented tags. A card
# matches a chip if the tag text appears anywhere in its effect text.
KEYWORD_CHIPS = [
    "Blocker", "On Play", "When Attacking", "Security",
    "DNA Digivolve", "Burst Digivolve", "Piercing", "Rush",
]

# Deck Builder columns, grouped by level curve. Each entry is
# (id, header, sublabel, predicate over a card dict) — level/type are the
# same real fields the catalog filters already use, nothing new.
LEVEL_COLUMNS = [
    ("egg", "Lv.2", "Digi-Egg", lambda c: c.get("type") == "Digi-Egg"),
    ("lv3", "Lv.3", "Rookie", lambda c: c.get("level") == 3),
    ("lv4", "Lv.4", "Champion", lambda c: c.get("level") == 4),
    ("lv5", "Lv.5", "Ultimate", lambda c: c.get("level") == 5),
    ("lv67", "Lv.6/7", "Mega", lambda c: c.get("level") in (6, 7)),
    ("tamer", "Tamers", "", lambda c: c.get("type") == "Tamer"),
    ("option", "Options", "", lambda c: c.get("type") == "Option"),
]
LEVEL_COLUMN_FALLBACK = ("other", "Outros", "", lambda c: True)
LEVEL_COLUMN_COLORS = {
    "egg": "#FBC02D", "lv3": "#43A047", "lv4": "#1E88E5", "lv5": "#8E44AD",
    "lv67": "#E53935", "tamer": "#F97316", "option": "#94A3B8", "other": "#475569",
}


class CollectionPage(QWidget):
    """Digimon TCG Deck Building Workspace: a vertical stack of

        DECK HEADER  (name / counts / progress bar / save state)
        DECK BUILDER (level-curve columns — the visual priority of the page)
        CATALOG      (search, color/effect filters, card grid)

    Edits to the active deck live in memory only (self._working_cards) until
    the user clicks Salvar — nothing touches the database until then."""

    navigate_requested = Signal(str)

    def __init__(self, repo, banlist, settings, analyzer, db, updater, collection=None, deckbuilder=None, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.banlist = banlist
        self.settings = settings
        self.deckbuilder = deckbuilder
        self.current_deck_id = None
        self.selected_card_id = None

        self._working_deck_id = None
        self._working_cards = {}  # card_id -> copies, in-memory only until Save
        self._dirty = False

        self._populated_filters = False
        self._filtered_results = []
        self._current_page = 0
        self._widgets = {}  # card_id -> CardWidget
        self._current_cols = 0
        self._image_queue = []
        self._build_queue = []
        self._build_index = 0
        self._build_generation = 0
        self._active_colors = set()
        self._active_keywords = set()

        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(SEARCH_DEBOUNCE_MS)
        self._search_debounce.timeout.connect(self._apply_filters)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(12)

        outer.addWidget(self._build_deck_header())

        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        outer.addWidget(splitter, 1)
        splitter.addWidget(self._build_deck_builder_section())
        splitter.addWidget(self._build_catalog_section())
        splitter.setSizes([380, 620])

    # ==================================================================
    # DECK HEADER
    # ==================================================================
    def _build_deck_header(self):
        box = QFrame()
        box.setObjectName("surface")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        row1 = QHBoxLayout()
        row1.setSpacing(16)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        eyebrow = QLabel("DECK BUILDING WORKSPACE")
        eyebrow.setObjectName("workspaceEyebrow")
        title_col.addWidget(eyebrow)
        self.deck_combo = QComboBox()
        self.deck_combo.setObjectName("deckNameCombo")
        self.deck_combo.setMinimumWidth(280)
        self.deck_combo.currentIndexChanged.connect(self._on_deck_combo_changed)
        title_col.addWidget(self.deck_combo)
        row1.addLayout(title_col)
        row1.addStretch()

        new_btn = QPushButton("+ Novo")
        new_btn.setObjectName("ghostButton")
        new_btn.clicked.connect(self._create_deck)
        row1.addWidget(new_btn)
        rename_btn = QPushButton("Renomear")
        rename_btn.setObjectName("ghostButton")
        rename_btn.clicked.connect(self._rename_deck)
        row1.addWidget(rename_btn)
        delete_btn = QPushButton("Excluir")
        delete_btn.setObjectName("ghostButton")
        delete_btn.setProperty("danger", True)
        delete_btn.clicked.connect(self._delete_deck)
        row1.addWidget(delete_btn)
        self.save_btn = QPushButton("💾  SALVAR")
        self.save_btn.setObjectName("primaryButton")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._save_deck)
        row1.addWidget(self.save_btn)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(16)

        self.deck_progress = QProgressBar()
        self.deck_progress.setObjectName("deckProgress")
        self.deck_progress.setRange(0, MAIN_DECK_SIZE)
        self.deck_progress.setValue(0)
        self.deck_progress.setTextVisible(False)
        row2.addWidget(self.deck_progress, 1)

        self.counts_label = QLabel("Nenhum deck selecionado")
        self.counts_label.setObjectName("deckHeaderStat")
        row2.addWidget(self.counts_label)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-weight: 800; font-size: 12px;")
        row2.addWidget(self.status_label)

        self.unsaved_label = QLabel("")
        self.unsaved_label.setStyleSheet("color: #F97316; font-weight: 700; font-size: 11px;")
        row2.addWidget(self.unsaved_label)
        layout.addLayout(row2)

        return box

    # ==================================================================
    # DECK BUILDER (level curve — the visual priority of the page)
    # ==================================================================
    def _build_deck_builder_section(self):
        panel = QFrame()
        panel.setObjectName("surface")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        header_row = QHBoxLayout()
        title = QLabel("DECK BUILDER")
        title.setObjectName("workspaceSectionTitle")
        header_row.addWidget(title)
        header_row.addStretch()
        self.issues_label = QLabel("")
        self.issues_label.setStyleSheet("color: #F97316; font-size: 11px; font-weight: 600;")
        self.issues_label.setAlignment(Qt.AlignRight)
        header_row.addWidget(self.issues_label)
        layout.addLayout(header_row)

        self.curve_row = QHBoxLayout()
        self.curve_row.setSpacing(10)
        layout.addLayout(self.curve_row)

        columns_scroll = QScrollArea()
        columns_scroll.setWidgetResizable(True)
        columns_scroll.setFrameShape(QFrame.NoFrame)
        columns_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        columns_inner = QWidget()
        self.deck_columns_layout = QHBoxLayout(columns_inner)
        self.deck_columns_layout.setContentsMargins(0, 0, 0, 0)
        self.deck_columns_layout.setSpacing(10)
        self.deck_columns_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        columns_scroll.setWidget(columns_inner)
        layout.addWidget(columns_scroll, 1)

        return panel

    def _build_deck_level_column(self, header, sublabel, count, accent="#475569"):
        col = QFrame()
        col.setObjectName("levelColumn")
        col.setFixedWidth(LEVEL_COLUMN_WIDTH)
        outer_layout = QVBoxLayout(col)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        accent_bar = QFrame()
        accent_bar.setFixedHeight(3)
        accent_bar.setStyleSheet(f"background-color: {accent}; border: none;")
        outer_layout.addWidget(accent_bar)

        col_layout = QVBoxLayout()
        col_layout.setContentsMargins(10, 10, 10, 10)
        col_layout.setSpacing(6)
        outer_layout.addLayout(col_layout)

        top_row = QHBoxLayout()
        h = QLabel(header)
        h.setObjectName("levelColumnHeader")
        top_row.addWidget(h)
        top_row.addStretch()
        count_lbl = QLabel(str(count))
        count_lbl.setStyleSheet(f"color: {accent}; font-weight: 800; font-size: 15px;")
        top_row.addWidget(count_lbl)
        col_layout.addLayout(top_row)

        if sublabel:
            sub = QLabel(sublabel.upper())
            sub.setObjectName("sectionHint")
            col_layout.addWidget(sub)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        tiles_layout = QGridLayout(inner)
        tiles_layout.setContentsMargins(0, 4, 0, 0)
        tiles_layout.setSpacing(6)
        tiles_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(inner)
        col_layout.addWidget(scroll, 1)

        return col, tiles_layout

    def _build_curve_block(self, header, count, max_count, color):
        block = QFrame()
        block.setFixedWidth(112)
        block_layout = QVBoxLayout(block)
        block_layout.setContentsMargins(0, 0, 0, 0)
        block_layout.setSpacing(3)

        top = QHBoxLayout()
        top.setSpacing(4)
        h = QLabel(header)
        h.setObjectName("curveColumnLabel")
        top.addWidget(h)
        top.addStretch()
        c = QLabel(str(count))
        c.setObjectName("curveColumnCount")
        top.addWidget(c)
        block_layout.addLayout(top)

        bar_bg = QFrame()
        bar_bg.setFixedHeight(6)
        bar_bg.setStyleSheet("background-color: #1B2A3A; border-radius: 3px;")
        bar_fill_layout = QHBoxLayout(bar_bg)
        bar_fill_layout.setContentsMargins(0, 0, 0, 0)
        bar_fill_layout.setSpacing(0)
        pct = int(max(1, count) / max(1, max_count) * 100) if count else 0
        fill = QFrame()
        fill.setStyleSheet(f"background-color: {color}; border-radius: 3px;")
        bar_fill_layout.addWidget(fill, max(pct, 1) if count else 0)
        bar_fill_layout.addStretch(max(1, 100 - pct))
        block_layout.addWidget(bar_bg)

        return block

    # ==================================================================
    # CATALOG
    # ==================================================================
    def _build_catalog_section(self):
        panel = QFrame()
        panel.setObjectName("surface")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        header_row = QHBoxLayout()
        title = QLabel("CATALOG")
        title.setObjectName("workspaceSectionTitle")
        header_row.addWidget(title)
        header_row.addStretch()
        layout.addLayout(header_row)

        layout.addWidget(self._build_selected_card_row())

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setObjectName("catalogSearch")
        self.search.setPlaceholderText("🔍  Buscar carta por nome ou código...")
        self.search.textChanged.connect(lambda: self._search_debounce.start())
        toolbar.addWidget(self.search, 2)

        self.set_filter = self._make_combo("Set")
        self.type_filter = self._make_combo("Tipo")
        self.rarity_filter = self._make_combo("Raridade")
        self.level_filter = self._make_combo("Level")
        for combo in [self.set_filter, self.type_filter, self.rarity_filter, self.level_filter]:
            toolbar.addWidget(combo)
        layout.addLayout(toolbar)

        layout.addWidget(self._build_color_chip_row())
        layout.addWidget(self._build_keyword_chip_row())

        result_row = QHBoxLayout()
        self.result_label = QLabel("")
        self.result_label.setStyleSheet("color: #64748B; font-size: 11px;")
        result_row.addWidget(self.result_label)
        result_row.addStretch()

        self.prev_page_btn = QPushButton("◀")
        self.prev_page_btn.setFixedWidth(32)
        self.prev_page_btn.clicked.connect(self._go_prev_page)
        result_row.addWidget(self.prev_page_btn)

        self.page_label = QLabel("")
        self.page_label.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600;")
        self.page_label.setAlignment(Qt.AlignCenter)
        self.page_label.setFixedWidth(110)
        result_row.addWidget(self.page_label)

        self.next_page_btn = QPushButton("▶")
        self.next_page_btn.setFixedWidth(32)
        self.next_page_btn.clicked.connect(self._go_next_page)
        result_row.addWidget(self.next_page_btn)

        layout.addLayout(result_row)

        self.catalog_scroll = QScrollArea()
        self.catalog_scroll.setWidgetResizable(True)
        self.catalog_scroll.setFrameShape(QFrame.NoFrame)
        self.grid_content = QWidget()
        self.grid = QGridLayout(self.grid_content)
        self.grid.setSpacing(14)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.catalog_scroll.setWidget(self.grid_content)
        layout.addWidget(self.catalog_scroll, 1)

        return panel

    # ---------- Selected-card row: a single slim line, no box of its own —
    # full detail lives in the hover popup; this is just enough to see what's
    # selected and adjust/inspect it without losing catalog real estate. ----------
    def _build_selected_card_row(self):
        row = QWidget()
        row.setFixedHeight(30)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.strip_name = QLabel("Nenhuma carta selecionada")
        self.strip_name.setObjectName("selectedCardLabel")
        layout.addWidget(self.strip_name)

        self.strip_meta = QLabel("")
        self.strip_meta.setObjectName("sectionHint")
        layout.addWidget(self.strip_meta)

        self.strip_restriction = QLabel("")
        layout.addWidget(self.strip_restriction)

        self.strip_indicators_box = QWidget()
        self.strip_indicators_layout = QHBoxLayout(self.strip_indicators_box)
        self.strip_indicators_layout.setContentsMargins(0, 0, 0, 0)
        self.strip_indicators_layout.setSpacing(12)
        layout.addWidget(self.strip_indicators_box)

        layout.addStretch()

        deck_lbl = QLabel("No deck:")
        deck_lbl.setStyleSheet("color: #64748B; font-size: 10.5px;")
        layout.addWidget(deck_lbl)
        deck_minus = QPushButton("−")
        deck_minus.setObjectName("qtyButton")
        deck_minus.setFixedSize(24, 22)
        deck_minus.clicked.connect(lambda: self._adjust_deck_copies(-1))
        layout.addWidget(deck_minus)
        self.deck_qty_label = QLabel("0")
        self.deck_qty_label.setFixedWidth(18)
        self.deck_qty_label.setAlignment(Qt.AlignCenter)
        self.deck_qty_label.setStyleSheet("font-weight: 800; color: #22C55E;")
        layout.addWidget(self.deck_qty_label)
        deck_plus = QPushButton("+")
        deck_plus.setObjectName("qtyButton")
        deck_plus.setFixedSize(24, 22)
        deck_plus.clicked.connect(lambda: self._adjust_deck_copies(1))
        layout.addWidget(deck_plus)
        self._deck_minus, self._deck_plus = deck_minus, deck_plus

        detail_btn = QPushButton("Detalhes")
        detail_btn.setObjectName("ghostButton")
        detail_btn.clicked.connect(self._open_full_detail)
        layout.addWidget(detail_btn)

        return row

    def _build_color_chip_row(self):
        row = QFrame()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        lbl = QLabel("COR")
        lbl.setObjectName("sectionHint")
        layout.addWidget(lbl)

        self._color_chip_buttons = {}
        for color, hex_code in COLOR_CHIPS:
            btn = QPushButton(f"● {color.upper()}")
            btn.setCheckable(True)
            btn.setObjectName("colorFilterChip")
            btn.setProperty("class", f"color-{color.lower()}")
            btn.clicked.connect(lambda checked, c=color: self._toggle_color_chip(c, checked))
            layout.addWidget(btn)
            self._color_chip_buttons[color] = btn
        layout.addStretch()
        return row

    def _build_keyword_chip_row(self):
        row = QFrame()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        lbl = QLabel("EFEITO")
        lbl.setObjectName("sectionHint")
        layout.addWidget(lbl)

        self._keyword_chip_buttons = {}
        for keyword in KEYWORD_CHIPS:
            btn = QPushButton(keyword)
            btn.setCheckable(True)
            btn.setObjectName("keywordChip")
            btn.clicked.connect(lambda checked, k=keyword: self._toggle_keyword_chip(k, checked))
            layout.addWidget(btn)
            self._keyword_chip_buttons[keyword] = btn
        layout.addStretch()
        return row

    def _toggle_color_chip(self, color, active):
        if active:
            self._active_colors.add(color)
        else:
            self._active_colors.discard(color)
        self._apply_filters()

    def _toggle_keyword_chip(self, keyword, active):
        if active:
            self._active_keywords.add(keyword)
        else:
            self._active_keywords.discard(keyword)
        self._apply_filters()

    def _make_combo(self, label):
        combo = QComboBox()
        combo.addItem(f"Todos — {label}", "")
        combo.currentIndexChanged.connect(self._apply_filters)
        combo.setMinimumWidth(110)
        return combo

    # ---------- Lifecycle ----------
    def refresh(self):
        if not self._populated_filters:
            self._populate_filters()
            self._populated_filters = True
            self._reload_deck_combo_list()
            self._apply_filters()
        else:
            # Catalog contents and the in-progress deck edit rarely need to
            # change just because the user switched back to this page —
            # avoid rebuilding ~900 tiles or discarding unsaved deck edits.
            self._refresh_visible_restrictions()

    def _populate_filters(self):
        sets = sorted({c["set"] for c in self.repo.cards})
        types = sorted({c["type"] for c in self.repo.cards})
        rarities = sorted({c["rarity"] for c in self.repo.cards})
        levels = sorted({c["level"] for c in self.repo.cards if c.get("level")})

        for combo, values in [
            (self.set_filter, sets), (self.type_filter, types), (self.rarity_filter, rarities),
        ]:
            for v in values:
                combo.addItem(v, v)
        for lvl in levels:
            self.level_filter.addItem(f"Lv.{lvl}", lvl)

    # ---------- In-memory working deck ----------
    def _working_cards_list(self):
        return [{"card_id": cid, "copies": n} for cid, n in self._working_cards.items()]

    def _switch_deck(self, deck_id):
        self.current_deck_id = deck_id
        self._working_deck_id = deck_id
        if deck_id and self.deckbuilder:
            self._working_cards = {c["card_id"]: c["copies"] for c in self.deckbuilder.get_deck_cards(deck_id)}
        else:
            self._working_cards = {}
        self._dirty = False
        self._render_deck_bar_status()
        self._render_deck_panel()
        self._refresh_visible_deck_counts()
        self._update_selected_strip()
        self._update_save_button_state()

    def _mark_dirty(self):
        self._dirty = True
        self._update_save_button_state()

    def _update_save_button_state(self):
        self.save_btn.setEnabled(bool(self.current_deck_id) and self._dirty)
        self.unsaved_label.setText("● Não salvo" if self._dirty else ("● Salvo" if self.current_deck_id else ""))

    def _save_deck(self):
        if not self.current_deck_id or not self.deckbuilder:
            return
        self.deckbuilder.save_deck_cards(self.current_deck_id, self._working_cards_list())
        self._dirty = False
        self._update_save_button_state()
        self._render_deck_bar_status()
        self._reload_deck_combo_list()

    def _confirm_discard_or_save(self) -> bool:
        """Asks what to do with unsaved edits before switching decks.
        Returns True if it's OK to proceed (saved or discarded), False to cancel."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Alterações não salvas")
        box.setText("Este deck tem alterações não salvas. O que deseja fazer?")
        save_btn = box.addButton("Salvar", QMessageBox.AcceptRole)
        discard_btn = box.addButton("Descartar", QMessageBox.DestructiveRole)
        box.addButton("Cancelar", QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save_btn:
            self._save_deck()
            return True
        if clicked is discard_btn:
            return True
        return False

    def _select_combo_deck(self, deck_id):
        idx = self.deck_combo.findData(deck_id)
        if idx >= 0:
            self.deck_combo.blockSignals(True)
            self.deck_combo.setCurrentIndex(idx)
            self.deck_combo.blockSignals(False)

    # ---------- Deck combo / CRUD ----------
    def _reload_deck_combo_list(self):
        if not self.deckbuilder:
            return
        decks = self.deckbuilder.list_decks()
        ids = [d["deck_id"] for d in decks]
        keep_id = self.current_deck_id if self.current_deck_id in ids else None

        self.deck_combo.blockSignals(True)
        self.deck_combo.clear()
        selected_index = -1
        for i, d in enumerate(decks):
            if d["deck_id"] == self._working_deck_id:
                summary = self.deckbuilder.summarize(self._working_cards_list())
            else:
                summary = d
            star = " *" if d["deck_id"] == self._working_deck_id and self._dirty else ""
            self.deck_combo.addItem(f'{d["name"]}{star} ({summary["main_count"]}/{MAIN_DECK_SIZE})', d["deck_id"])
            if d["deck_id"] == keep_id:
                selected_index = i
        self.deck_combo.blockSignals(False)

        if selected_index >= 0:
            self.deck_combo.setCurrentIndex(selected_index)
            if self._working_deck_id != keep_id:
                self._switch_deck(keep_id)
        elif decks:
            self.deck_combo.setCurrentIndex(0)
            self._switch_deck(decks[0]["deck_id"])
        else:
            self._switch_deck(None)
        self._render_deck_bar_status()

    def _on_deck_combo_changed(self, index):
        new_id = self.deck_combo.itemData(index) if index >= 0 else None
        if new_id == self._working_deck_id:
            return
        if self._dirty and not self._confirm_discard_or_save():
            self._select_combo_deck(self._working_deck_id)
            return
        self._switch_deck(new_id)
        self._reload_deck_combo_list()

    def _create_deck(self):
        if self._dirty and not self._confirm_discard_or_save():
            return
        name, ok = QInputDialog.getText(self, "Novo Deck", "Nome do deck:")
        if not ok or not name.strip():
            return
        deck_id = self.deckbuilder.create_deck(name.strip())
        self._switch_deck(deck_id)
        self._reload_deck_combo_list()

    def _rename_deck(self):
        if not self.current_deck_id:
            return
        deck = self.deckbuilder.get_deck(self.current_deck_id)
        name, ok = QInputDialog.getText(self, "Renomear Deck", "Novo nome:", text=deck["name"] if deck else "")
        if not ok or not name.strip():
            return
        self.deckbuilder.rename_deck(self.current_deck_id, name.strip())
        self._reload_deck_combo_list()

    def _delete_deck(self):
        if not self.current_deck_id:
            return
        confirm = QMessageBox.question(self, "Excluir deck", "Tem certeza que deseja excluir este deck?")
        if confirm != QMessageBox.Yes:
            return
        self.deckbuilder.delete_deck(self.current_deck_id)
        self._switch_deck(None)
        self._reload_deck_combo_list()

    def _render_deck_bar_status(self):
        if not self.current_deck_id or not self.deckbuilder:
            self.counts_label.setText("Nenhum deck selecionado")
            self.status_label.setText("")
            self.deck_progress.setValue(0)
            return
        validation = self.deckbuilder.validate_cards(self._working_cards_list())
        self.counts_label.setText(
            f'{validation["main_count"]}/{MAIN_DECK_SIZE} CARDS  ·  '
            f'{validation["egg_count"]}/{DIGI_EGG_DECK_MAX} DIGI-EGGS'
        )
        self.deck_progress.setMaximum(MAIN_DECK_SIZE)
        self.deck_progress.setValue(min(MAIN_DECK_SIZE, validation["main_count"]))
        label, color = STATUS_META.get(validation["status"], ("", "#94A3B8"))
        self.status_label.setText(label)
        self.status_label.setStyleSheet(f"font-weight: 800; font-size: 12px; color: {color};")

    # ---------- Catalog filtering / grid ----------
    def _apply_filters(self):
        text = self.search.text().strip().lower()
        set_v = self.set_filter.currentData()
        type_v = self.type_filter.currentData()
        rarity_v = self.rarity_filter.currentData()
        level_v = self.level_filter.currentData()

        results = []
        for c in self.repo.cards:
            if text and text not in c["card_id"].lower() and text not in c.get("name", "").lower():
                continue
            if set_v and c["set"] != set_v:
                continue
            if type_v and c["type"] != type_v:
                continue
            if rarity_v and c["rarity"] != rarity_v:
                continue
            if level_v and c.get("level") != level_v:
                continue
            if self._active_colors and c.get("color") not in self._active_colors and c.get("color2") not in self._active_colors:
                continue
            if self._active_keywords and not self._card_has_any_keyword(c):
                continue
            results.append(c)

        self._filtered_results = results
        self._current_page = 0
        self._rebuild_grid()

    def _card_has_any_keyword(self, card):
        effect_text = " ".join(filter(None, [
            card.get("main_effect"), card.get("source_effect"), card.get("alt_effect"),
        ]))
        return any(keyword in effect_text for keyword in self._active_keywords)

    def _total_pages(self):
        return max(1, -(-len(self._filtered_results) // PAGE_SIZE))  # ceil div

    def _current_page_items(self):
        start = self._current_page * PAGE_SIZE
        return self._filtered_results[start:start + PAGE_SIZE]

    def _update_pagination_controls(self):
        total = len(self._filtered_results)
        total_pages = self._total_pages()
        self.result_label.setText(f"{total} cartas encontradas")
        self.page_label.setText(f"Página {self._current_page + 1} de {total_pages}")
        self.prev_page_btn.setEnabled(self._current_page > 0)
        self.next_page_btn.setEnabled(self._current_page < total_pages - 1)

    def _go_prev_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._rebuild_grid()

    def _go_next_page(self):
        if self._current_page < self._total_pages() - 1:
            self._current_page += 1
            self._rebuild_grid()

    def _rebuild_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        self._widgets = {}
        self._image_queue = []
        restriction_map = self.banlist.restriction_map()
        self._update_pagination_controls()

        width = max(self.catalog_scroll.viewport().width() - 20, COLS_TARGET_WIDTH)
        self._current_cols = max(1, width // COLS_TARGET_WIDTH)

        # Widgets (and their image decode) are built progressively across
        # event-loop ticks instead of all at once, AND only for the current
        # page (at most PAGE_SIZE cards) — so this stays fast no matter how
        # big the full catalog (4000+ cards) is.
        self._build_generation += 1
        self._build_queue = self._current_page_items()
        self._build_index = 0
        self._restriction_snapshot = restriction_map
        self._process_build_queue(self._build_generation)

    def _process_build_queue(self, generation):
        if generation != self._build_generation:
            return  # a newer filter/rebuild superseded this one
        batch, self._build_queue = self._build_queue[:WIDGET_BATCH_SIZE], self._build_queue[WIDGET_BATCH_SIZE:]
        cols = self._current_cols
        for card in batch:
            cid = card["card_id"]
            widget = CardWidget(
                card, restriction=self._restriction_snapshot.get(cid), draggable=False,
                deck_count=self._working_cards.get(cid, 0) if self.current_deck_id else None,
                selected=(cid == self.selected_card_id),
                lazy_image=True,
                indicators=self._indicators_for(cid),
            )
            widget.clicked.connect(self._catalog_left_click)
            widget.right_clicked.connect(self._catalog_right_click)
            self._widgets[cid] = widget
            self.grid.addWidget(widget, self._build_index // cols, self._build_index % cols)
            self._build_index += 1
            self._image_queue.append(widget)

        if self._build_queue:
            QTimer.singleShot(0, lambda: self._process_build_queue(generation))
        else:
            self._process_image_queue()

    def _indicators_for(self, card_id):
        """Only cards with real per-deck presence data carry indicators —
        shown discreetly in the hover popup, never as a permanent badge."""
        return self.repo.ban_candidate(card_id)

    def _reflow(self):
        width = max(self.catalog_scroll.viewport().width() - 20, COLS_TARGET_WIDTH)
        cols = max(1, width // COLS_TARGET_WIDTH)
        if cols == self._current_cols:
            return
        self._current_cols = cols
        widgets = list(self._widgets.values())
        for w in widgets:
            self.grid.removeWidget(w)
        for i, w in enumerate(widgets):
            self.grid.addWidget(w, i // cols, i % cols)

    def _refresh_visible_deck_counts(self):
        for card_id, widget in self._widgets.items():
            widget.set_deck_count(self._working_cards.get(card_id, 0) if self.current_deck_id else None)

    def _refresh_visible_restrictions(self):
        restriction_map = self.banlist.restriction_map()
        for card_id, widget in self._widgets.items():
            widget.set_restriction(restriction_map.get(card_id))

    def _process_image_queue(self):
        batch, self._image_queue = self._image_queue[:IMAGE_BATCH_SIZE], self._image_queue[IMAGE_BATCH_SIZE:]
        for widget in batch:
            widget.load_image()
        if self._image_queue:
            QTimer.singleShot(0, self._process_image_queue)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._populated_filters:
            self._reflow()

    # ---------- Selection / selected-card strip ----------
    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _select_card(self, card_id):
        if self.selected_card_id and self.selected_card_id in self._widgets:
            self._widgets[self.selected_card_id].set_selected(False)
        self.selected_card_id = card_id
        if card_id in self._widgets:
            self._widgets[card_id].set_selected(True)
        self._update_selected_strip()

    def _update_selected_strip(self):
        card = self.repo.card(self.selected_card_id) if self.selected_card_id else None
        if not card:
            self.strip_name.setText("Nenhuma carta selecionada")
            self.strip_meta.setText("")
            self.strip_restriction.setText("")
            self._clear_layout(self.strip_indicators_layout)
            self.deck_qty_label.setText("0")
            for btn in (self._deck_minus, self._deck_plus):
                btn.setEnabled(False)
            return

        color_dot = "".join(f'<span style="color:{color_hex(c)};">●</span> ' for c in [card.get("color"), card.get("color2")] if c)
        self.strip_name.setTextFormat(Qt.RichText)
        self.strip_name.setText(f'{color_dot}<b>{card.get("name","")}</b>  ·  {card["card_id"]}')
        self.strip_meta.setText(
            f'{card.get("color","")} · Lv.{card.get("level") or "-"} · {card.get("type","")} · '
            f'{card.get("rarity","")} · {card.get("set","")}'
        )

        restriction = self.banlist.restriction_of(card["card_id"])
        if restriction:
            meta = RESTRICTION_META[restriction]
            self.strip_restriction.setText(f'{meta["icon"]} {meta["label"].upper()}')
            self.strip_restriction.setStyleSheet(f'color: {meta["color"]}; font-weight: 800; font-size: 11px;')
        else:
            self.strip_restriction.setText("")

        self._clear_layout(self.strip_indicators_layout)
        candidate = self.repo.ban_candidate(card["card_id"])
        if candidate:
            for key, label in INDICATOR_FIELDS:
                self.strip_indicators_layout.addWidget(MetricInline(label, candidate.get(key, 0.0)))

        in_deck = self._working_cards.get(card["card_id"], 0)
        self.deck_qty_label.setText(str(in_deck))
        deck_active = bool(self.current_deck_id)
        allowed = self.deckbuilder.max_allowed_copies(card["card_id"]) if deck_active else 0
        self._deck_minus.setEnabled(deck_active and in_deck > 0)
        self._deck_plus.setEnabled(deck_active and in_deck < allowed)

    def _catalog_left_click(self, card_id):
        self._select_card(card_id)
        self._adjust_deck_copies(1)

    def _catalog_right_click(self, card_id):
        self._select_card(card_id)
        self._adjust_deck_copies(-1)

    def _adjust_deck_copies(self, delta):
        if not self.selected_card_id or not self.current_deck_id or not self.deckbuilder:
            return
        current = self._working_cards.get(self.selected_card_id, 0)
        allowed = self.deckbuilder.max_allowed_copies(self.selected_card_id)
        new_copies = max(0, min(current + delta, allowed))
        if new_copies == current:
            return
        if new_copies <= 0:
            self._working_cards.pop(self.selected_card_id, None)
        else:
            self._working_cards[self.selected_card_id] = new_copies

        self._mark_dirty()
        self._update_selected_strip()
        self._refresh_visible_deck_counts()
        self._render_deck_bar_status()
        self._render_deck_panel()
        self._update_current_combo_label()

    def _update_current_combo_label(self):
        """Cheap alternative to _reload_deck_combo_list(): updates just the
        active deck's own combo entry instead of re-querying every deck (and
        every deck's full card list) from the DB on each +/- click."""
        idx = self.deck_combo.currentIndex()
        if idx < 0 or not self.current_deck_id:
            return
        deck = self.deckbuilder.get_deck(self.current_deck_id)
        if not deck:
            return
        summary = self.deckbuilder.summarize(self._working_cards_list())
        star = " *" if self._dirty else ""
        self.deck_combo.blockSignals(True)
        self.deck_combo.setItemText(idx, f'{deck["name"]}{star} ({summary["main_count"]}/{MAIN_DECK_SIZE})')
        self.deck_combo.blockSignals(False)

    # ---------- Deck Builder columns + curve ----------
    def _render_deck_panel(self):
        while self.deck_columns_layout.count():
            item = self.deck_columns_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        while self.curve_row.count():
            item = self.curve_row.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not self.current_deck_id or not self.deckbuilder:
            empty_col, empty_tiles = self._build_deck_level_column("—", "", 0, accent="#1B2A3A")
            empty = QLabel("Selecione ou crie um deck para começar a montar.")
            empty.setObjectName("sectionHint")
            empty.setWordWrap(True)
            empty_tiles.addWidget(empty, 0, 0, 1, 2)
            self.deck_columns_layout.addWidget(empty_col)
            self.curve_row.addStretch()
            self.issues_label.setText("")
            return

        validation = self.deckbuilder.validate_cards(self._working_cards_list())
        issues = validation["issues"]
        if issues:
            extra = f"  (+{len(issues) - 1})" if len(issues) > 1 else ""
            self.issues_label.setText(f"⚠ {issues[0]}{extra}")
            self.issues_label.setToolTip("\n".join(issues))
        else:
            self.issues_label.setText("")
            self.issues_label.setToolTip("")

        cards_with_copies = []
        for card_id, copies in self._working_cards.items():
            card = self.repo.card(card_id)
            if card:
                cards_with_copies.append((card, copies))

        columns = LEVEL_COLUMNS + [LEVEL_COLUMN_FALLBACK]
        remaining = list(cards_with_copies)
        buckets = []
        for col_id, header, sublabel, predicate in columns:
            matched = [(card, copies) for card, copies in remaining if predicate(card)]
            remaining = [pair for pair in remaining if pair not in matched]
            buckets.append((col_id, header, sublabel, matched))

        counts = [sum(c for _, c in group) for _, _, _, group in buckets]
        max_count = max(counts) if any(counts) else 1

        for (col_id, header, sublabel, group), count in zip(buckets, counts):
            accent = LEVEL_COLUMN_COLORS.get(col_id, "#475569")
            col, tiles_layout = self._build_deck_level_column(header, sublabel, count, accent=accent)
            group.sort(key=lambda x: x[0]["card_id"])
            for i, (card, copies) in enumerate(group):
                tiles_layout.addWidget(self._build_deck_tile(card, copies), i // 2, i % 2)
            self.deck_columns_layout.addWidget(col)

            if col_id != "other" or count:
                self.curve_row.addWidget(
                    self._build_curve_block(header, count, max_count, LEVEL_COLUMN_COLORS.get(col_id, "#475569"))
                )
        self.curve_row.addStretch()

    def _build_deck_tile(self, card, copies):
        frame = QFrame()
        frame.setObjectName("surface")
        frame.setProperty("class", "cardWidget")
        frame.setCursor(Qt.PointingHandCursor)
        frame.setStyleSheet(f"QFrame#surface {{ border: 1px solid {color_hex(card.get('color'))}; border-radius: 8px; }}")
        frame.setToolTip(
            f'{card.get("name","")} ({card["card_id"]}) — clique esquerdo adiciona 1, direito remove 1'
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)

        img = QLabel()
        img.setFixedSize(DECK_TILE_IMG)
        img.setAlignment(Qt.AlignCenter)
        img.setPixmap(load_card_pixmap(card["card_id"], DECK_TILE_IMG))
        layout.addWidget(img, alignment=Qt.AlignCenter)

        qty = QLabel(f"×{copies}")
        qty.setAlignment(Qt.AlignCenter)
        qty.setStyleSheet("font-weight: 800; color: #22C55E; font-size: 10.5px;")
        layout.addWidget(qty)

        frame.mousePressEvent = lambda e, cid=card["card_id"]: self._deck_tile_clicked(e, cid)
        frame.enterEvent = lambda e, c=card: self._deck_tile_hover_enter(c)
        frame.leaveEvent = lambda e: self._deck_tile_hover_leave()
        return frame

    def _deck_tile_clicked(self, event, card_id):
        self._select_card(card_id)
        if event.button() == Qt.RightButton:
            self._adjust_deck_copies(-1)
        else:
            self._adjust_deck_copies(1)

    def _deck_tile_hover_enter(self, card):
        indicators = self.repo.ban_candidate(card["card_id"])
        restriction = self.banlist.restriction_of(card["card_id"])
        self._deck_hover_timer = QTimer(self)
        self._deck_hover_timer.setSingleShot(True)
        self._deck_hover_timer.timeout.connect(
            lambda: get_hover_popup().show_for(card, QCursor.pos(), indicators, restriction)
        )
        self._deck_hover_timer.start(220)

    def _deck_tile_hover_leave(self):
        if getattr(self, "_deck_hover_timer", None):
            self._deck_hover_timer.stop()
        get_hover_popup().hide()

    def _open_full_detail(self):
        card = self.repo.card(self.selected_card_id) if self.selected_card_id else None
        if not card:
            return
        dlg = CardDetailDialog(card, self.repo, self.banlist, self.settings, parent=self)
        dlg.restriction_changed.connect(self.refresh)
        dlg.exec()
