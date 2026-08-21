"""Shared, neutral 0-100% metric bar — used everywhere the app shows one of
the three real competitive-presence indicators (Meta Usage, Top Cut,
Dominance). Deliberately a single flat accent color rather than a
red/orange/yellow escalation: these are objective measurements, not a risk
score, so nothing here should look like a verdict."""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar

BAR_COLOR = "#2388FF"


class MetricBar(QWidget):
    """Label + big progress bar, e.g. for the Card Detail dialog."""

    def __init__(self, label: str, value: float, suffix: str = "%", color: str = BAR_COLOR, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        top = QHBoxLayout()
        name = QLabel(label.upper())
        name.setObjectName("sectionLabel")
        val = QLabel(f"{value:g}{suffix}")
        val.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 800;")
        top.addWidget(name)
        top.addStretch()
        top.addWidget(val)
        layout.addLayout(top)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(max(0, min(100, round(value))))
        bar.setTextVisible(False)
        bar.setFixedHeight(10)
        bar.setStyleSheet(f"""
            QProgressBar {{ background-color: #1B2A3A; border-radius: 5px; border: none; }}
            QProgressBar::chunk {{ background-color: {color}; border-radius: 5px; }}
        """)
        layout.addWidget(bar)


class MetricInline(QWidget):
    """Compact one-line 'LABEL  value%' readout — for hover popups, tile
    badges and other tight spaces where a full bar doesn't fit."""

    def __init__(self, label: str, value: float, suffix: str = "%", color: str = BAR_COLOR, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        name = QLabel(label.upper())
        name.setStyleSheet("color: #6B7F97; font-size: 10px; font-weight: 700;")
        val = QLabel(f"{value:g}{suffix}")
        val.setStyleSheet(f"color: {color}; font-size: 10.5px; font-weight: 800;")
        layout.addWidget(name)
        layout.addWidget(val)
        layout.addStretch()


INDICATOR_FIELDS = [
    ("meta_usage", "Meta Usage"),
    ("top_cut", "Top Cut"),
    ("dominance", "Dominance"),
]


def presence_notes(candidate: dict, threshold: float = 60.0) -> list:
    """Neutral, factual phrases for indicators that are high — never a
    restriction verdict. Empty list when nothing clears the threshold."""
    phrases = {
        "meta_usage": "Strong Meta Usage",
        "top_cut": "High Top Cut presence",
        "dominance": "High Dominance",
    }
    return [
        phrases[key]
        for key, _label in INDICATOR_FIELDS
        if candidate.get(key, 0) >= threshold
    ]
