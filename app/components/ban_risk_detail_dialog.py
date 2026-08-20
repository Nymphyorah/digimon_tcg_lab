"""Detailed Ban Risk panel for the Análise page.

Shows the full breakdown behind a card's Ban Score and a plain-language
'why is this problematic' summary, both derived entirely from data already
computed by core/ban_score.py — no new calculations are introduced here.
Also includes a restriction selector wired to the existing Ban List manager,
with an explicit note that impact simulation isn't implemented yet (per
project rule: never fabricate numbers the engine doesn't actually produce).
"""
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QWidget, QScrollArea
)

from app.components.image_loader import load_card_pixmap
from app.components.ban_score_bar import BanScoreGauge, FactorBar, _color_for_value
from core.ban_score import compute_ban_score, score_breakdown, risk_for_score
from core.banlist_manager import RESTRICTION_META

# Which score_breakdown() factors count as "why is this problematic" reasons,
# and the plain-language phrase to show when that factor is high (>= 70/100).
PROBLEM_REASONS = {
    "Meta Usage": "ALTA PRESENÇA NO META",
    "Top Cut": "ALTO TOP CUT",
    "Performance": "ALTA DOMINÂNCIA EM COLOCAÇÕES",
    "Growth": "CRESCIMENTO ACELERADO",
}
HIGH_THRESHOLD = 70


class BanRiskDetailDialog(QDialog):
    restriction_changed = Signal()

    def __init__(self, candidate: dict, repo, banlist_manager, settings_manager, parent=None):
        super().__init__(parent)
        self.candidate = candidate
        self.card = candidate["card"]
        self.card_id = self.card["card_id"]
        self.repo = repo
        self.banlist = banlist_manager
        self.settings = settings_manager

        self.setWindowTitle(f'Análise · {self.card_id} · {self.card.get("name","")}')
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
        name_label = QLabel(self.card.get("name", ""))
        name_label.setStyleSheet("font-size: 19px; font-weight: 800;")
        name_label.setWordWrap(True)
        left.addWidget(name_label)
        meta_label = QLabel(
            f'{self.card.get("color","")} · Lv.{self.card.get("level") or "-"} · '
            f'{self.card.get("rarity","")} · {self.card.get("set","")}'
        )
        meta_label.setStyleSheet("color: #64748B; font-size: 11px;")
        meta_label.setWordWrap(True)
        left.addWidget(meta_label)
        left.addStretch()
        root.addLayout(left)

        # ---- Right: scrollable analysis ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        right_content = QWidget()
        right = QVBoxLayout(right_content)
        right.setSpacing(16)

        weights = self.settings.get("ban_score_weights")
        score = compute_ban_score(candidate, weights)
        risk_label, risk_icon = risk_for_score(score)

        # Stats row
        stats_row = QHBoxLayout()
        for key, label, suffix in [
            ("meta_usage", "Meta Usage", "%"), ("top_cut", "Top Cut", "%"),
            ("avg_copies", "Avg Copies", ""), ("growth", "Growth", "%"),
            ("dominance", "Dominance", "%"),
        ]:
            box = QVBoxLayout()
            box.setSpacing(2)
            lbl = QLabel(label.upper())
            lbl.setObjectName("sectionHint")
            val_raw = candidate.get(key, 0)
            prefix = "+" if key == "growth" and val_raw >= 0 else ""
            val = QLabel(f"{prefix}{val_raw}{suffix}")
            val.setStyleSheet("font-size: 15px; font-weight: 800; color: #F8FAFC;")
            box.addWidget(lbl)
            box.addWidget(val)
            stats_row.addLayout(box)
        right.addLayout(stats_row)

        divider = QFrame()
        divider.setObjectName("sidebarDivider")
        divider.setFixedHeight(1)
        right.addWidget(divider)

        # Ban Score gauge + breakdown bars
        gauge_row = QHBoxLayout()
        gauge = BanScoreGauge(score, risk_label, risk_icon)
        gauge_row.addWidget(gauge)
        gauge_row.addStretch()
        right.addLayout(gauge_row)

        breakdown = score_breakdown(candidate, weights)
        for f_label, value, weight in breakdown:
            right.addWidget(FactorBar(f_label, value, weight))

        # ---- Why is this problematic ----
        why_title = QLabel("POR QUE ESSA CARTA É CONSIDERADA PROBLEMÁTICA?")
        why_title.setObjectName("sectionLabel")
        right.addWidget(why_title)

        reasons = [
            PROBLEM_REASONS[label]
            for label, value, _w in breakdown
            if label in PROBLEM_REASONS and value >= HIGH_THRESHOLD
        ]
        reasons_box = QFrame()
        reasons_box.setObjectName("surfaceRaised")
        reasons_layout = QVBoxLayout(reasons_box)
        reasons_layout.setContentsMargins(14, 12, 14, 12)
        reasons_layout.setSpacing(6)
        if reasons:
            for reason in reasons:
                chip = QLabel(f"● {reason}")
                chip.setStyleSheet(f"color: {_color_for_value(score)}; font-weight: 700; font-size: 12px;")
                reasons_layout.addWidget(chip)
        else:
            none_label = QLabel("Nenhum fator individual está em nível crítico — o score reflete uma combinação moderada de fatores.")
            none_label.setObjectName("sectionHint")
            none_label.setWordWrap(True)
            reasons_layout.addWidget(none_label)
        right.addWidget(reasons_box)

        # ---- Restriction selector ----
        restriction_title = QLabel("RESTRIÇÃO")
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
            label = meta["label"] if restriction == "BAN" else f'Limit {meta["max_copies"]}'
            btn = QPushButton(f'{meta["icon"]} {label}')
            btn.setCheckable(True)
            btn.setChecked(current == restriction)
            btn.clicked.connect(lambda _, r=restriction: self._apply_restriction(r))
            actions.addWidget(btn)
            self.action_buttons[restriction] = btn
        right.addLayout(actions)

        impact_note = QLabel(
            "Impacto estimado da restrição: indisponível nesta versão — ainda não há uma engine "
            "de simulação de meta conectada. Esta área está preparada para recebê-la futuramente."
        )
        impact_note.setObjectName("sectionHint")
        impact_note.setWordWrap(True)
        right.addWidget(impact_note)

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
        self.banlist.set_restriction(self.card_id, restriction, reason="Definido via Análise")
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
