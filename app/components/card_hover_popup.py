"""Floating quick-preview shown ~220ms after the cursor rests on a card
tile, across both the catalog and the current-deck panel. A single shared
instance is reused (see get_hover_popup()) instead of one per tile.

Only shows fields that are genuinely present in data/cards.json — image,
DP, Play Cost, Digivolve Cost, and the printed effect text
(main_effect/source_effect/alt_effect), all sourced from the digimoncard.io
public API. No fabricated stats."""
from PySide6.QtCore import Qt, QSize, QPoint
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QWidget

from app.components.image_loader import load_card_pixmap

POPUP_IMG_SIZE = QSize(180, 252)


class CardHoverPopup(QFrame):
    def __init__(self):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setObjectName("cardHoverPopup")
        self.setFixedWidth(240)
        self.setMaximumHeight(520)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(8)

        self.image_label = QLabel()
        self.image_label.setFixedSize(POPUP_IMG_SIZE)
        self.image_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self.image_label, alignment=Qt.AlignCenter)

        self.name_label = QLabel()
        self.name_label.setObjectName("hoverPopupName")
        self.name_label.setWordWrap(True)
        root.addWidget(self.name_label)

        self.meta_label = QLabel()
        self.meta_label.setObjectName("hoverPopupMeta")
        self.meta_label.setWordWrap(True)
        root.addWidget(self.meta_label)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        self.dp_label = QLabel()
        self.dp_label.setObjectName("hoverPopupStat")
        stats_row.addWidget(self.dp_label)
        self.cost_label = QLabel()
        self.cost_label.setObjectName("hoverPopupStat")
        stats_row.addWidget(self.cost_label)
        stats_row.addStretch()
        root.addLayout(stats_row)

        self.risk_label = QLabel()
        self.risk_label.setWordWrap(True)
        root.addWidget(self.risk_label)

        effect_scroll = QScrollArea()
        effect_scroll.setWidgetResizable(True)
        effect_scroll.setFrameShape(QFrame.NoFrame)
        effect_scroll.setMaximumHeight(160)
        effect_inner = QWidget()
        effect_layout = QVBoxLayout(effect_inner)
        effect_layout.setContentsMargins(0, 0, 0, 0)
        self.effect_label = QLabel()
        self.effect_label.setObjectName("hoverPopupEffect")
        self.effect_label.setWordWrap(True)
        self.effect_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        effect_layout.addWidget(self.effect_label)
        effect_scroll.setWidget(effect_inner)
        root.addWidget(effect_scroll)

        self.hide()

    def show_for(self, card: dict, global_pos: QPoint, risk_chip: tuple = None):
        self.image_label.setPixmap(load_card_pixmap(card["card_id"], POPUP_IMG_SIZE))
        self.name_label.setText(f'{card.get("name","")}')
        self.meta_label.setText(
            f'{card["card_id"]} · {card.get("color","")} · Lv.{card.get("level") or "-"} · '
            f'{card.get("type","")} · {card.get("rarity","")} · {card.get("set","")}'
        )

        dp = card.get("dp")
        self.dp_label.setText(f"DP {dp}" if dp is not None else "")
        self.dp_label.setVisible(dp is not None)

        cost_parts = []
        if card.get("play_cost") is not None:
            cost_parts.append(f'Custo {card["play_cost"]}')
        if card.get("evolution_cost") is not None:
            cost_parts.append(f'Digivolução {card["evolution_cost"]}')
        self.cost_label.setText(" · ".join(cost_parts))
        self.cost_label.setVisible(bool(cost_parts))

        if risk_chip:
            chip_text, chip_object_name = risk_chip
            self.risk_label.setText(chip_text)
            self.risk_label.setObjectName(chip_object_name)
            self.risk_label.setVisible(True)
            self.risk_label.style().unpolish(self.risk_label)
            self.risk_label.style().polish(self.risk_label)
        else:
            self.risk_label.setText("")
            self.risk_label.setVisible(False)

        effect_text = "\n\n".join(filter(None, [
            card.get("main_effect"), card.get("source_effect"), card.get("alt_effect"),
        ]))
        self.effect_label.setText(effect_text or "Sem texto de efeito disponível.")

        self.adjustSize()
        self.move(self._clamp_to_screen(global_pos))
        self.show()

    def _clamp_to_screen(self, pos: QPoint) -> QPoint:
        target = QPoint(pos.x() + 18, pos.y() + 18)
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            if target.x() + self.width() > geo.right():
                target.setX(pos.x() - self.width() - 18)
            if target.y() + self.height() > geo.bottom():
                target.setY(max(geo.top(), geo.bottom() - self.height()))
        return target


_popup = None


def get_hover_popup() -> CardHoverPopup:
    global _popup
    if _popup is None:
        _popup = CardHoverPopup()
    return _popup
