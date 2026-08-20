from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea, QWidget, QGridLayout
)

from app.components.image_loader import load_card_pixmap
from app.components.card_detail_dialog import CardDetailDialog


def _inclusion_color(pct: float) -> str:
    if pct >= 90:
        return "#22C55E"
    if pct >= 50:
        return "#2388FF"
    if pct >= 20:
        return "#EAB308"
    return "#94A3B8"


class DeckDetailDialog(QDialog):
    def __init__(self, deck: dict, repo, banlist_manager, settings_manager, parent=None):
        super().__init__(parent)
        self.deck = deck
        self.repo = repo
        self.banlist = banlist_manager
        self.settings = settings_manager

        self.setWindowTitle(deck.get("archetype", deck.get("name", "Deck")))
        self.resize(1180, 760)
        self.setMinimumSize(900, 620)
        self.setStyleSheet("QDialog { background-color: #070B12; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        title = QLabel(deck.get("archetype", "").upper())
        title.setStyleSheet("font-size: 26px; font-weight: 800;")
        root.addWidget(title)

        stats = QHBoxLayout()
        stats.setSpacing(32)
        for key, label, suffix in [
            ("entries", "Participação", ""), ("meta_usage", "Meta Usage", "%"),
            ("top8", "Top 8", "%"), ("win_rate", "Win Rate", "%")
        ]:
            box = QVBoxLayout()
            lbl = QLabel(label.upper())
            lbl.setObjectName("sectionHint")
            val = QLabel(f'{deck.get(key, 0)}{suffix}')
            val.setStyleSheet("font-size: 22px; font-weight: 800; color: #2388FF;")
            box.addWidget(lbl)
            box.addWidget(val)
            stats.addLayout(box)
        stats.addStretch()
        root.addLayout(stats)

        section_row = QHBoxLayout()
        section = QLabel("LISTA DE CARTAS")
        section.setObjectName("sectionLabel")
        section_row.addWidget(section)
        section_row.addStretch()
        legend = QLabel("% de aparição nos decks deste arquétipo")
        legend.setObjectName("sectionHint")
        section_row.addWidget(legend)
        root.addLayout(section_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        grid = QGridLayout(content)
        grid.setSpacing(12)
        grid.setAlignment(Qt.AlignTop)

        cards_sorted = sorted(
            deck.get("cards", []),
            key=lambda c: (-c.get("inclusion_pct", 0), -c["copies"]),
        )
        cols = 6
        for i, entry in enumerate(cards_sorted):
            card = self.repo.card(entry["card_id"])
            if not card:
                continue
            tile = self._build_card_tile(card, entry["copies"], entry.get("inclusion_pct"))
            grid.addWidget(tile, i // cols, i % cols)

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

    def _build_card_tile(self, card, copies, inclusion_pct):
        frame = QFrame()
        frame.setObjectName("surface")
        frame.setCursor(Qt.PointingHandCursor)
        frame.setFixedWidth(150)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(9, 9, 9, 9)
        layout.setSpacing(5)

        img = QLabel()
        img.setPixmap(load_card_pixmap(card["card_id"], QSize(128, 179)))
        img.setAlignment(Qt.AlignCenter)
        layout.addWidget(img, alignment=Qt.AlignCenter)

        row = QHBoxLayout()
        id_label = QLabel(card["card_id"])
        id_label.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: 700;")
        copies_label = QLabel(f"×{copies}")
        copies_label.setStyleSheet("color: #2388FF; font-size: 11px; font-weight: 800;")
        row.addWidget(id_label)
        row.addStretch()
        row.addWidget(copies_label)
        layout.addLayout(row)

        name_label = QLabel(card.get("name", ""))
        name_label.setStyleSheet("font-size: 11px; font-weight: 700;")
        name_label.setWordWrap(True)
        layout.addWidget(name_label)

        if inclusion_pct is not None:
            color = _inclusion_color(inclusion_pct)
            pct_row = QHBoxLayout()
            pct_row.setSpacing(6)
            bar_bg = QFrame()
            bar_bg.setFixedHeight(6)
            bar_bg.setStyleSheet("background-color: #1B2A3A; border-radius: 3px;")
            bar_layout = QHBoxLayout(bar_bg)
            bar_layout.setContentsMargins(0, 0, 0, 0)
            bar_fill = QFrame()
            bar_fill.setFixedHeight(6)
            bar_fill.setStyleSheet(f"background-color: {color}; border-radius: 3px;")
            bar_layout.addWidget(bar_fill, int(max(1, inclusion_pct)))
            if inclusion_pct < 100:
                bar_layout.addStretch(int(100 - inclusion_pct))
            layout.addWidget(bar_bg)

            pct_label = QLabel(f"{inclusion_pct:.0f}% dos decks")
            pct_label.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: 700;")
            layout.addWidget(pct_label)

        frame.mousePressEvent = lambda e, c=card: self._open_card(c)
        return frame

    def _open_card(self, card):
        dlg = CardDetailDialog(card, self.repo, self.banlist, self.settings, parent=self)
        dlg.exec()
