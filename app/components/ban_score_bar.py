from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar


def _color_for_value(value: int) -> str:
    if value >= 90:
        return "#EF4444"
    if value >= 75:
        return "#F97316"
    if value >= 55:
        return "#EAB308"
    if value >= 30:
        return "#2388FF"
    return "#94A3B8"


class FactorBar(QWidget):
    def __init__(self, label: str, value: int, weight: float, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        top = QHBoxLayout()
        name = QLabel(f"{label} ({int(weight*100)}%)")
        name.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600;")
        val = QLabel(str(value))
        val.setStyleSheet(f"color: {_color_for_value(value)}; font-size: 11px; font-weight: 700;")
        top.addWidget(name)
        top.addStretch()
        top.addWidget(val)
        layout.addLayout(top)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(value)
        bar.setTextVisible(False)
        bar.setFixedHeight(8)
        color = _color_for_value(value)
        bar.setStyleSheet(f"""
            QProgressBar {{ background-color: #1B2A3A; border-radius: 4px; border: none; }}
            QProgressBar::chunk {{ background-color: {color}; border-radius: 4px; }}
        """)
        layout.addWidget(bar)


class BanScoreGauge(QWidget):
    def __init__(self, score: int, risk_label: str, risk_icon: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignCenter)

        score_label = QLabel(f"{score} / 100")
        score_label.setAlignment(Qt.AlignCenter)
        score_label.setStyleSheet(f"font-size: 30px; font-weight: 800; color: {_color_for_value(score)};")
        layout.addWidget(score_label)

        risk = QLabel(f"{risk_icon} {risk_label}")
        risk.setAlignment(Qt.AlignCenter)
        risk.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {_color_for_value(score)};")
        layout.addWidget(risk)
