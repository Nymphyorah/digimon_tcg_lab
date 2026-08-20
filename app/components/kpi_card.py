from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class KpiCard(QFrame):
    def __init__(self, label: str, value: str, accent: str = "#2388FF", parent=None):
        super().__init__(parent)
        self.setObjectName("surface")
        self.setMinimumHeight(96)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        self.value_label = QLabel(value)
        self.value_label.setObjectName("kpiValue")
        self.value_label.setStyleSheet(f"color: {accent};")

        self.text_label = QLabel(label.upper())
        self.text_label.setObjectName("kpiLabel")
        self.text_label.setWordWrap(True)

        layout.addWidget(self.value_label)
        layout.addWidget(self.text_label)
        layout.addStretch()

    def set_value(self, value: str):
        self.value_label.setText(value)
