from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton


class FirstRunDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Digimon TCG Lab")
        self.setFixedSize(460, 360)
        self.setStyleSheet("QDialog { background-color: #070B12; }")
        self.setWindowFlag(Qt.FramelessWindowHint, False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel("DIGIMON TCG LAB")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: 800; letter-spacing: 2px;")
        layout.addWidget(title)

        subtitle = QLabel("Meta Analysis & Ban List Manager")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #2388FF; font-size: 11px; font-weight: 700; letter-spacing: 1px;")
        layout.addWidget(subtitle)
        layout.addSpacing(20)

        self.status = QLabel("Configurando banco local...")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet("color: #94A3B8;")
        layout.addWidget(self.status)
        layout.addSpacing(6)

        self.check_labels = []
        for text in ["Banco criado", "Configurações criadas", "Dados iniciais carregados"]:
            lbl = QLabel(f"○ {text}")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: #475569;")
            layout.addWidget(lbl)
            self.check_labels.append(lbl)

        layout.addSpacing(20)
        self.start_btn = QPushButton("COMEÇAR")
        self.start_btn.setObjectName("primaryButton")
        self.start_btn.setFixedHeight(42)
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self.accept)
        layout.addWidget(self.start_btn)

    def mark_done(self, index: int):
        if 0 <= index < len(self.check_labels):
            lbl = self.check_labels[index]
            text = lbl.text().replace("○", "✓")
            lbl.setText(text)
            lbl.setStyleSheet("color: #22C55E; font-weight: 600;")

    def finish(self):
        self.status.setText("Tudo pronto!")
        self.start_btn.setEnabled(True)
