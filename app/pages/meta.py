from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QLabel, QFrame
)

from app.components.kpi_card import KpiCard
from app.components.charts import BarChart
from app.components.deck_detail_dialog import DeckDetailDialog
from core.meta_aggregator import aggregate, available_formats, available_tournaments

RANK_COLORS = {1: "#EAB308", 2: "#94A3B8", 3: "#B45309"}
PERIOD_OPTIONS = [
    ("Todo o período", None),
    ("Últimos 7 dias", 7),
    ("Últimos 30 dias", 30),
    ("Últimos 90 dias", 90),
]


class MetaPage(QWidget):
    navigate_requested = Signal(str)

    def __init__(self, repo, banlist, settings, analyzer, db, updater, collection=None, deckbuilder=None, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.banlist = banlist
        self.settings = settings
        self._populated_filters = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 24)
        outer.setSpacing(16)

        header_col = QVBoxLayout()
        header_col.setSpacing(2)
        title = QLabel("META ANALYSIS")
        title.setObjectName("sectionLabel")
        header_col.addWidget(title)
        subtitle = QLabel("Panorama do formato competitivo com base nos torneios reais coletados.")
        subtitle.setObjectName("sectionHint")
        header_col.addWidget(subtitle)
        outer.addLayout(header_col)

        filters = QHBoxLayout()
        self.format_combo = QComboBox()
        self.period_combo = QComboBox()
        for label, _days in PERIOD_OPTIONS:
            self.period_combo.addItem(label, _days)
        self.tournament_combo = QComboBox()

        for label, combo in [("Formato", self.format_combo), ("Período", self.period_combo),
                              ("Torneio", self.tournament_combo)]:
            box = QVBoxLayout()
            box.setSpacing(3)
            lbl = QLabel(label.upper())
            lbl.setObjectName("sectionHint")
            box.addWidget(lbl)
            box.addWidget(combo)
            filters.addLayout(box)
        filters.addStretch()
        outer.addLayout(filters)

        self.format_combo.currentIndexChanged.connect(self._apply_filters)
        self.period_combo.currentIndexChanged.connect(self._apply_filters)
        self.tournament_combo.currentIndexChanged.connect(self._apply_filters)

        self.kpi_row = QHBoxLayout()
        self.kpi_row.setSpacing(16)
        outer.addLayout(self.kpi_row)

        chart_box = QFrame()
        chart_box.setObjectName("surface")
        chart_layout = QVBoxLayout(chart_box)
        chart_layout.setContentsMargins(18, 14, 18, 14)
        chart_title = QLabel("DISTRIBUIÇÃO DO META (TOP 8)")
        chart_title.setObjectName("sectionLabel")
        chart_layout.addWidget(chart_title)
        self.meta_chart = BarChart()
        self.meta_chart.setMinimumHeight(180)
        self.meta_chart.setMaximumHeight(220)
        chart_layout.addWidget(self.meta_chart)
        outer.addWidget(chart_box)

        table_box = QFrame()
        table_box.setObjectName("surface")
        table_layout = QVBoxLayout(table_box)
        table_layout.setContentsMargins(16, 14, 16, 14)
        table_title = QLabel("RANKING DE DECKS")
        table_title.setObjectName("sectionLabel")
        table_layout.addWidget(table_title)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Rank", "Deck", "Participação", "Meta Usage", "Top 8", "Win Rate"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.cellDoubleClicked.connect(self._on_row_activated)
        table_layout.addWidget(self.table)

        self.empty_label = QLabel("Nenhum resultado para os filtros selecionados.")
        self.empty_label.setObjectName("sectionHint")
        self.empty_label.hide()
        table_layout.addWidget(self.empty_label)

        hint = QLabel("Clique duas vezes em um deck para ver a lista completa de cartas.")
        hint.setObjectName("sectionHint")
        table_layout.addWidget(hint)

        outer.addWidget(table_box, 1)

    def refresh(self):
        if not self._populated_filters:
            self._populate_filters()
            self._populated_filters = True
        self._apply_filters()

    def _populate_filters(self):
        entries = self.repo.meta_entries

        self.format_combo.blockSignals(True)
        self.format_combo.addItem("Todos", None)
        for fmt in available_formats(entries):
            self.format_combo.addItem(fmt, fmt)
        self.format_combo.blockSignals(False)

        self.tournament_combo.blockSignals(True)
        self.tournament_combo.addItem("Todos", None)
        tournaments_by_id = {t["tournament_id"]: t for t in self.repo.tournaments}
        for tid, _date in available_tournaments(entries):
            t = tournaments_by_id.get(tid)
            label = t["name"] if t else tid
            self.tournament_combo.addItem(label, tid)
        self.tournament_combo.blockSignals(False)

    def _apply_filters(self):
        entries = self.repo.meta_entries
        if not entries:
            # No real per-entry data collected yet (synthetic/mock dataset) —
            # fall back to the static pre-computed snapshot in meta.json.
            self._render_from_snapshot(self.repo.meta)
            return

        result = aggregate(
            entries,
            period_days=self.period_combo.currentData(),
            fmt=self.format_combo.currentData(),
            tournament_id=self.tournament_combo.currentData(),
        )
        self._render(result)

    def _render_from_snapshot(self, meta):
        self._render({
            "deck_ranking": meta.get("deck_ranking", []),
            "decks_analyzed": meta.get("decks_analyzed", 0),
            "tournaments": meta.get("tournaments", 0),
            "top8_total": meta.get("top8_total", 0),
            "avg_win_rate": meta.get("avg_win_rate", 0),
        })

    def _render(self, result):
        self._clear_layout(self.kpi_row)
        kpis = [
            ("Decks analisados", f'{result.get("decks_analyzed", 0):,}'.replace(",", "."), "#2388FF"),
            ("Torneios", str(result.get("tournaments", 0)), "#22C55E"),
            ("Top 8", str(result.get("top8_total", 0)), "#EAB308"),
            ("Win Rate médio", f'{result.get("avg_win_rate", 0)}%', "#EF4444"),
        ]
        for label, value, color in kpis:
            self.kpi_row.addWidget(KpiCard(label, value, color))

        ranking = result.get("deck_ranking", [])
        self.table.setVisible(bool(ranking))
        self.empty_label.setVisible(not ranking)
        self.table.setRowCount(len(ranking))
        for row, entry in enumerate(ranking):
            rank_item = QTableWidgetItem(str(entry["rank"]))
            if entry["rank"] in RANK_COLORS:
                rank_item.setForeground(QColor(RANK_COLORS[entry["rank"]]))
                font = rank_item.font()
                font.setBold(True)
                rank_item.setFont(font)
            self.table.setItem(row, 0, rank_item)
            self.table.setItem(row, 1, QTableWidgetItem(entry["name"]))
            self.table.setItem(row, 2, QTableWidgetItem(str(entry.get("entries", 0))))
            self.table.setItem(row, 3, QTableWidgetItem(f'{entry["meta_usage"]}%'))
            self.table.setItem(row, 4, QTableWidgetItem(f'{entry["top8"]}%'))
            self.table.setItem(row, 5, QTableWidgetItem(f'{entry["win_rate"]}%'))
            self.table.item(row, 0).setData(Qt.UserRole, entry["deck_id"])

        self._build_chart(ranking)

    def _build_chart(self, ranking):
        top = ranking[:8]
        if not top:
            self.meta_chart.clear_chart()
            return
        labels = [entry["name"] for entry in top]
        values = [entry["meta_usage"] for entry in top]
        colors = ["#2388FF"] * len(top)
        for i, entry in enumerate(top):
            if entry["rank"] in RANK_COLORS:
                colors[i] = RANK_COLORS[entry["rank"]]
        self.meta_chart.plot_bars(labels, values, colors)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _on_row_activated(self, row, _col):
        item = self.table.item(row, 0)
        if not item:
            return
        deck_id = item.data(Qt.UserRole)
        deck = self.repo.deck(deck_id)
        if not deck:
            return
        dlg = DeckDetailDialog(deck, self.repo, self.banlist, self.settings, parent=self)
        dlg.exec()
