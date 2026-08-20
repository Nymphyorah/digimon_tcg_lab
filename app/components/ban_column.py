from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout, QScrollArea, QWidget, QGridLayout
)

from core.banlist_manager import RESTRICTION_META

DESCRIPTIONS = {
    "BAN": "Removida totalmente do formato competitivo.",
    "LIMIT_1": "No máximo 1 cópia permitida por deck.",
    "LIMIT_2": "No máximo 2 cópias permitidas por deck.",
    "LIMIT_3": "No máximo 3 cópias permitidas por deck.",
}


class BanColumn(QFrame):
    """A drop-zone column representing one restriction tier of the Ban List —
    styled as a 'Restriction Board' lane: strong header, status accent,
    short description, and a visual empty state instead of dead space."""

    card_dropped = Signal(str, str)  # card_id, restriction

    def __init__(self, restriction: str, parent=None):
        super().__init__(parent)
        self.restriction = restriction
        meta = RESTRICTION_META[restriction]
        self.color = meta["color"]

        self.setObjectName("surface")
        self.setAcceptDrops(True)
        self.setMinimumWidth(270)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Accent strip along the top of the lane, colored by restriction tier.
        accent = QFrame()
        accent.setFixedHeight(4)
        accent.setStyleSheet(f"background-color: {self.color}; border: none; border-top-left-radius: 14px; border-top-right-radius: 14px;")
        outer.addWidget(accent)

        body = QVBoxLayout()
        body.setContentsMargins(16, 14, 16, 16)
        body.setSpacing(4)
        outer.addLayout(body)

        header = QHBoxLayout()
        title = QLabel(f'{meta["icon"]} {meta["label"].upper()}')
        title.setStyleSheet(f"font-weight: 800; font-size: 13.5px; color: {self.color}; letter-spacing: 0.3px;")
        header.addWidget(title)
        header.addStretch()

        self.count_badge = QLabel("0")
        self.count_badge.setAlignment(Qt.AlignCenter)
        self.count_badge.setFixedSize(26, 22)
        self.count_badge.setStyleSheet(
            f"background-color: rgba{self._rgba(self.color, 0.16)}; color: {self.color}; "
            f"border-radius: 11px; font-weight: 800; font-size: 11px;"
        )
        header.addWidget(self.count_badge)
        body.addLayout(header)

        desc = QLabel(DESCRIPTIONS.get(restriction, ""))
        desc.setObjectName("sectionHint")
        desc.setWordWrap(True)
        body.addWidget(desc)
        body.addSpacing(10)

        # ---- Card area (with a visual empty state instead of dead space) ----
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)

        self.content = QWidget()
        self.grid = QGridLayout(self.content)
        self.grid.setSpacing(12)
        self.grid.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.content)
        body.addWidget(self.scroll, 1)

        self.empty_state = QFrame()
        empty_layout = QVBoxLayout(self.empty_state)
        empty_layout.setContentsMargins(8, 30, 8, 30)
        empty_layout.setSpacing(4)
        empty_icon = QLabel("+")
        empty_icon.setAlignment(Qt.AlignCenter)
        empty_icon.setStyleSheet(f"color: {self.color}; font-size: 22px; font-weight: 800;")
        empty_title = QLabel("Adicionar carta")
        empty_title.setObjectName("emptyState")
        empty_title.setAlignment(Qt.AlignCenter)
        empty_hint = QLabel("Arraste uma carta até aqui")
        empty_hint.setObjectName("emptyStateHint")
        empty_hint.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_icon)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_hint)
        body.addWidget(self.empty_state, 1)

        self._default_style = f"""
            QFrame#surface {{
                background-color: #0D1622;
                border: 1px solid #1B2A3A;
                border-radius: 14px;
            }}
        """
        self._hover_style = f"""
            QFrame#surface {{
                background-color: #0D1622;
                border: 2px dashed {self.color};
                border-radius: 14px;
            }}
        """
        self.setStyleSheet(self._default_style)

        self.drop_hint = QLabel("Solte a carta aqui")
        self.drop_hint.setAlignment(Qt.AlignCenter)
        self.drop_hint.setStyleSheet(f"color: {self.color}; font-weight: 700; font-size: 13px;")
        self.drop_hint.hide()
        body.addWidget(self.drop_hint)

        self._update_empty_state(0)

    @staticmethod
    def _rgba(hex_color: str, alpha: float) -> str:
        hex_color = hex_color.lstrip("#")
        r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
        return f"({r}, {g}, {b}, {alpha})"

    def set_count(self, n: int):
        self.count_badge.setText(str(n))
        self._update_empty_state(n)

    def _update_empty_state(self, n: int):
        self.scroll.setVisible(n > 0)
        self.empty_state.setVisible(n == 0)

    def clear_cards(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def add_card_widget(self, widget, row, col):
        self.grid.addWidget(widget, row, col)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
            self.setStyleSheet(self._hover_style)
            self.drop_hint.show()

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self._default_style)
        self.drop_hint.hide()

    def dropEvent(self, event):
        card_id = event.mimeData().text()
        self.setStyleSheet(self._default_style)
        self.drop_hint.hide()
        if card_id:
            self.card_dropped.emit(card_id, self.restriction)
        event.acceptProposedAction()
