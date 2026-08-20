from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QLabel, QTabWidget, QFrame, QScrollArea, QGridLayout
)

from app.components.ban_risk_detail_dialog import BanRiskDetailDialog
from app.components.ban_score_bar import _color_for_value


class AnalysisPage(QWidget):
    navigate_requested = Signal(str)

    def __init__(self, repo, banlist, settings, analyzer, db, updater, collection=None, deckbuilder=None, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.banlist = banlist
        self.settings = settings
        self.analyzer = analyzer

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 24)
        outer.setSpacing(14)

        header_col = QVBoxLayout()
        header_col.setSpacing(2)
        title = QLabel("BAN RISK ANALYSIS")
        title.setObjectName("sectionLabel")
        header_col.addWidget(title)
        subtitle = QLabel("Clique duas vezes numa carta para investigar por que ela está no radar.")
        subtitle.setObjectName("sectionHint")
        header_col.addWidget(subtitle)
        outer.addLayout(header_col)

        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)

        # ---- Ban Risk tab ----
        self.risk_table = QTableWidget()
        self.risk_table.setColumnCount(8)
        self.risk_table.setHorizontalHeaderLabels(
            ["Card", "Meta Usage", "Top Cut", "Avg Copies", "Growth", "Dominance", "Ban Score", "Risk"]
        )
        self.risk_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.risk_table.verticalHeader().setVisible(False)
        self.risk_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.risk_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.risk_table.setAlternatingRowColors(True)
        self.risk_table.cellDoubleClicked.connect(self._on_row_activated)
        self.tabs.addTab(self.risk_table, "Ban Risk")

        # ---- Engine Detection tab ----
        engine_scroll = QScrollArea()
        engine_scroll.setWidgetResizable(True)
        engine_scroll.setFrameShape(QFrame.NoFrame)
        engine_content = QWidget()
        self.engine_layout = QVBoxLayout(engine_content)
        self.engine_layout.setSpacing(12)
        engine_scroll.setWidget(engine_content)
        self.tabs.addTab(engine_scroll, "Engine Detection")

    def refresh(self):
        rows = self.analyzer.ban_risk_table(self.settings.get("ban_score_weights"))
        self.risk_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            card = row["card"]
            self.risk_table.setItem(i, 0, QTableWidgetItem(f'{card["card_id"]} · {card.get("name","")}'))
            self.risk_table.setItem(i, 1, QTableWidgetItem(f'{row["meta_usage"]}%'))
            self.risk_table.setItem(i, 2, QTableWidgetItem(f'{row["top_cut"]}%'))
            self.risk_table.setItem(i, 3, QTableWidgetItem(str(row["avg_copies"])))
            self.risk_table.setItem(i, 4, QTableWidgetItem(f'{"+" if row["growth"]>=0 else ""}{row["growth"]}%'))
            self.risk_table.setItem(i, 5, QTableWidgetItem(f'{row["dominance"]}%'))

            score_item = QTableWidgetItem(str(row["ban_score"]))
            score_item.setForeground(Qt.GlobalColor.white)
            self.risk_table.setItem(i, 6, score_item)

            risk_item = QTableWidgetItem(f'{row["risk_icon"]} {row["risk_label"]}')
            self.risk_table.setItem(i, 7, risk_item)

            self.risk_table.item(i, 0).setData(Qt.UserRole, row)

        self._build_engine_detection()

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
        item = self.risk_table.item(row, 0)
        if not item:
            return
        candidate = item.data(Qt.UserRole)
        if not candidate:
            return
        dlg = BanRiskDetailDialog(candidate, self.repo, self.banlist, self.settings, parent=self)
        dlg.restriction_changed.connect(self.refresh)
        dlg.exec()
