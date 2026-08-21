from PySide6.QtCore import Qt, Signal, QSize, QTimer, QPoint
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, QComboBox,
    QScrollArea, QFrame, QLabel, QPushButton, QSplitter,
    QInputDialog, QMessageBox
)

from app.components.card_widget import CardWidget
from app.components.image_loader import load_card_pixmap, invalidate_card_pixmap_cache
from app.components.card_detail_dialog import CardDetailDialog
from app.components.card_hover_popup import get_hover_popup
from core.image_cache import get_image_cache_manager
from core.deckbuilder import MAIN_DECK_SIZE, DIGI_EGG_DECK_MAX
from core.ban_score import compute_ban_score, risk_for_score

RISK_CHIP_OBJECT_NAMES = {
    "CRITICO": "riskChipCritical",
    "ALTO": "riskChipHigh",
    "MODERADO": "riskChipModerate",
    "BAIXO": "riskChipLow",
    "NORMAL": "riskChipNormal",
}

COLS_TARGET_WIDTH = 176
IMAGE_BATCH_SIZE = 40
WIDGET_BATCH_SIZE = 60
PAGE_SIZE = 120  # caps how many tiles are ever live at once, regardless of catalog size
SEARCH_DEBOUNCE_MS = 250
STATUS_META = {
    "LEGAL": ("✅ Válido", "#22C55E"),
    "INCOMPLETO": ("⚠ Incompleto", "#EAB308"),
    "ILEGAL": ("❌ Ilegal", "#EF4444"),
}

# Official Digimon TCG card colors — used both for the quick filter chips and
# for the colored accent on each chip/border (presentational only, not new
# game data: every card's own `color` field already carries one of these).
COLOR_CHIPS = [
    ("Red", "#EF4444"), ("Blue", "#3B82F6"), ("Yellow", "#EAB308"),
    ("Green", "#22C55E"), ("Black", "#94A3B8"), ("Purple", "#A855F7"),
    ("White", "#F8FAFC"),
]

# Curated from the real printed effect text (main_effect/source_effect/
# alt_effect) already collected from digimoncard.io — these are literal
# substrings that appear on cards using them, not invented tags. A card
# matches a chip if the tag text appears anywhere in its effect text.
KEYWORD_CHIPS = [
    "Blocker", "On Play", "When Attacking", "Security",
    "DNA Digivolve", "Burst Digivolve", "Piercing", "Rush",
]

# Deck panel: groups the working deck into level-curve columns instead of a
# flat type list. Each entry is (id, header, predicate over a card dict).
LEVEL_COLUMNS = [
    ("egg", "Lv.2 · Digi-Ovo", lambda c: c.get("type") == "Digi-Egg"),
    ("lv3", "Lv.3 · Rookie", lambda c: c.get("level") == 3),
    ("lv4", "Lv.4 · Champion", lambda c: c.get("level") == 4),
    ("lv5", "Lv.5 · Ultimate", lambda c: c.get("level") == 5),
    ("lv67", "Lv.6-7 · Mega", lambda c: c.get("level") in (6, 7)),
    ("tamer", "Tamers", lambda c: c.get("type") == "Tamer"),
    ("option", "Options", lambda c: c.get("type") == "Option"),
]
LEVEL_COLUMN_FALLBACK = ("other", "Outros", lambda c: True)


