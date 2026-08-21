from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea, QPushButton,
    QLineEdit, QComboBox, QTextEdit, QDateEdit
)
from PySide6.QtCore import QDate

from app.components.metric_bar import MetricInline, INDICATOR_FIELDS
from core.banlist_manager import RESTRICTION_META

RESTRICTION_TIMELINE_META = {
    **RESTRICTION_META,
    "REMOVED": {"label": "Removido da Ban List", "color": "#94A3B8", "icon": "⚪", "max_copies": None},
}
UNLIMITED_LABEL = "Unlimited"


class HistoryPage(QWidget):
    navigate_requested = Signal(str)

    def __init__(self, repo, banlist, settings, analyzer, db, updater, collection=None, deckbuilder=None, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.banlist = banlist
        self.db = db

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 24)
        outer.setSpacing(16)

        header_row = QHBoxLayout()
        header_col = QVBoxLayout()
        header_col.setSpacing(2)
        title = QLabel("LINHA DO TEMPO")
        title.setObjectName("sectionLabel")
        header_col.addWidget(title)
        subtitle = QLabel("Todo ajuste na Ban List fica registrado aqui.")
        subtitle.setObjectName("sectionHint")
        header_col.addWidget(subtitle)
        header_row.addLayout(header_col)
        header_row.addStretch()
        self.add_btn = QPushButton("+ Adicionar observação")
        self.add_btn.setObjectName("primaryButton")
        self.add_btn.clicked.connect(self._toggle_form)
        header_row.addWidget(self.add_btn)
        outer.addLayout(header_row)

        self.form_box = self._build_form()
        self.form_box.hide()
        outer.addWidget(self.form_box)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self.timeline_content = QWidget()
        self.timeline_layout = QVBoxLayout(self.timeline_content)
        self.timeline_layout.setSpacing(4)
        scroll.setWidget(self.timeline_content)
        outer.addWidget(scroll, 1)

    def _build_form(self):
        box = QFrame()
        box.setObjectName("surface")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        row1 = QHBoxLayout()
        self.card_input = QLineEdit()
        self.card_input.setPlaceholderText("Card ID (ex: BT25-082)")
        row1.addWidget(self.card_input, 1)

        self.restriction_combo = QComboBox()
        for r in list(RESTRICTION_META.keys()):
            self.restriction_combo.addItem(RESTRICTION_META[r]["label"], r)
        row1.addWidget(self.restriction_combo)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        row1.addWidget(self.date_edit)
        layout.addLayout(row1)

        self.note_input = QTextEdit()
        self.note_input.setPlaceholderText("Observação / motivo...")
        self.note_input.setFixedHeight(60)
        layout.addWidget(self.note_input)

        save_btn = QPushButton("Salvar observação")
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self._save_entry)
        layout.addWidget(save_btn, alignment=Qt.AlignRight)
        return box

    def _toggle_form(self):
        self.form_box.setVisible(not self.form_box.isVisible())

    def _save_entry(self):
        card_id = self.card_input.text().strip().upper()
        if not card_id:
            return
        restriction = self.restriction_combo.currentData()
        note = self.note_input.toPlainText().strip()
        date_str = self.date_edit.date().toString("yyyy-MM-dd") + " 00:00:00"
        self.db.add_history(card_id, restriction, reason="Observação manual", note=note, date=date_str)
        self.card_input.clear()
        self.note_input.clear()
        self.form_box.hide()
        self.refresh()

    def refresh(self):
        while self.timeline_layout.count():
            item = self.timeline_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        entries = self.db.get_history()
        if not entries:
            empty = QLabel("Nenhum evento registrado ainda.")
            empty.setStyleSheet("color: #64748B;")
            self.timeline_layout.addWidget(empty)
            self.timeline_layout.addStretch()
            return

        last_date = None
        for i, entry in enumerate(entries):
            date_only = entry["date"].split(" ")[0]
            if date_only != last_date:
                date_label = QLabel(self._format_date(date_only))
                date_label.setStyleSheet("color: #64748B; font-size: 11px; font-weight: 700; margin-top: 10px;")
                self.timeline_layout.addWidget(date_label)
                last_date = date_only

            meta = RESTRICTION_TIMELINE_META.get(entry["restriction"], RESTRICTION_TIMELINE_META["REMOVED"])
            row = QFrame()
            row.setObjectName("surface")
            row.setStyleSheet(
                f"QFrame#surface {{ background-color: #0D1622; border: 1px solid #1B2A3A; "
                f"border-left: 3px solid {meta['color']}; border-radius: 14px; }}"
            )
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(14, 10, 14, 10)
            row_layout.setSpacing(2)

            top = QHBoxLayout()
            badge = QLabel(f'{meta["icon"]} {entry["card_id"]}')
            badge.setStyleSheet(f'color: {meta["color"]}; font-weight: 800; font-size: 13px;')
            top.addWidget(badge)
            top.addStretch()
            status = QLabel(meta["label"].upper())
            status.setStyleSheet(f'color: {meta["color"]}; font-weight: 700; font-size: 11px;')
            top.addWidget(status)
            row_layout.addLayout(top)

            # "From -> To": the prior state is derived from the next-older
            # real history row for this same card — no invented history,
            # just reading the chronological record already on disk.
            prior_restriction = self._prior_restriction(entries, i, entry["card_id"])
            from_label = RESTRICTION_META.get(prior_restriction, {}).get("label", UNLIMITED_LABEL)
            to_label = RESTRICTION_META.get(entry["restriction"], {}).get("label", UNLIMITED_LABEL)
            transition = QLabel(f"{from_label} → {to_label}")
            transition.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600;")
            row_layout.addWidget(transition)

            candidate = self.repo.ban_candidate(entry["card_id"])
            if candidate:
                indicators_row = QHBoxLayout()
                indicators_row.setSpacing(14)
                for key, label in INDICATOR_FIELDS:
                    indicators_row.addWidget(MetricInline(label, candidate.get(key, 0.0)))
                indicators_row.addStretch()
                row_layout.addLayout(indicators_row)

            if entry.get("note"):
                note = QLabel(entry["note"])
                note.setStyleSheet("color: #94A3B8; font-size: 11px;")
                note.setWordWrap(True)
                row_layout.addWidget(note)
            if entry.get("reason"):
                reason = QLabel(f'Motivo: {entry["reason"]}')
                reason.setStyleSheet("color: #475569; font-size: 10px;")
                row_layout.addWidget(reason)

            self.timeline_layout.addWidget(row)

        self.timeline_layout.addStretch()

    @staticmethod
    def _prior_restriction(entries, index, card_id):
        """entries is ordered most-recent-first; the prior state is the
        restriction from the next OLDER row for this same card, if any."""
        for older in entries[index + 1:]:
            if older["card_id"] == card_id:
                return older["restriction"] if older["restriction"] != "REMOVED" else None
        return None

    def _format_date(self, date_str):
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            months = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]
            return f"{d.day:02d} {months[d.month-1]} {d.year}"
        except ValueError:
            return date_str
