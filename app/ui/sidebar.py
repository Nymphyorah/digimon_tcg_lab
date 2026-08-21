from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QFrame, QButtonGroup

NAV_ITEMS = [
    ("overview", "🏠", "Overview"),
    ("meta", "📊", "Meta Lab"),
    ("collection", "🃏", "Collection"),
    ("analysis", "🔎", "Analysis"),
    ("ban_list", "🛑", "Ban List"),
    ("history", "📜", "History"),
]

FOOTER_ITEMS = []


class Sidebar(QWidget):
    page_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self._collapsed = False
        self._expanded_width = 220
        self._collapsed_width = 64
        self.setFixedWidth(self._expanded_width)

        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(14, 18, 14, 18)
        self.layout_.setSpacing(4)

        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        self.title_label = QLabel("DIGIMON")
        self.title_label.setObjectName("sidebarTitle")
        self.subtitle_label = QLabel("TCG LAB")
        self.subtitle_label.setObjectName("sidebarSubtitle")
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)
        self.layout_.addLayout(title_box)
        self.layout_.addSpacing(14)

        divider = QFrame()
        divider.setObjectName("sidebarDivider")
        divider.setFixedHeight(1)
        self.layout_.addWidget(divider)
        self.layout_.addSpacing(10)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}

        for key, icon, label in NAV_ITEMS:
            btn = self._make_button(icon, label)
            self.group.addButton(btn)
            self.buttons[key] = btn
            btn.clicked.connect(lambda _, k=key: self.page_selected.emit(k))
            self.layout_.addWidget(btn)

        self.layout_.addStretch()

        divider2 = QFrame()
        divider2.setObjectName("sidebarDivider")
        divider2.setFixedHeight(1)
        self.layout_.addWidget(divider2)
        self.layout_.addSpacing(6)

        for key, icon, label in FOOTER_ITEMS:
            btn = self._make_button(icon, label)
            self.group.addButton(btn)
            self.buttons[key] = btn
            btn.clicked.connect(lambda _, k=key: self.page_selected.emit(k))
            self.layout_.addWidget(btn)

        collapse_btn = QPushButton("⟨⟨  Recolher")
        collapse_btn.setObjectName("navButton")
        collapse_btn.clicked.connect(self.toggle_collapsed)
        self.layout_.addWidget(collapse_btn)
        self.collapse_btn = collapse_btn

        self.buttons["overview"].setChecked(True)

    def _make_button(self, icon, label):
        btn = QPushButton(f"  {icon}   {label}")
        btn.setObjectName("navButton")
        btn.setCheckable(True)
        btn.setToolTip(label)
        btn.setMinimumHeight(38)
        return btn

    def set_active(self, key: str):
        if key in self.buttons:
            self.buttons[key].setChecked(True)

    def toggle_collapsed(self):
        self._collapsed = not self._collapsed
        if self._collapsed:
            self.setFixedWidth(self._collapsed_width)
            self.title_label.hide()
            self.subtitle_label.hide()
            self.collapse_btn.setText("⟩⟩")
            for key, icon, label in NAV_ITEMS + FOOTER_ITEMS:
                self.buttons[key].setText(f" {icon}")
        else:
            self.setFixedWidth(self._expanded_width)
            self.title_label.show()
            self.subtitle_label.show()
            self.collapse_btn.setText("⟨⟨  Recolher")
            for key, icon, label in NAV_ITEMS + FOOTER_ITEMS:
                self.buttons[key].setText(f"  {icon}   {label}")
