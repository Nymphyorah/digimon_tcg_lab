from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QComboBox, QPushButton,
    QScrollArea, QSlider, QMessageBox
)

from core.ban_score import DEFAULT_WEIGHTS


WEIGHT_LABELS = {
    "meta_usage": "Meta Usage",
    "top_cut": "Top Cut",
    "performance": "Performance",
    "avg_copies": "Average Copies",
    "diversity": "Diversity",
    "growth": "Growth",
}


class SettingsPage(QWidget):
    navigate_requested = Signal(str)

    def __init__(self, repo, banlist, settings, analyzer, db, updater, collection=None, deckbuilder=None, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.settings = settings
        self.db = db
        self.updater = updater

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(20)
        scroll.setWidget(content)

        layout.addWidget(self._build_data_section())
        layout.addWidget(self._build_preferences_section())
        layout.addWidget(self._build_ban_score_section())
        layout.addWidget(self._build_storage_section())
        layout.addStretch()

    def _section(self, title):
        box = QFrame()
        box.setObjectName("surface")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        header = QLabel(title.upper())
        header.setObjectName("sectionLabel")
        layout.addWidget(header)
        return box, layout

    def _build_data_section(self):
        box, layout = self._section("Dados")
        version = self.repo.version
        self.data_updated_label = QLabel(f'Última atualização: {version.get("meta_version", "--")}')
        self.data_updated_label.setStyleSheet("color: #F8FAFC; font-size: 13px;")
        layout.addWidget(self.data_updated_label)

        btn_row = QHBoxLayout()
        check_btn = QPushButton("VERIFICAR ATUALIZAÇÕES")
        check_btn.clicked.connect(self._check_updates)
        update_btn = QPushButton("ATUALIZAR AGORA")
        update_btn.setObjectName("primaryButton")
        update_btn.clicked.connect(self._update_now)
        btn_row.addWidget(check_btn)
        btn_row.addWidget(update_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        source = self.repo.meta.get("source")
        if source:
            credit = QLabel(f"Dados de meta e torneios: {source}")
            credit.setObjectName("sectionHint")
            layout.addWidget(credit)
        return box

    def _build_preferences_section(self):
        box, layout = self._section("Preferências")

        row = QHBoxLayout()
        for label, key, options in [
            ("Formato", "format", ["English", "Japanese", "Chinese"]),
            ("Período", "period_days", ["7", "30", "90"]),
        ]:
            col = QVBoxLayout()
            lbl = QLabel(label.upper())
            lbl.setStyleSheet("color: #64748B; font-size: 10px; font-weight: 700;")
            combo = QComboBox()
            combo.addItems(options)
            current = str(self.settings.get(key))
            if current in options:
                combo.setCurrentText(current)
            combo.currentTextChanged.connect(lambda v, k=key: self.settings.set(k, v))
            col.addWidget(lbl)
            col.addWidget(combo)
            row.addLayout(col)
        row.addStretch()
        layout.addLayout(row)
        return box

    def _build_ban_score_section(self):
        box, layout = self._section("Pesos do Ban Score")
        note = QLabel("Ajuste a importância de cada fator no cálculo do Ban Score.")
        note.setObjectName("sectionHint")
        layout.addWidget(note)

        weights = self.settings.get("ban_score_weights", DEFAULT_WEIGHTS)
        self.weight_sliders = {}
        self.weight_value_labels = {}
        for key, label in WEIGHT_LABELS.items():
            row = QHBoxLayout()
            name = QLabel(label)
            name.setFixedWidth(140)
            name.setStyleSheet("color: #F8FAFC; font-size: 12px;")
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(int(weights.get(key, DEFAULT_WEIGHTS[key]) * 100))
            value_label = QLabel(f"{slider.value()}%")
            value_label.setFixedWidth(40)
            value_label.setStyleSheet("color: #2388FF; font-weight: 700;")
            slider.valueChanged.connect(lambda v, k=key, l=value_label: self._on_weight_changed(k, v, l))
            row.addWidget(name)
            row.addWidget(slider, 1)
            row.addWidget(value_label)
            layout.addLayout(row)
            self.weight_sliders[key] = slider
            self.weight_value_labels[key] = value_label

        reset_btn = QPushButton("Restaurar padrão")
        reset_btn.clicked.connect(self._reset_weights)
        layout.addWidget(reset_btn, alignment=Qt.AlignRight)
        return box

    def _on_weight_changed(self, key, value, label):
        label.setText(f"{value}%")
        weights = dict(self.settings.get("ban_score_weights", DEFAULT_WEIGHTS))
        weights[key] = value / 100.0
        self.settings.set("ban_score_weights", weights)

    def _reset_weights(self):
        self.settings.set("ban_score_weights", dict(DEFAULT_WEIGHTS))
        for key, slider in self.weight_sliders.items():
            slider.setValue(int(DEFAULT_WEIGHTS[key] * 100))

    def _build_storage_section(self):
        box, layout = self._section("Armazenamento")
        size_mb = self.db.db_size_bytes() / (1024 * 1024)
        rows = [
            ("Database", f"{size_mb:.1f} MB"),
            ("Cards", str(len(self.repo.cards))),
            ("Meta Records", str(len(self.repo.meta.get("ban_candidates", [])) + len(self.repo.decks) + len(self.repo.tournaments))),
        ]
        for label, value in rows:
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #94A3B8; font-size: 12px;")
            val = QLabel(value)
            val.setStyleSheet("color: #F8FAFC; font-size: 12px; font-weight: 700;")
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(val)
            layout.addLayout(row)
        return box

    def refresh(self):
        pass

    def _check_updates(self):
        remote = self.updater.check_data_update()
        if remote:
            QMessageBox.information(
                self, "Atualização disponível",
                f'Novos dados disponíveis: {remote.get("meta_version")}\n'
                f'Sua versão: {self.repo.version.get("meta_version")}'
            )
        else:
            QMessageBox.information(self, "Dados atualizados", "Você já está com os dados mais recentes disponíveis (ou está offline).")

    def _update_now(self):
        QMessageBox.information(
            self, "Atualização de dados",
            "A sincronização com o pipeline de dados público ainda não está configurada nesta versão.\n"
            "Os dados locais continuam disponíveis normalmente."
        )
