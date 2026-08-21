"""Single, reusable card-detail dialog used everywhere the app needs to show
a card plus its real competitive-presence data and let the user set (or
clear) its restriction tier.

Shows Meta Usage / Top Cut / Dominance exactly as collected — no aggregate
score, no suggested restriction. Language stays neutral ('Strong Meta
Usage', not 'should be banned'): the decision is always the user's."""
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QWidget, QScrollArea
)

from app.components.image_loader import load_card_pixmap
from app.components.metric_bar import MetricBar, INDICATOR_FIELDS, presence_notes
from core.banlist_manager import RESTRICTION_META, RESTRICTIONS


class CardDetailDialog(QDialog):
    restriction_changed = Signal()

    def __init__(self, card: dict, repo, banlist_manager, settings_manager, parent=None):
        super().__init__(parent)
        self.card = card
        self.card_id = card["card_id"]
        self.repo = repo
        self.banlist = banlist_manager
        self.settings = settings_manager

        self.setWindowTitle(f'{self.card_id} · {card.get("name","")}')
        self.setMinimumSize(760, 620)
        self.setStyleSheet("QDialog { background-color: #070B12; }")

        root = QHBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(22)

        # ---- Left: card art + identity ----
        left = QVBoxLayout()
        left.setSpacing(10)
        img = QLabel()
        img.setPixmap(load_card_pixmap(self.card_id, QSize(240, 336)))
        left.addWidget(img)

        id_label = QLabel(self.card_id)
        id_label.setStyleSheet("color: #2388FF; font-weight: 800; font-size: 13px;")
        left.addWidget(id_label)
        name_label = QLabel(card.get("name", ""))
        name_label.setStyleSheet("font-size: 19px; font-weight: 800;")
        name_label.setWordWrap(True)
        left.addWidget(name_label)
        meta_label = QLabel(
            f'{card.get("color","")} · Lv.{card.get("level") or "-"} · '
            f'{card.get("type","")} · {card.get("rarity","")} · {card.get("set","")}'
        )
        meta_label.setStyleSheet("color: #64748B; font-size: 11px;")
        meta_label.setWordWrap(True)
        left.addWidget(meta_label)
        left.addStretch()
        root.addLayout(left)

        # ---- Right: scrollable indicators + restriction controls ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        right_content = QWidget()
        right = QVBoxLayout(right_content)
        right.setSpacing(16)

        candidate = self.repo.ban_candidate(self.card_id)
        if candidate:
            indicators_title = QLabel("COMPETITIVE PRESENCE")
            indicators_title.setObjectName("sectionLabel")
            right.addWidget(indicators_title)

            for key, label in INDICATOR_FIELDS:
                right.addWidget(MetricBar(label, candidate.get(key, 0.0)))

            notes = presence_notes(candidate)
            if notes:
                notes_row = QHBoxLayout()
                notes_row.setSpacing(6)
                for note in notes:
                    chip = QLabel(note)
                    chip.setObjectName("presenceChip")
                    notes_row.addWidget(chip)
                notes_row.addStretch()
                right.addLayout(notes_row)
        else:
            no_data = QLabel("Sem dados de meta competitivo para esta carta.")
            no_data.setObjectName("sectionHint")
            right.addWidget(no_data)

        divider = QFrame()
        divider.setObjectName("sidebarDivider")
        divider.setFixedHeight(1)
        right.addWidget(divider)

        # ---- Restriction selector ----
        restriction_title = QLabel("RESTRICTION")
        restriction_title.setObjectName("sectionLabel")
        right.addWidget(restriction_title)

        current = self.banlist.restriction_of(self.card_id)
        self.status_label = QLabel()
        self._update_status_label(current)
        right.addWidget(self.status_label)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.action_buttons = {}

        unlimited_btn = QPushButton("Unlimited")
        unlimited_btn.setCheckable(True)
        unlimited_btn.setChecked(current is None)
        unlimited_btn.clicked.connect(self._remove_restriction)
        actions.addWidget(unlimited_btn)
        self.unlimited_btn = unlimited_btn

        for restriction in ["LIMIT_3", "LIMIT_2", "LIMIT_1", "BAN"]:
            meta = RESTRICTION_META[restriction]
            btn = QPushButton(f'{meta["icon"]} {meta["label"]}')
            btn.setCheckable(True)
            btn.setChecked(current == restriction)
            btn.clicked.connect(lambda _, r=restriction: self._apply_restriction(r))
            actions.addWidget(btn)
            self.action_buttons[restriction] = btn
        right.addLayout(actions)

        note = QLabel(
            "A decisão de restringir uma carta é sempre sua (ou da sua comunidade) — "
            "esta tela mostra os dados reais, não uma recomendação."
        )
        note.setObjectName("sectionHint")
        note.setWordWrap(True)
        right.addWidget(note)

        right.addStretch()
        scroll.setWidget(right_content)
        root.addWidget(scroll, 1)

    def _update_status_label(self, restriction):
        if restriction:
            meta = RESTRICTION_META[restriction]
            self.status_label.setText(f'Status atual: {meta["icon"]} {meta["label"]}')
            self.status_label.setStyleSheet(f"color: {meta['color']}; font-weight: 700; font-size: 12px;")
        else:
            self.status_label.setText("Status atual: Unlimited (sem restrição)")
            self.status_label.setStyleSheet("color: #64748B; font-weight: 700; font-size: 12px;")

    def _apply_restriction(self, restriction):
        self.banlist.set_restriction(self.card_id, restriction, reason="Definido via análise de carta")
        self.unlimited_btn.setChecked(False)
        for r, btn in self.action_buttons.items():
            btn.setChecked(r == restriction)
        self._update_status_label(restriction)
        self.restriction_changed.emit()

    def _remove_restriction(self):
        self.banlist.remove(self.card_id)
        self.unlimited_btn.setChecked(True)
        for btn in self.action_buttons.values():
            btn.setChecked(False)
        self._update_status_label(None)
        self.restriction_changed.emit()
