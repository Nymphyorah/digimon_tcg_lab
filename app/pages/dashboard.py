from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QScrollArea, QFrame, QPushButton
)

from app.components.kpi_card import KpiCard
from app.components.charts import TrendChart
from app.components.card_detail_dialog import CardDetailDialog
from app.components.image_loader import load_card_pixmap, invalidate_card_pixmap_cache
from core.ban_score import compute_ban_score, risk_for_score
from core.banlist_manager import RESTRICTION_META, RESTRICTIONS
from core.image_cache import get_image_cache_manager

# Purely presentational bucketing of numbers the app already computes
# (critical candidates vs. total) — no new scoring logic, just a qualitative
# label so the dashboard reads "how healthy is the meta" at a glance.
META_HEALTH_BANDS = [
    (0.0, 0.05, "SAUDÁVEL", "#22C55E", "🟢",
     "Poucos ou nenhum candidato crítico — o formato está bem distribuído."),
    (0.05, 0.15, "EM OBSERVAÇÃO", "#EAB308", "🟡",
     "Uma parcela pequena do meta concentra risco — vale acompanhar de perto."),
    (0.15, 1.01, "ATENÇÃO NECESSÁRIA", "#EF4444", "🔴",
     "Concentração alta de candidatos críticos — o formato pode estar desequilibrado."),
]


