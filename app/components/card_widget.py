from PySide6.QtCore import Qt, Signal, QSize, QMimeData, QTimer
from PySide6.QtGui import QDrag, QMouseEvent, QCursor
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QHBoxLayout

from app.components.image_loader import load_card_pixmap, invalidate_card_pixmap_cache
from app.components.card_hover_popup import get_hover_popup
from core.banlist_manager import RESTRICTION_META
from core.image_cache import get_image_cache_manager

CARD_IMG_SIZE = QSize(180, 252)
CARD_IMG_SIZE_LARGE = QSize(188, 263)
HOVER_DELAY_MS = 220

# Official Digimon TCG card colors. This is the single source of truth for
# color -> hex used across the catalog (card borders/dots), the color filter
# chips, and the hover popup — every card's own `color` (and `color2` for
# dual-color cards) field already carries one of these names verbatim.
CARD_COLOR_HEX = {
    "Red": "#E53935",
    "Blue": "#1E88E5",
    "Yellow": "#FBC02D",
    "Green": "#43A047",
    "Black": "#455A64",  # true black (#263238) reads as invisible on the dark theme; this is its visible-on-dark accent
    "Purple": "#8E44AD",
    "White": "#F5F5F5",
    "Colorless": "#5C6B7A",
}


def color_hex(name: str) -> str:
    return CARD_COLOR_HEX.get(name, CARD_COLOR_HEX["Colorless"])


def _rgba_tuple(hex_color: str) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return f"{r}, {g}, {b}"


