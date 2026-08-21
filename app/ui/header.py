from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel

PAGE_TITLES = {
    "overview": ("Overview", "Visão geral factual do meta e da sua Ban List"),
    "meta": ("Meta Lab", "Análise do meta competitivo"),
    "collection": ("Collection", "Sua coleção e Deck Builder — monte decks com o que você possui, seguindo as regras oficiais e sua Ban List"),
    "analysis": ("Analysis", "Meta Usage, Top Cut e Dominance por carta — dados reais, sem pontuação artificial"),
    "ban_list": ("Ban List", "Gerencie sua lista de restrição pessoal"),
    "history": ("History", "Linha do tempo das alterações na Ban List"),
}


class Header(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("header")
        self.setFixedHeight(64)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)

        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        self.title_label = QLabel("Dashboard")
        self.title_label.setObjectName("headerTitle")
        self.subtitle_label = QLabel("")
        self.subtitle_label.setObjectName("headerSubtitle")
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)
        layout.addLayout(title_box)
        layout.addStretch()

        status_box = QVBoxLayout()
        status_box.setSpacing(0)
        status_box.setAlignment(Qt.AlignRight)
        self.status_label = QLabel("● ONLINE")
        self.status_label.setObjectName("statusOnline")
        self.updated_label = QLabel("Última atualização: --/--/----")
        self.updated_label.setObjectName("headerSubtitle")
        status_box.addWidget(self.status_label, alignment=Qt.AlignRight)
        status_box.addWidget(self.updated_label, alignment=Qt.AlignRight)
        layout.addLayout(status_box)

    def set_page(self, key: str):
        title, subtitle = PAGE_TITLES.get(key, (key.title(), ""))
        self.title_label.setText(title)
        self.subtitle_label.setText(subtitle)

    def set_status(self, online: bool):
        if online:
            self.status_label.setText("● ONLINE")
            self.status_label.setObjectName("statusOnline")
        else:
            self.status_label.setText("● OFFLINE")
            self.status_label.setObjectName("statusOffline")
        self.status_label.setStyleSheet("")
        self.style().unpolish(self.status_label)
        self.style().polish(self.status_label)

    def set_last_updated(self, date_str: str):
        self.updated_label.setText(f"Última atualização: {date_str}")
