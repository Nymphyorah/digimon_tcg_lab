from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel, QFileDialog, QMessageBox
)

from app.components.ban_column import BanColumn
from app.components.card_widget import CardWidget
from app.components.card_detail_dialog import CardDetailDialog
from app.components.card_picker_dialog import CardPickerDialog
from core.banlist_manager import RESTRICTIONS, RESTRICTION_META


class BanListPage(QWidget):
    navigate_requested = Signal(str)

    def __init__(self, repo, banlist, settings, analyzer, db, updater, collection=None, deckbuilder=None, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.banlist = banlist
        self.settings = settings

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 24)
        outer.setSpacing(16)

        header_row = QHBoxLayout()
        header_col = QVBoxLayout()
        header_col.setSpacing(2)
        title = QLabel("RESTRICTION BOARD")
        title.setObjectName("sectionLabel")
        header_col.addWidget(title)
        subtitle = QLabel("Arraste cartas entre as colunas ou clique numa carta para gerenciar sua restrição.")
        subtitle.setObjectName("sectionHint")
        header_col.addWidget(subtitle)
        header_row.addLayout(header_col)
        header_row.addStretch()
        outer.addLayout(header_row)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Pesquisar carta na Ban List...")
        self.search.textChanged.connect(self._apply_filter)
        toolbar.addWidget(self.search, 1)

        export_btn = QPushButton("↓ Exportar")
        export_btn.clicked.connect(self._export)
        toolbar.addWidget(export_btn)

        import_btn = QPushButton("↑ Importar")
        import_btn.setObjectName("primaryButton")
        import_btn.clicked.connect(self._import)
        toolbar.addWidget(import_btn)

        outer.addLayout(toolbar)

        columns_row = QHBoxLayout()
        columns_row.setSpacing(16)
        self.columns = {}
        for restriction in RESTRICTIONS:
            col = BanColumn(restriction)
            col.card_dropped.connect(self._on_card_dropped)
            col.add_card_requested.connect(self._on_add_card_requested)
            self.columns[restriction] = col
            columns_row.addWidget(col, 1)
        outer.addLayout(columns_row, 1)

        self._filter_text = ""

    def refresh(self):
        buckets = self.banlist.by_restriction()
        for restriction, col in self.columns.items():
            col.clear_cards()
            rows = buckets.get(restriction, [])
            filtered = [r for r in rows if self._matches_filter(r["card_id"])]
            col.set_count(len(rows))
            for i, row in enumerate(filtered):
                card = self.repo.card(row["card_id"])
                if not card:
                    continue
                widget = CardWidget(card, restriction=restriction, draggable=True, large=True)
                widget.clicked.connect(self._open_card_detail)
                col.add_card_widget(widget, i, 0)

    def _matches_filter(self, card_id):
        if not self._filter_text:
            return True
        card = self.repo.card(card_id)
        haystack = f'{card_id} {card.get("name","") if card else ""}'.lower()
        return self._filter_text.lower() in haystack

    def _apply_filter(self, text):
        self._filter_text = text
        self.refresh()

    def _on_card_dropped(self, card_id, restriction):
        self.banlist.set_restriction(card_id, restriction, reason="Movido via drag & drop")
        self.refresh()

    def _on_add_card_requested(self, restriction):
        meta = RESTRICTION_META[restriction]
        dlg = CardPickerDialog(self.repo, title=f'Add Card · {meta["label"]}', parent=self)
        if dlg.exec() == CardPickerDialog.DialogCode.Accepted and dlg.selected_card_id:
            self.banlist.set_restriction(dlg.selected_card_id, restriction, reason="Adicionado via + Add Card")
            self.refresh()

    def _open_card_detail(self, card_id):
        card = self.repo.card(card_id)
        if not card:
            return
        dlg = CardDetailDialog(card, self.repo, self.banlist, self.settings, parent=self)
        dlg.restriction_changed.connect(self.refresh)
        dlg.exec()

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exportar Ban List", "Minha-Ban-List.dtl", "Digimon TCG Lab (*.dtl);;JSON (*.json)")
        if not path:
            return
        try:
            self.banlist.export_to_file(path)
            QMessageBox.information(self, "Exportação concluída", f"Ban List exportada para:\n{path}")
        except OSError as e:
            QMessageBox.critical(self, "Erro ao exportar", str(e))

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importar Ban List", "", "Digimon TCG Lab (*.dtl);;JSON (*.json);;Todos os arquivos (*)")
        if not path:
            return
        try:
            count = self.banlist.import_from_file(path, merge=True)
            QMessageBox.information(self, "Importação concluída", f"{count} cartas importadas.")
            self.refresh()
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, "Erro ao importar", str(e))