class DashboardPage(QWidget):
    navigate_requested = Signal(str)

    def __init__(self, repo, banlist, settings, analyzer, db, updater, collection=None, deckbuilder=None, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.banlist = banlist
        self.settings = settings
        self.analyzer = analyzer

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

        # Meta Health hero banner
        self.health_box = QFrame()
        self.health_box.setObjectName("surfaceRaised")
        self.health_layout = QHBoxLayout(self.health_box)
        self.health_layout.setContentsMargins(22, 18, 22, 18)
        self.layout_.addWidget(self.health_box)

        # Secondary KPI row
        self.kpi_row = QHBoxLayout()
        self.kpi_row.setSpacing(16)
        self.layout_.addLayout(self.kpi_row)

        # Distribution strip (compact) + Fun Score stub
        strip_row = QHBoxLayout()
        strip_row.setSpacing(16)

        self.distribution_box = QFrame()
        self.distribution_box.setObjectName("surface")
        self.distribution_layout = QVBoxLayout(self.distribution_box)
        self.distribution_layout.setContentsMargins(18, 14, 18, 14)
        strip_row.addWidget(self.distribution_box, 3)

        self.fun_score_box = QFrame()
        self.fun_score_box.setObjectName("surface")
        self.fun_score_layout = QVBoxLayout(self.fun_score_box)
        self.fun_score_layout.setContentsMargins(18, 14, 18, 14)
        strip_row.addWidget(self.fun_score_box, 1)
        self.layout_.addLayout(strip_row)

        # Top Ban Candidates — card-forward grid
        self.candidates_box = QFrame()
        self.candidates_box.setObjectName("surface")
        self.candidates_layout = QVBoxLayout(self.candidates_box)
        self.candidates_layout.setContentsMargins(18, 16, 18, 16)
        self.layout_.addWidget(self.candidates_box)

        # Trend chart
        trend_box = QFrame()
        trend_box.setObjectName("surface")
        trend_layout = QVBoxLayout(trend_box)
        trend_layout.setContentsMargins(18, 16, 18, 16)
        trend_title = QLabel("TENDÊNCIA DO META")
        trend_title.setObjectName("sectionLabel")
        trend_layout.addWidget(trend_title)
        self.trend_chart = TrendChart()
        self.trend_chart.setMinimumHeight(240)
        trend_layout.addWidget(self.trend_chart)
        self.layout_.addWidget(trend_box)

    def refresh(self):
        counts = self.banlist.counts()
        restricted_total = sum(counts.values())
        meta = self.repo.meta
        ban_candidates = meta.get("ban_candidates", [])
        weights = self.settings.get("ban_score_weights")
        critical = sum(1 for c in ban_candidates if compute_ban_score(c, weights) >= 90)

        self._build_health_banner(critical, len(ban_candidates), meta)
        self._build_kpi_row(restricted_total, meta, critical)
        self._build_distribution(counts)
        self._build_fun_score_stub()
        self._build_candidates(ban_candidates, weights)
        self._build_trend(meta)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _build_health_banner(self, critical, total_candidates, meta):
        self._clear_layout(self.health_layout)
        ratio = (critical / total_candidates) if total_candidates else 0.0
        status, color, icon, description = next(
            (s, c, i, d) for lo, hi, s, c, i, d in META_HEALTH_BANDS if lo <= ratio < hi
        )

        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 34px;")
        self.health_layout.addWidget(icon_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        eyebrow = QLabel("META HEALTH")
        eyebrow.setObjectName("sectionLabel")
        text_col.addWidget(eyebrow)
        status_label = QLabel(status)
        status_label.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {color};")
        text_col.addWidget(status_label)
        desc_label = QLabel(description)
        desc_label.setObjectName("sectionHint")
        desc_label.setWordWrap(True)
        text_col.addWidget(desc_label)
        self.health_layout.addLayout(text_col, 1)

        stat_col = QVBoxLayout()
        stat_col.setAlignment(Qt.AlignRight)
        stat_val = QLabel(f"{critical}/{total_candidates}")
        stat_val.setAlignment(Qt.AlignRight)
        stat_val.setStyleSheet("font-size: 22px; font-weight: 800; color: #F8FAFC;")
        stat_lbl = QLabel("CANDIDATOS CRÍTICOS")
        stat_lbl.setObjectName("sectionLabel")
        stat_lbl.setAlignment(Qt.AlignRight)
        stat_col.addWidget(stat_val)
        stat_col.addWidget(stat_lbl)
        self.health_layout.addLayout(stat_col)

    def _build_kpi_row(self, restricted_total, meta, critical):
        self._clear_layout(self.kpi_row)
        kpis = [
            ("Cartas Restritas", str(restricted_total), "#2388FF"),
            ("Decks Analisados", f'{meta.get("decks_analyzed", 0):,}'.replace(",", "."), "#22C55E"),
            ("Torneios", str(meta.get("tournaments", 0)), "#EAB308"),
            ("Candidatos Críticos", str(critical), "#EF4444"),
        ]
        for label, value, color in kpis:
            self.kpi_row.addWidget(KpiCard(label, value, color))

    def _build_distribution(self, counts):
        self._clear_layout(self.distribution_layout)
        title = QLabel("DISTRIBUIÇÃO DA BAN LIST")
        title.setObjectName("sectionLabel")
        self.distribution_layout.addWidget(title)
        self.distribution_layout.addSpacing(8)

        pills_row = QHBoxLayout()
        pills_row.setSpacing(10)
        for restriction in RESTRICTIONS:
            meta = RESTRICTION_META[restriction]
            pill = QFrame()
            pill.setObjectName("surfaceRaised")
            pill_layout = QVBoxLayout(pill)
            pill_layout.setContentsMargins(12, 8, 12, 8)
            pill_layout.setSpacing(0)
            count_lbl = QLabel(str(counts.get(restriction, 0)))
            count_lbl.setAlignment(Qt.AlignCenter)
            count_lbl.setStyleSheet(f'font-size: 20px; font-weight: 800; color: {meta["color"]};')
            name_lbl = QLabel(f'{meta["icon"]} {meta["label"]}')
            name_lbl.setAlignment(Qt.AlignCenter)
            name_lbl.setStyleSheet("color: #8494A8; font-size: 10px; font-weight: 600;")
            pill_layout.addWidget(count_lbl)
            pill_layout.addWidget(name_lbl)
            pills_row.addWidget(pill, 1)
        self.distribution_layout.addLayout(pills_row)
        self.distribution_layout.addSpacing(4)

        view_btn = QPushButton("Ver Ban List completa →")
        view_btn.clicked.connect(lambda: self.navigate_requested.emit("ban_list"))
        self.distribution_layout.addWidget(view_btn)

    def _build_fun_score_stub(self):
        self._clear_layout(self.fun_score_layout)
        title = QLabel("FUN SCORE")
        title.setObjectName("sectionLabel")
        self.fun_score_layout.addWidget(title)
        self.fun_score_layout.addSpacing(4)

        value_label = QLabel("—")
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setStyleSheet("font-size: 28px; font-weight: 800; color: #4B5A6E;")
        self.fun_score_layout.addWidget(value_label)

        note = QLabel("Em breve: quão divertido e diverso está o formato, além do risco de banimento.")
        note.setObjectName("sectionHint")
        note.setWordWrap(True)
        note.setAlignment(Qt.AlignCenter)
        self.fun_score_layout.addWidget(note)
        self.fun_score_layout.addStretch()

    def _build_candidates(self, ban_candidates, weights):
        self._clear_layout(self.candidates_layout)
        title = QLabel("TOP BAN CANDIDATES")
        title.setObjectName("sectionLabel")
        self.candidates_layout.addWidget(title)
        self.candidates_layout.addSpacing(10)

        scored = []
        for c in ban_candidates:
            card = self.repo.card(c["card_id"])
            if not card:
                continue
            score = compute_ban_score(c, weights)
            label, icon = risk_for_score(score)
            scored.append((score, label, icon, c, card))
        scored.sort(key=lambda t: -t[0])

        grid = QGridLayout()
        grid.setSpacing(14)
        cols = 3
        for i, (score, label, icon, candidate, card) in enumerate(scored[:6]):
            grid.addWidget(self._build_candidate_card(score, label, icon, candidate, card), i // cols, i % cols)
        self.candidates_layout.addLayout(grid)

    def _build_candidate_card(self, score, label, icon, candidate, card):
        row = QFrame()
        row.setObjectName("surfaceRaised")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(12, 12, 12, 12)
        row_layout.setSpacing(12)

        img_size = QSize(64, 90)
        img = QLabel()
        img.setPixmap(load_card_pixmap(card["card_id"], img_size))
        img.card_id = card["card_id"]
        get_image_cache_manager().image_ready.connect(
            lambda card_id, lbl=img, size=img_size: self._on_candidate_image_ready(card_id, lbl, size)
        )
        row_layout.addWidget(img)

        info = QVBoxLayout()
        info.setSpacing(3)
        id_label = QLabel(f'{card["card_id"]}')
        id_label.setStyleSheet("color: #6B7F97; font-size: 10px; font-weight: 700;")
        info.addWidget(id_label)
        name_label = QLabel(card.get("name", ""))
        name_label.setStyleSheet("font-weight: 800; font-size: 13px;")
        name_label.setWordWrap(True)
        info.addWidget(name_label)
        usage_label = QLabel(f'Meta Usage: {candidate.get("meta_usage", 0)}%')
        usage_label.setStyleSheet("color: #6B7F97; font-size: 10.5px;")
        info.addWidget(usage_label)

        score_row = QHBoxLayout()
        score_row.setSpacing(6)
        score_label = QLabel(str(score))
        score_color = RESTRICTION_META["BAN"]["color"] if score >= 90 else "#F97316"
        score_label.setStyleSheet(f'font-size: 17px; font-weight: 800; color: {score_color};')
        score_row.addWidget(score_label)
        risk_chip = QLabel(f"{icon} {label}")
        risk_chip.setObjectName(self._risk_chip_object_name(label))
        score_row.addWidget(risk_chip)
        score_row.addStretch()
        info.addLayout(score_row)

        view_btn = QPushButton("Ver análise")
        view_btn.clicked.connect(lambda _, c=card: self._open_card_detail(c))
        info.addWidget(view_btn)

        row_layout.addLayout(info, 1)
        return row

    @staticmethod
    def _on_candidate_image_ready(card_id, label, size):
        if getattr(label, "card_id", None) != card_id:
            return
        try:
            invalidate_card_pixmap_cache(card_id)
            label.setPixmap(load_card_pixmap(card_id, size))
        except RuntimeError:
            pass  # label was already torn down by a later refresh()

    @staticmethod
    def _risk_chip_object_name(label):
        return {
            "CRITICO": "riskChipCritical",
            "ALTO": "riskChipHigh",
            "MODERADO": "riskChipModerate",
            "BAIXO": "riskChipLow",
            "NORMAL": "riskChipNormal",
        }.get(label, "riskChipNormal")

    def _build_trend(self, meta):
        trends = meta.get("trends", [])
        if not trends:
            return
        labels = [w["week"] for w in trends]
        card_ids = [c["card_id"] for c in trends[0]["cards"][:4]] if trends[0]["cards"] else []
        series = {}
        for cid in card_ids:
            values = []
            for week in trends:
                match = next((c["usage"] for c in week["cards"] if c["card_id"] == cid), 0)
                values.append(match)
            card = self.repo.card(cid)
            label = card["name"] if card else cid
            series[label] = values
        self.trend_chart.plot_series(labels, series)

    def _open_card_detail(self, card):
        dlg = CardDetailDialog(card, self.repo, self.banlist, self.settings, parent=self)
        dlg.restriction_changed.connect(self.refresh)
        dlg.exec()
