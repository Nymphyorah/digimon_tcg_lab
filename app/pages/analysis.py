"""Analysis — the core screen for identifying cards with strong competitive
presence. Shows the three real, independent indicators collected from
tournament data (Meta Usage, Top Cut, Dominance) side by side, sortable and
searchable. No aggregate score is computed and no restriction is ever
suggested automatically — the system presents data, the community decides.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QLabel, QLineEdit, QTabWidget, QFrame, QScrollArea
)

from app.components.card_detail_dialog import CardDetailDialog
from app.components.charts import ScatterChart

INDICATOR_COLUMNS = [
    ("meta_usage", "Meta Usage"),
    ("top_cut", "Top Cut"),
    ("dominance", "Dominance"),
]


class _NumericItem(QTableWidgetItem):
    """Sorts by the real underlying number, displays it formatted."""

    def __init__(self, value: float, text: str):
        super().__init__(text)
        self.value = value

    def __lt__(self, other):
        if isinstance(other, _NumericItem):
            return self.value < other.value
        return super().__lt__(other)


class AnalysisPage(QWidget):
    navigate_requested = Signal(str)

    def __init__(self, repo, banlist, settings, analyzer, db, updater, collection=None, deckbuilder=None, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.banlist = banlist
        self.settings = settings
        self.analyzer = analyzer
        self._rows = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 24)
        outer.setSpacing(14)

        header_col = QVBoxLayout()
        header_col.setSpacing(2)
        title = QLabel("ANALYSIS")
        title.setObjectName("sectionLabel")
        header_col.addWidget(title)
        subtitle = QLabel(
            "Meta Usage, Top Cut e Dominance de cada carta — dados reais, sem pontuação artificial. "
            "A decisão de restringir é sempre sua."
        )
        subtitle.setObjectName("sectionHint")
        subtitle.setWordWrap(True)
        header_col.addWidget(subtitle)
        outer.addLayout(header_col)

        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)

        # ---- Main tab: scatter + sortable/searchable table ----
        main_tab = QWidget()
        main_layout = QVBoxLayout(main_tab)
        main_layout.setContentsMargins(0, 12, 0, 0)
        main_layout.setSpacing(12)

        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Buscar carta...")
        self.search.textChanged.connect(self._apply_search)
        toolbar.addWidget(self.search, 1)
        hint = QLabel("Clique no cabeçalho da coluna para ordenar · duplo clique na linha para abrir a carta")
        hint.setObjectName("sectionHint")
        toolbar.addWidget(hint)
        main_layout.addLayout(toolbar)

        scatter_box = QFrame()
        scatter_box.setObjectName("surface")
        scatter_layout = QVBoxLayout(scatter_box)
        scatter_layout.setContentsMargins(16, 12, 16, 12)
        scatter_title = QLabel("META USAGE × DOMINANCE")
        scatter_title.setObjectName("sectionLabel")
        scatter_layout.addWidget(scatter_title)
        scatter_hint = QLabel("Cada ponto é uma carta · o tamanho representa o Top Cut")
        scatter_hint.setObjectName("sectionHint")
        scatter_layout.addWidget(scatter_hint)
        self.scatter = ScatterChart()
        self.scatter.setMinimumHeight(220)
        self.scatter.setMaximumHeight(280)
        self.scatter.point_clicked.connect(self._open_card_by_id)
        scatter_layout.addWidget(self.scatter)
        main_layout.addWidget(scatter_box)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Card", "Meta Usage", "Top Cut", "Dominance"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.cellDoubleClicked.connect(self._on_row_activated)
        main_layout.addWidget(self.table, 1)

        self.tabs.addTab(main_tab, "Indicadores")

        # ---- Secondary tab: Engine Detection (unchanged, real data) ----
        engine_scroll = QScrollArea()
        engine_scroll.setWidgetResizable(True)
        engine_scroll.setFrameShape(QFrame.NoFrame)
        engine_content = QWidget()
        self.engine_layout = QVBoxLayout(engine_content)
        self.engine_layout.setSpacing(12)
        engine_scroll.setWidget(engine_content)
        self.tabs.addTab(engine_scroll, "Engine Detection")

    def refresh(self):
        self._rows = self.analyzer.candidate_table()
        self._populate_table(self._rows)
        self._populate_scatter(self._rows)
        self._build_engine_detection()

    def _apply_search(self, text):
        text = text.strip().lower()
        if not text:
            self._populate_table(self._rows)
            return
        filtered = [
            r for r in self._rows
            if text in r["card"]["card_id"].lower() or text in r["card"].get("name", "").lower()
        ]
        self._populate_table(filtered)

    def _populate_table(self, rows):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            card = row["card"]
            name_item = QTableWidgetItem(f'{card["card_id"]} · {card.get("name","")}')
            name_item.setData(Qt.UserRole, row)
            self.table.setItem(i, 0, name_item)
            for col, (key, _label) in enumerate(INDICATOR_COLUMNS, start=1):
                value = row.get(key, 0.0)
                self.table.setItem(i, col, _NumericItem(value, f"{value}%"))
        self.table.setSortingEnabled(True)

    def _populate_scatter(self, rows):
        self.scatter.plot_points(rows)

    def _build_engine_detection(self):
        while self.engine_layout.count():
            item = self.engine_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        clusters = self.analyzer.engine_detection()
        if not clusters:
            empty = QLabel("Nenhum engine recorrente identificado com os dados atuais.")
            empty.setStyleSheet("color: #64748B;")
            self.engine_layout.addWidget(empty)
            self.engine_layout.addStretch()
            return

        note = QLabel(
            "Descoberta analítica baseada em coocorrência de cartas em alta quantidade — "
            "não representa uma regra oficial."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #475569; font-size: 10px;")
        self.engine_layout.addWidget(note)

        for cluster in clusters:
            box = QFrame()
            box.setObjectName("surface")
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(16, 14, 16, 14)

            header = QHBoxLayout()
            title = QLabel("ENGINE DETECTADA")
            title.setStyleSheet("color: #2388FF; font-weight: 800; font-size: 12px;")
            header.addWidget(title)
            header.addStretch()
            presence = QLabel(f'Presença conjunta: {cluster["presence_pct"]}%')
            presence.setStyleSheet("color: #94A3B8; font-size: 11px;")
            header.addWidget(presence)
            box_layout.addLayout(header)

            cards_row = QHBoxLayout()
            for entry in cluster["cards"]:
                card = self.repo.card(entry["card_id"])
                name = card["name"] if card else entry["card_id"]
                lbl = QLabel(f'{entry["card_id"]} ×{entry["copies"]} — {name}')
                lbl.setStyleSheet("color: #F8FAFC; font-size: 11px; font-weight: 600;")
                cards_row.addWidget(lbl)
            cards_row.addStretch()
            box_layout.addLayout(cards_row)

            deck_label = QLabel(
                f'Principal deck: {cluster["main_deck"]}  ·  Presença: {cluster["main_deck_presence_pct"]}%'
            )
            deck_label.setStyleSheet("color: #64748B; font-size: 11px;")
            box_layout.addWidget(deck_label)

            self.engine_layout.addWidget(box)

        self.engine_layout.addStretch()

    def _on_row_activated(self, row, _col):
        item = self.table.item(row, 0)
        if not item:
            return
        candidate_row = item.data(Qt.UserRole)
        if not candidate_row:
            return
        self._open_card(candidate_row["card"])

    def _open_card_by_id(self, card_id):
        card = self.repo.card(card_id)
        if card:
            self._open_card(card)

    def _open_card(self, card):
        dlg = CardDetailDialog(card, self.repo, self.banlist, self.settings, parent=self)
        dlg.restriction_changed.connect(self.refresh)
        dlg.exec()