class CardWidget(QFrame):
    """A single Digimon card tile used across Collection, Ban List, Overview
    and the Deck Builder's card catalog. Pass large=True where the card
    itself should be the visual protagonist (e.g. the Ban List board)."""

    clicked = Signal(str)
    right_clicked = Signal(str)

    def __init__(self, card: dict, restriction: str = None, draggable: bool = False,
                 deck_count: int = None, selected: bool = False, lazy_image: bool = False,
                 large: bool = False, indicators: dict = None, parent=None):
        """indicators: optional {"meta_usage", "top_cut", "dominance"} dict —
        real per-card competitive data, shown discreetly in the hover popup
        rather than as a permanent on-tile badge, so the catalog stays
        card-forward instead of cluttered with numbers."""
        super().__init__(parent)
        self.card = card
        self.card_id = card["card_id"]
        self.restriction = restriction
        self.draggable = draggable
        self._drag_start = None
        self._image_loaded = False
        self._selected = selected
        self._hovered = False
        self.img_size = CARD_IMG_SIZE_LARGE if large else CARD_IMG_SIZE
        self._indicators = indicators
        self._color_names = [c for c in [card.get("color"), card.get("color2")] if c]
        self._primary_color_hex = color_hex(self._color_names[0] if self._color_names else None)
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(HOVER_DELAY_MS)
        self._hover_timer.timeout.connect(self._show_hover_popup)

        self.setObjectName("surface")
        self.setProperty("class", "cardWidget")
        self.setFixedWidth(232 if large else 208)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_frame_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 11, 11, 11)
        layout.setSpacing(7)

        self.image_label = QLabel()
        self.image_label.setFixedSize(self.img_size)
        self.image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.image_label, alignment=Qt.AlignCenter)
        get_image_cache_manager().image_ready.connect(self._on_image_ready)
        if lazy_image:
            self.image_label.setStyleSheet("background-color: #12202E; border-radius: 8px;")
        else:
            self.load_image()

        id_row = QHBoxLayout()
        id_row.setSpacing(6)
        id_label = QLabel(self.card_id)
        id_label.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: 700;")
        id_row.addWidget(id_label)

        # Color dot(s) — the primary way to recognize a card's color without
        # reading text; a second dot appears only for genuinely dual-color
        # cards (card["color2"] is real data, not inferred).
        for color_name in self._color_names:
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color_hex(color_name)}; font-size: 12px;")
            dot.setToolTip(color_name)
            id_row.addWidget(dot)

        id_row.addStretch()
        self.restriction_badge = QLabel()
        id_row.addWidget(self.restriction_badge)
        layout.addLayout(id_row)
        self.set_restriction(restriction)

        name_label = QLabel(card.get("name", ""))
        name_label.setStyleSheet(f"font-weight: 700; font-size: {13 if large else 12}px;")
        name_label.setWordWrap(True)
        layout.addWidget(name_label)

        meta_label = QLabel(f'{card.get("color","")} · {card.get("set","")} · {card.get("rarity","")}')
        meta_label.setStyleSheet(f"color: #64748B; font-size: {11 if large else 10}px;")
        layout.addWidget(meta_label)

        self.deck_label = None
        if deck_count is not None:
            self.deck_label = QLabel()
            self.deck_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.deck_label)
            self.set_deck_count(deck_count)

    def load_image(self):
        if self._image_loaded:
            return
        self._image_loaded = True
        self.image_label.setStyleSheet("")
        self.image_label.setPixmap(load_card_pixmap(self.card_id, self.img_size))

    def _on_image_ready(self, card_id: str):
        if card_id != self.card_id or not self._image_loaded:
            return
        invalidate_card_pixmap_cache(card_id)
        self.image_label.setPixmap(load_card_pixmap(self.card_id, self.img_size))

    def set_deck_count(self, deck_count: int):
        if self.deck_label is None:
            return
        self.deck_label.setText(f"No deck: {deck_count}")
        self.deck_label.setStyleSheet(
            "font-size: 10px; font-weight: 700; color: #22C55E;" if deck_count > 0
            else "font-size: 10px; color: #475569;"
        )

    def set_restriction(self, restriction: str):
        self.restriction = restriction
        if restriction:
            meta = RESTRICTION_META[restriction]
            self.restriction_badge.setText(meta["label"].upper())
            self.restriction_badge.setStyleSheet(
                f'background-color: rgba({_rgba_tuple(meta["color"])}, 0.18); color: {meta["color"]}; '
                f'border: 1px solid {meta["color"]}; border-radius: 6px; font-size: 8.5px; '
                f'font-weight: 800; padding: 1px 5px;'
            )
            self.restriction_badge.setToolTip(meta["label"])
        else:
            self.restriction_badge.setText("")
            self.restriction_badge.setStyleSheet("")
            self.restriction_badge.setToolTip("")

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_frame_style()

    def _apply_frame_style(self):
        if self._selected:
            self.setStyleSheet("QFrame#surface { border: 2px solid #2388FF; }")
        elif self._hovered:
            # A discreet glow in the card's own color on hover — not the
            # generic blue highlight, so color identity stays legible even
            # while the user is scanning the grid with the mouse.
            self.setStyleSheet(
                f"QFrame#surface {{ border: 1px solid {self._primary_color_hex}; "
                f"background-color: rgba({_rgba_tuple(self._primary_color_hex)}, 0.07); }}"
            )
        else:
            self.setStyleSheet(f"QFrame#surface {{ border: 1px solid {self._primary_color_hex}; }}")

    def enterEvent(self, event):
        self._hovered = True
        self._apply_frame_style()
        self._hover_timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._apply_frame_style()
        self._hover_timer.stop()
        get_hover_popup().hide()
        super().leaveEvent(event)

    def _show_hover_popup(self):
        get_hover_popup().show_for(self.card, QCursor.pos(), self._indicators, self.restriction)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.draggable and self._drag_start and (event.buttons() & Qt.LeftButton):
            distance = (event.position().toPoint() - self._drag_start).manhattanLength()
            if distance >= 12:
                drag = QDrag(self)
                mime = QMimeData()
                mime.setText(self.card_id)
                drag.setMimeData(mime)
                drag.setPixmap(self.image_label.pixmap())
                drag.setHotSpot(event.position().toPoint())
                drag.exec(Qt.MoveAction)
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and self._drag_start is not None:
            distance = (event.position().toPoint() - self._drag_start).manhattanLength()
            if distance < 12:
                self.clicked.emit(self.card_id)
            self._drag_start = None
        elif event.button() == Qt.RightButton:
            self.right_clicked.emit(self.card_id)
        super().mouseReleaseEvent(event)