class CollectionPage(QWidget):
    """Coleção + Deck Builder num único workspace: painel de detalhe à
    esquerda, catálogo pesquisável no centro, deck atual à direita —
    sobre toda a base de cartas do catálogo.

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
        outer.setContentsMargins(24, 20, 24, 24)
        outer.setSpacing(12)

        get_image_cache_manager().image_ready.connect(self._on_detail_image_ready)

        outer.addWidget(self._build_deck_bar())

        splitter = QSplitter(Qt.Horizontal)
        outer.addWidget(splitter, 1)
        splitter.addWidget(self._build_detail_panel())
        splitter.addWidget(self._build_catalog_panel())
        splitter.addWidget(self._build_deck_panel())
        splitter.setSizes([260, 760, 460])
        splitter.splitterMoved.connect(lambda *_: self._reflow())

    # ---------- Top: deck context bar ----------
    def _build_deck_bar(self):
        bar = QFrame()
        bar.setObjectName("surface")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        deck_lbl = QLabel("DECK:")
        deck_lbl.setStyleSheet("color: #64748B; font-size: 10px; font-weight: 700;")
        layout.addWidget(deck_lbl)

        self.deck_combo = QComboBox()
        self.deck_combo.setMinimumWidth(180)
        self.deck_combo.currentIndexChanged.connect(self._on_deck_combo_changed)
        layout.addWidget(self.deck_combo)

        new_btn = QPushButton("+ Novo")
        new_btn.clicked.connect(self._create_deck)
        layout.addWidget(new_btn)
        rename_btn = QPushButton("Renomear")
        rename_btn.clicked.connect(self._rename_deck)
        layout.addWidget(rename_btn)
        delete_btn = QPushButton("Excluir")
        delete_btn.setObjectName("dangerButton")
        delete_btn.clicked.connect(self._delete_deck)
        layout.addWidget(delete_btn)

        self.save_btn = QPushButton("💾 Salvar")
        self.save_btn.setObjectName("primaryButton")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._save_deck)
        layout.addWidget(self.save_btn)

        layout.addSpacing(16)
        self.counts_label = QLabel("")
        self.counts_label.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 700;")
        layout.addWidget(self.counts_label)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-weight: 800; font-size: 12px;")
        layout.addWidget(self.status_label)

        self.unsaved_label = QLabel("")
        self.unsaved_label.setStyleSheet("color: #F97316; font-weight: 700; font-size: 11px;")
        layout.addWidget(self.unsaved_label)

        layout.addStretch()
        return bar

    # ---------- Left: selected card detail ----------
    def _build_detail_panel(self):
        panel = QFrame()
        panel.setObjectName("surface")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignTop)

        self.detail_image = QLabel()
        self.detail_image.setFixedSize(QSize(200, 280))
        self.detail_image.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.detail_image, alignment=Qt.AlignCenter)

        self.detail_name = QLabel("Selecione uma carta")
        self.detail_name.setStyleSheet("font-size: 15px; font-weight: 800;")
        self.detail_name.setWordWrap(True)
        layout.addWidget(self.detail_name)

        self.detail_meta = QLabel("")
        self.detail_meta.setStyleSheet("color: #64748B; font-size: 11px;")
        self.detail_meta.setWordWrap(True)
        layout.addWidget(self.detail_meta)

        self.detail_restriction = QLabel("")
        self.detail_restriction.setStyleSheet("font-size: 11px; font-weight: 700;")
        layout.addWidget(self.detail_restriction)

        deck_row = QHBoxLayout()
        deck_lbl = QLabel("No deck:")
        deck_lbl.setStyleSheet("color: #94A3B8; font-size: 11px;")
        deck_minus = QPushButton("−")
        deck_minus.setFixedSize(28, 26)
        deck_minus.clicked.connect(lambda: self._adjust_deck_copies(-1))
        self.deck_qty_label = QLabel("0")
        self.deck_qty_label.setFixedWidth(24)
        self.deck_qty_label.setAlignment(Qt.AlignCenter)
        self.deck_qty_label.setStyleSheet("font-weight: 800; color: #22C55E;")
        deck_plus = QPushButton("+")
        deck_plus.setFixedSize(28, 26)
        deck_plus.clicked.connect(lambda: self._adjust_deck_copies(1))
        deck_row.addWidget(deck_lbl)
        deck_row.addStretch()
        deck_row.addWidget(deck_minus)
        deck_row.addWidget(self.deck_qty_label)
        deck_row.addWidget(deck_plus)
        layout.addLayout(deck_row)
        self._deck_minus, self._deck_plus = deck_minus, deck_plus

        detail_btn = QPushButton("Ver análise completa / Ban List")
        detail_btn.clicked.connect(self._open_full_detail)
        layout.addWidget(detail_btn)

        layout.addStretch()
        return panel

    # ---------- Center: catalog ----------
    def _build_catalog_panel(self):
        panel = QFrame()
        panel.setObjectName("surface")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Buscar carta...")
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

    # ---------- Right: current deck ----------
    def _build_deck_panel(self):
        panel = QFrame()
        panel.setObjectName("surface")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        title = QLabel("DECK ATUAL")
        title.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 700; letter-spacing: 1px;")
        layout.addWidget(title)

        self.deck_stats_label = QLabel("")
        self.deck_stats_label.setStyleSheet("color: #F8FAFC; font-size: 12px; font-weight: 700;")
        layout.addWidget(self.deck_stats_label)

        self.deck_curve_bar = QFrame()
        self.deck_curve_bar.setFixedHeight(8)
        curve_layout = QHBoxLayout(self.deck_curve_bar)
        curve_layout.setContentsMargins(0, 0, 0, 0)
        curve_layout.setSpacing(2)
        self.deck_curve_layout = curve_layout
        layout.addWidget(self.deck_curve_bar)

        self.issues_label = QLabel("")
        self.issues_label.setStyleSheet("color: #F97316; font-size: 10px;")
        self.issues_label.setWordWrap(True)
        layout.addWidget(self.issues_label)

        columns_scroll = QScrollArea()
        columns_scroll.setWidgetResizable(True)
        columns_scroll.setFrameShape(QFrame.NoFrame)
        columns_inner = QWidget()
        self.deck_columns_layout = QHBoxLayout(columns_inner)
        self.deck_columns_layout.setContentsMargins(0, 0, 0, 0)
        self.deck_columns_layout.setSpacing(8)
        self.deck_columns_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        columns_scroll.setWidget(columns_inner)
        layout.addWidget(columns_scroll, 1)

        return panel

    def _build_deck_level_column(self, header_text):
        col = QFrame()
        col.setObjectName("levelColumn")
        col.setFixedWidth(96)
        col_layout = QVBoxLayout(col)
        col_layout.setContentsMargins(6, 8, 6, 8)
        col_layout.setSpacing(6)

        header = QLabel(header_text)
        header.setObjectName("levelColumnHeader")
        header.setWordWrap(True)
        header.setAlignment(Qt.AlignCenter)
        col_layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        tiles_layout = QVBoxLayout(inner)
        tiles_layout.setContentsMargins(0, 0, 0, 0)
        tiles_layout.setSpacing(6)
        tiles_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(inner)
        col_layout.addWidget(scroll, 1)

        return col, tiles_layout

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
            btn = QPushButton(color)
            btn.setCheckable(True)
            btn.setProperty("class", "colorChip")
            btn.setStyleSheet(
                f'QPushButton {{ border: 1px solid {hex_code}; color: {hex_code}; }}'
                f'QPushButton:checked {{ background-color: {hex_code}; color: #070B12; }}'
            )
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
        self._update_detail_panel()
        self._update_save_button_state()

    def _mark_dirty(self):
        self._dirty = True
        self._update_save_button_state()

    def _update_save_button_state(self):
        self.save_btn.setEnabled(bool(self.current_deck_id) and self._dirty)
        self.unsaved_label.setText("● Não salvo" if self._dirty else "")

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
            return
        validation = self.deckbuilder.validate_cards(self._working_cards_list())
        self.counts_label.setText(
            f'Principal {validation["main_count"]}/{MAIN_DECK_SIZE}  ·  '
            f'Digi-Ovo {validation["egg_count"]}/{DIGI_EGG_DECK_MAX}'
        )
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
        self._weights_snapshot = self.settings.get("ban_score_weights")
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
                risk_chip=self._risk_chip_for(cid),
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

    def _risk_chip_for(self, card_id):
        """Only cards with real meta/ban-score data get a discreet risk chip —
        the catalog stays clean for the hundreds of cards without any."""
        candidate = self.repo.ban_candidate(card_id)
        if not candidate:
            return None
        score = compute_ban_score(candidate, self._weights_snapshot)
        label, icon = risk_for_score(score)
        if label in ("NORMAL",):
            return None  # not worth flagging — keeps chips meaningful, not noisy
        return f"{icon} {label}", RISK_CHIP_OBJECT_NAMES.get(label, "riskChipNormal")

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

    # ---------- Selection / detail panel ----------
    def _select_card(self, card_id):
        if self.selected_card_id and self.selected_card_id in self._widgets:
            self._widgets[self.selected_card_id].set_selected(False)
        self.selected_card_id = card_id
        if card_id in self._widgets:
            self._widgets[card_id].set_selected(True)
        self._update_detail_panel()

    def _update_detail_panel(self):
        card = self.repo.card(self.selected_card_id) if self.selected_card_id else None
        if not card:
            self.detail_image.clear()
            self.detail_name.setText("Selecione uma carta")
            self.detail_meta.setText("")
            self.detail_restriction.setText("")
            self.deck_qty_label.setText("0")
            for btn in (self._deck_minus, self._deck_plus):
                btn.setEnabled(False)
            return

        self.detail_image.setPixmap(load_card_pixmap(self.selected_card_id, QSize(200, 280)))
        self.detail_name.setText(f'{card.get("name","")}\n{card["card_id"]}')
        self.detail_meta.setText(
            f'{card.get("color","")} · Lv.{card.get("level") or "-"} · {card.get("type","")} · '
            f'{card.get("rarity","")} · {card.get("set","")}'
        )

        restriction = self.banlist.restriction_of(card["card_id"])
        if restriction:
            from core.banlist_manager import RESTRICTION_META
            meta = RESTRICTION_META[restriction]
            self.detail_restriction.setText(f'{meta["icon"]} {meta["label"]}')
            self.detail_restriction.setStyleSheet(f'color: {meta["color"]}; font-weight: 700; font-size: 11px;')
        else:
            self.detail_restriction.setText("")

        in_deck = self._working_cards.get(card["card_id"], 0)
        self.deck_qty_label.setText(str(in_deck))
        deck_active = bool(self.current_deck_id)
        allowed = self.deckbuilder.max_allowed_copies(card["card_id"]) if deck_active else 0
        self._deck_minus.setEnabled(deck_active and in_deck > 0)
        self._deck_plus.setEnabled(deck_active and in_deck < allowed)

    def _on_detail_image_ready(self, card_id: str):
        if card_id != self.selected_card_id:
            return
        invalidate_card_pixmap_cache(card_id)
        self.detail_image.setPixmap(load_card_pixmap(card_id, QSize(200, 280)))

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
        self._update_detail_panel()
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

    # ---------- Right panel: current deck, grouped by level curve ----------
    def _render_deck_panel(self):
        while self.deck_columns_layout.count():
            item = self.deck_columns_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        while self.deck_curve_layout.count():
            item = self.deck_curve_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not self.current_deck_id or not self.deckbuilder:
            empty_col, empty_tiles = self._build_deck_level_column("—")
            empty = QLabel("Selecione ou crie um deck para começar a montar.")
            empty.setStyleSheet("color: #64748B; font-size: 11px;")
            empty.setWordWrap(True)
            empty_tiles.addWidget(empty)
            self.deck_columns_layout.addWidget(empty_col)
            self.deck_stats_label.setText("")
            self.issues_label.setText("")
            return

        validation = self.deckbuilder.validate_cards(self._working_cards_list())
        self.issues_label.setText("\n".join(f"• {msg}" for msg in validation["issues"][:5]))
        self.deck_stats_label.setText(
            f'{validation["main_count"]}/{MAIN_DECK_SIZE} cartas  ·  '
            f'{validation["egg_count"]}/{DIGI_EGG_DECK_MAX} Digi-Ovos'
        )

        cards_with_copies = []
        for card_id, copies in self._working_cards.items():
            card = self.repo.card(card_id)
            if card:
                cards_with_copies.append((card, copies))

        columns = LEVEL_COLUMNS + [LEVEL_COLUMN_FALLBACK]
        remaining = list(cards_with_copies)
        buckets = []
        for col_id, header, predicate in columns:
            matched = [(card, copies) for card, copies in remaining if predicate(card)]
            remaining = [pair for pair in remaining if pair not in matched]
            buckets.append((header, matched))

        total_copies = sum(copies for _, copies in cards_with_copies) or 1
        for header, group in buckets:
            count = sum(c for _, c in group)
            col, tiles_layout = self._build_deck_level_column(f"{header}\n({count})")
            group.sort(key=lambda x: x[0]["card_id"])
            for card, copies in group:
                tiles_layout.addWidget(self._build_deck_tile(card, copies))
            self.deck_columns_layout.addWidget(col)

            if count:
                segment = QFrame()
                segment.setStyleSheet(f"background-color: {self._level_column_color(header)}; border-radius: 2px;")
                self.deck_curve_layout.addWidget(segment, count)
        if not any(count for _, group in buckets for count in [sum(c for _, c in group)]):
            self.deck_curve_layout.addStretch()

    @staticmethod
    def _level_column_color(header):
        return {
            "Lv.2 · Digi-Ovo": "#FACC15", "Lv.3 · Rookie": "#22C55E", "Lv.4 · Champion": "#3B82F6",
            "Lv.5 · Ultimate": "#A855F7", "Lv.6-7 · Mega": "#EF4444",
            "Tamers": "#F97316", "Options": "#94A3B8", "Outros": "#475569",
        }.get(header, "#475569")

    def _build_deck_tile(self, card, copies):
        frame = QFrame()
        frame.setCursor(Qt.PointingHandCursor)
        frame.setToolTip(
            f'{card.get("name","")} ({card["card_id"]}) — clique esquerdo adiciona 1, direito remove 1'
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        img = QLabel()
        img.setFixedSize(QSize(76, 106))
        img.setAlignment(Qt.AlignCenter)
        img.setPixmap(load_card_pixmap(card["card_id"], QSize(76, 106)))
        layout.addWidget(img, alignment=Qt.AlignCenter)

        qty = QLabel(f"×{copies}")
        qty.setAlignment(Qt.AlignCenter)
        qty.setStyleSheet("font-weight: 800; color: #22C55E; font-size: 11px;")
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
        self._deck_hover_timer = QTimer(self)
        self._deck_hover_timer.setSingleShot(True)
        self._deck_hover_timer.timeout.connect(lambda: get_hover_popup().show_for(card, QCursor.pos()))
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
