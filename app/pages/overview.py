"""Overview — a factual, non-evaluative snapshot of the system: how many
decks/tournaments/cards are tracked, how the meta is distributed, the
current state of the Ban List, real activity over time, and the most
recent restriction changes. No health score, no fun score, no candidate
ranking — just numbers the app already has, presented plainly."""
from collections import defaultdict
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame, QPushButton

from app.components.kpi_card import KpiCard
from app.components.charts import BarChart, TrendChart
from core.banlist_manager import RESTRICTION_META, RESTRICTIONS

RANK_COLORS = {1: "#EAB308", 2: "#94A3B8", 3: "#B45309"}


class OverviewPage(QWidget):
    navigate_requested = Signal(str)

    def __init__(self, repo, banlist, settings, analyzer, db, updater, collection=None, deckbuilder=None, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.banlist = banlist
        self.db = db

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        self.layout_ = QVBoxLayout(content)
        self.layout_.setContentsMargins(24, 20, 24, 24)
        self.layout_.setSpacing(18)
        scroll.setWidget(content)

        header_col = QVBoxLayout()
        header_col.setSpacing(2)
        title = QLabel("OVERVIEW")
        title.setObjectName("sectionLabel")
        header_col.addWidget(title)
        subtitle = QLabel("Community Format · panorama factual do meta e da Ban List")
        subtitle.setObjectName("sectionHint")
        header_col.addWidget(subtitle)
        self.layout_.addLayout(header_col)

        self.kpi_row = QHBoxLayout()
        self.kpi_row.setSpacing(16)
        self.layout_.addLayout(self.kpi_row)

        # META DISTRIBUTION + CURRENT BAN LIST, side by side
        top_row = QHBoxLayout()
        top_row.setSpacing(16)

        self.distribution_box = QFrame()
        self.distribution_box.setObjectName("surface")
        self.distribution_layout = QVBoxLayout(self.distribution_box)
        self.distribution_layout.setContentsMargins(18, 14, 18, 14)
        top_row.addWidget(self.distribution_box, 2)

        self.banlist_box = QFrame()
        self.banlist_box.setObjectName("surface")
        self.banlist_layout = QVBoxLayout(self.banlist_box)
        self.banlist_layout.setContentsMargins(18, 14, 18, 14)
        top_row.addWidget(self.banlist_box, 1)

        self.layout_.addLayout(top_row)

        # META ACTIVITY
        activity_box = QFrame()
        activity_box.setObjectName("surface")
        activity_layout = QVBoxLayout(activity_box)
        activity_layout.setContentsMargins(18, 16, 18, 16)
        activity_title = QLabel("META ACTIVITY")
        activity_title.setObjectName("sectionLabel")
        activity_layout.addWidget(activity_title)
        activity_hint = QLabel("Participações registradas por semana, com base nos torneios coletados.")
        activity_hint.setObjectName("sectionHint")
        activity_layout.addWidget(activity_hint)
        self.activity_chart = TrendChart()
        self.activity_chart.setMinimumHeight(200)
        activity_layout.addWidget(self.activity_chart)
        self.layout_.addWidget(activity_box)

        # RECENT ACTIVITY
        self.recent_box = QFrame()
        self.recent_box.setObjectName("surface")
        self.recent_layout = QVBoxLayout(self.recent_box)
        self.recent_layout.setContentsMargins(18, 14, 18, 14)
        self.layout_.addWidget(self.recent_box)

    def refresh(self):
        meta = self.repo.meta
        counts = self.banlist.counts()

        self._build_kpi_row(meta, counts)
        self._build_distribution(meta)
        self._build_ban_list_summary(counts)
        self._build_activity(self.repo.meta_entries)
        self._build_recent_activity()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _build_kpi_row(self, meta, counts):
        self._clear_layout(self.kpi_row)
        kpis = [
            ("Decks Analisados", f'{meta.get("decks_analyzed", 0):,}'.replace(",", "."), "#2388FF"),
            ("Torneios", str(meta.get("tournaments", 0)), "#22C55E"),
            ("Cartas no Catálogo", f'{len(self.repo.cards):,}'.replace(",", "."), "#EAB308"),
            ("Cartas Restritas", str(sum(counts.values())), "#F97316"),
        ]
        for label, value, color in kpis:
            self.kpi_row.addWidget(KpiCard(label, value, color))

    def _build_distribution(self, meta):
        self._clear_layout(self.distribution_layout)
        title = QLabel("META DISTRIBUTION")
        title.setObjectName("sectionLabel")
        self.distribution_layout.addWidget(title)

        ranking = meta.get("deck_ranking", [])[:8]
        if not ranking:
            empty = QLabel("Sem dados de meta coletados ainda.")
            empty.setObjectName("sectionHint")
            self.distribution_layout.addWidget(empty)
            return

        chart = BarChart()
        chart.setMinimumHeight(180)
        chart.setMaximumHeight(220)
        labels = [entry["name"] for entry in ranking]
        values = [entry["meta_usage"] for entry in ranking]
        colors = ["#2388FF"] * len(ranking)
        for i, entry in enumerate(ranking):
            if entry.get("rank") in RANK_COLORS:
                colors[i] = RANK_COLORS[entry["rank"]]
        chart.plot_bars(labels, values, colors)
        self.distribution_layout.addWidget(chart)

        view_btn = QPushButton("Ver Meta Lab completo →")
        view_btn.clicked.connect(lambda: self.navigate_requested.emit("meta"))
        self.distribution_layout.addWidget(view_btn)

    def _build_ban_list_summary(self, counts):
        self._clear_layout(self.banlist_layout)
        title = QLabel("CURRENT BAN LIST")
        title.setObjectName("sectionLabel")
        self.banlist_layout.addWidget(title)
        self.banlist_layout.addSpacing(8)

        for restriction in RESTRICTIONS:
            meta = RESTRICTION_META[restriction]
            row = QHBoxLayout()
            row.setSpacing(8)
            dot = QLabel(meta["icon"])
            row.addWidget(dot)
            label = QLabel(meta["label"].upper())
            label.setStyleSheet(f'color: {meta["color"]}; font-size: 11.5px; font-weight: 700;')
            row.addWidget(label)
            row.addStretch()
            count = QLabel(str(counts.get(restriction, 0)))
            count.setStyleSheet(f'color: {meta["color"]}; font-size: 14px; font-weight: 800;')
            row.addWidget(count)
            self.banlist_layout.addLayout(row)

        self.banlist_layout.addSpacing(6)
        view_btn = QPushButton("Ver Ban List completa →")
        view_btn.clicked.connect(lambda: self.navigate_requested.emit("ban_list"))
        self.banlist_layout.addWidget(view_btn)
        self.banlist_layout.addStretch()

    def _build_activity(self, entries):
        if not entries:
            self.activity_chart.clear_chart()
            return

        # Real activity over time: how many tournament entries were
        # collected per ISO week. Not a per-card usage trend (the collector
        # doesn't have repeated historical snapshots for that yet) — this is
        # simply the real submission volume over time.
        buckets = defaultdict(int)
        for e in entries:
            date_str = e.get("date")
            if not date_str:
                continue
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                continue
            year, week, _ = d.isocalendar()
            buckets[(year, week)] += 1

        if not buckets:
            self.activity_chart.clear_chart()
            return

        keys = sorted(buckets.keys())[-16:]  # most recent 16 weeks, to stay legible
        labels = [f"S{week}/{year % 100}" for year, week in keys]
        values = [buckets[k] for k in keys]
        self.activity_chart.plot_series(labels, {"Participações": values})

    def _build_recent_activity(self):
        self._clear_layout(self.recent_layout)
        title = QLabel("RECENT ACTIVITY")
        title.setObjectName("sectionLabel")
        self.recent_layout.addWidget(title)
        self.recent_layout.addSpacing(6)

        entries = self.db.get_history()[:5]
        if not entries:
            empty = QLabel("Nenhuma alteração registrada na Ban List ainda.")
            empty.setObjectName("sectionHint")
            self.recent_layout.addWidget(empty)
            return

        for entry in entries:
            row = QHBoxLayout()
            row.setSpacing(10)
            meta = RESTRICTION_META.get(entry["restriction"])
            icon = meta["icon"] if meta else "⚪"
            color = meta["color"] if meta else "#94A3B8"
            label = meta["label"] if meta else "Removido"

            badge = QLabel(f'{icon} {entry["card_id"]}')
            badge.setStyleSheet(f'color: {color}; font-weight: 700; font-size: 12px;')
            row.addWidget(badge)

            status = QLabel(f'→ {label}')
            status.setStyleSheet(f'color: {color}; font-size: 11px;')
            row.addWidget(status)
            row.addStretch()

            date_label = QLabel(entry["date"].split(" ")[0])
            date_label.setStyleSheet("color: #64748B; font-size: 10.5px;")
            row.addWidget(date_label)

            self.recent_layout.addLayout(row)

        view_btn = QPushButton("Ver histórico completo →")
        view_btn.clicked.connect(lambda: self.navigate_requested.emit("history"))
        self.recent_layout.addSpacing(6)
        self.recent_layout.addWidget(view_btn)
