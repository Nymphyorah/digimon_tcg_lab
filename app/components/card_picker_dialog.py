"""Small reusable 'search and pick one card' dialog — used by the
Restriction Board's + Add Card button so a restriction can be set without
needing to drag from Collection."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QLabel, QPushButton
)

MAX_RESULTS = 40


class CardPickerDialog(QDialog):
    def __init__(self, repo, title="Add Card", parent=None):
        super().__init__(parent)
        self.repo = repo
        self.selected_card_id = None

        self.setWindowTitle(title)
        self.setMinimumSize(420, 520)
        self.setStyleSheet("QDialog { background-color: #070B12; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title_label = QLabel(title.upper())
        title_label.setObjectName("sectionLabel")
        layout.addWidget(title_label)

        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Buscar por nome ou código...")
        self.search.textChanged.connect(self._apply_search)
        layout.addWidget(self.search)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._accept_item)
        layout.addWidget(self.list, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)
        actions.addWidget(cancel_btn)
        select_btn = QPushButton("Selecionar")
        select_btn.setObjectName("primaryButton")
        select_btn.clicked.connect(self._accept_selected)
        actions.addWidget(select_btn)
        layout.addLayout(actions)

        self._populate([])

    def _apply_search(self, text):
        text = text.strip().lower()
        if not text:
            self._populate([])
            return
        results = [
            c for c in self.repo.cards
            if text in c["card_id"].lower() or text in c.get("name", "").lower()
        ][:MAX_RESULTS]
        self._populate(results)

    def _populate(self, cards):
        self.list.clear()
        for card in cards:
            item = QListWidgetItem(f'{card["card_id"]} · {card.get("name","")}')
            item.setData(Qt.UserRole, card["card_id"])
            self.list.addItem(item)

    def _accept_item(self, item):
        self.selected_card_id = item.data(Qt.UserRole)
        self.accept()

    def _accept_selected(self):
        item = self.list.currentItem()
        if not item:
            return
        self.selected_card_id = item.data(Qt.UserRole)
        self.accept()
