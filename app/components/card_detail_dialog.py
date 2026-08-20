from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QWidget, QScrollArea
)

from app.components.image_loader import load_card_pixmap
from app.components.ban_score_bar import BanScoreGauge, FactorBar
from core.ban_score import compute_ban_score, score_breakdown, risk_for_score
from core.banlist_manager import RESTRICTION_META


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
        self.setMinimumSize(680, 560)
        self.setStyleSheet("QDialog { background-color: #070B12; }")

        root = QHBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(20)

        # Left: image
        left = QVBoxLayout()
        img = QLabel()
        img.setPixmap(load_card_pixmap(self.card_id, QSize(240, 336)))
        left.addWidget(img)
        left.addStretch()
        root.addLayout(left)

        # Right: scrollable details
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        right_content = QWidget()
        right = QVBoxLayout(right_content)
        right.setSpacing(14)

        id_label = QLabel(self.card_id)
        id_label.setStyleSheet("color: #2388FF; font-weight: 800; font-size: 14px;")
        right.addWidget(id_label)

        name_label = QLabel(card.get("name", ""))
        name_label.setStyleSheet("font-size: 22px; font-weight: 800;")
        name_label.setWordWrap(True)
        right.addWidget(name_label)

        info_grid = QHBoxLayout()
        for key, label in [("color", "Cor"), ("level", "Level"), ("rarity", "Raridade"), ("set", "Set")]:
            box = QVBoxLayout()
            lbl = QLabel(label.upper())
            lbl.setStyleSheet("color: #64748B; font-size: 10px; font-weight: 700;")
            val = QLabel(str(card.get(key) or "-"))
            val.setStyleSheet("font-size: 14px; font-weight: 700;")
            box.addWidget(lbl)
            box.addWidget(val)
            info_grid.addLayout(box)
        right.addLayout(info_grid)

        divider = QFrame()
        divider.setObjectName("sidebarDivider")
        divider.setFixedHeight(1)
        right.addWidget(divider)

        candidate = self.repo.ban_candidate(self.card_id)
        if candidate:
            meta_grid = QHBoxLayout()
            for key, label, suffix in [
                ("meta_usage", "Meta Usage", "%"),
                ("top_cut", "Top Cut", "%"),
                ("avg_copies", "Average Copies", ""),
            ]:
                box = QVBoxLayout()
                lbl = QLabel(label.upper())
                lbl.setStyleSheet("color: #64748B; font-size: 10px; font-weight: 700;")
                val = QLabel(f"{candidate.get(key, 0)}{suffix}")
                val.setStyleSheet("font-size: 16px; font-weight: 800; color: #F8FAFC;")
                box.addWidget(lbl)
                box.addWidget(val)
                meta_grid.addLayout(box)
            right.addLayout(meta_grid)

            weights = self.settings.get("ban_score_weights")
            score = compute_ban_score(candidate, weights)
            label, icon = risk_for_score(score)
            gauge = BanScoreGauge(score, label, icon)
            right.addWidget(gauge)

            for f_label, value, weight in score_breakdown(candidate, weights):
                right.addWidget(FactorBar(f_label, value, weight))
        else:
            no_data = QLabel("Sem dados de meta para esta carta.")
            no_data.setStyleSheet("color: #64748B;")
            right.addWidget(no_data)

        right.addWidget(divider if False else QFrame())

        current = self.banlist.restriction_of(self.card_id)
        status_label = QLabel()
        self._update_status_label(status_label, current)
        right.addWidget(status_label)
        self.status_label = status_label

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.action_buttons = {}
        for restriction in ["BAN", "LIMIT_1", "LIMIT_2", "LIMIT_3"]:
            meta = RESTRICTION_META[restriction]
            btn = QPushButton(f'{meta["icon"]} {meta["label"] if restriction=="BAN" else "Limitar a " + str(meta["max_copies"])}')
            btn.setCheckable(True)
            btn.setChecked(current == restriction)
            btn.clicked.connect(lambda _, r=restriction: self._apply_restriction(r))
            actions.addWidget(btn)
            self.action_buttons[restriction] = btn
        right.addLayout(actions)

        remove_btn = QPushButton("Remover da Ban List")
        remove_btn.setObjectName("dangerButton")
        remove_btn.setVisible(current is not None)
        remove_btn.clicked.connect(self._remove_restriction)
        right.addWidget(remove_btn)
        self.remove_btn = remove_btn

        right.addStretch()
        scroll.setWidget(right_content)
        root.addWidget(scroll, 1)

    def _update_status_label(self, label: QLabel, restriction):
        if restriction:
            meta = RESTRICTION_META[restriction]
            label.setText(f'Status atual: {meta["icon"]} {meta["label"]}')
            label.setStyleSheet(f"color: {meta['color']}; font-weight: 700;")
        else:
            label.setText("Status atual: Sem restrição")
            label.setStyleSheet("color: #64748B; font-weight: 700;")

    def _apply_restriction(self, restriction):
        self.banlist.set_restriction(self.card_id, restriction, reason="Definido manualmente")
        for r, btn in self.action_buttons.items():
            btn.setChecked(r == restriction)
        self._update_status_label(self.status_label, restriction)
        self.remove_btn.setVisible(True)
        self.restriction_changed.emit()

    def _remove_restriction(self):
        self.banlist.remove(self.card_id)
        for btn in self.action_buttons.values():
            btn.setChecked(False)
        self._update_status_label(self.status_label, None)
        self.remove_btn.setVisible(False)
        self.restriction_changed.emit()
