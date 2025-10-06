from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QLineEdit, QMessageBox, QDialog, QListWidget, QDialogButtonBox, QFormLayout, QSpinBox, QDoubleSpinBox, QComboBox
)
from PySide6.QtCore import Qt
from ui_qt.widgets.header import Header
from ui_qt.theme import THEME
    # commit
from ui_qt.data import commesse_dao as cdao, tipologie_dao as tdao

class QuoteVaniPage(QWidget):
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self._current_id: int | None = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(8,8,8,8); root.setSpacing(6)
        root.addWidget(Header(self.appwin, "QUOTE VANI LUCE (COMMESSE)"))

        body = QHBoxLayout(); body.setSpacing(8); root.addLayout(body, 1)

        # Sinistra: anagrafica commessa
        left = QFrame(); body.addWidget(left, 1)
        ll = QVBoxLayout(left); ll.setContentsMargins(6,6,6,6)

        title = QLabel("COMMESSA"); title.setStyleSheet("font-weight:700;")
        ll.addWidget(title)

        row_id = QHBoxLayout()
        row_id.addWidget(QLabel("ID:"))
        self.lbl_comm_id = QLabel("-"); self.lbl_comm_id.setStyleSheet(f"color:{THEME.WARN}; font-family:Consolas; font-weight:700;")
        row_id.addWidget(self.lbl_comm_id); row_id.addStretch(1)
        ll.addLayout(row_id)

        row_cli = QHBoxLayout()
        row_cli.addWidget(QLabel("Cliente:"))
        self.ed_cliente = QLineEdit(); self.ed_cliente.setFixedWidth(200)
        row_cli.addWidget(self.ed_cliente); row_cli.addStretch(1)
        ll.addLayout(row_cli)

        row_note = QHBoxLayout()
        row_note.addWidget(QLabel("Note:"))
        self.ed_note = QLineEdit(); self.ed_note.setFixedWidth(200)
        row_note.addWidget(self.ed_note); row_note.addStretch(1)
        ll.addLayout(row_note)

        btns = QHBoxLayout()
        btn_new = QPushButton("Nuova"); btn_new.clicked.connect(self._new_commessa)
        btn_open = QPushButton("Apri"); btn_open.clicked.connect(self._open_commessa)
        btn_save = QPushButton("Salva"); btn_save.clicked.connect(self._save_commessa)
        btns.addWidget(btn_new); btns.addWidget(btn_open); btns.addWidget(btn_save); btns.addStretch(1)
        ll.addLayout(btns)

        # Destra: righe/pezzi della commessa
        right = QFrame(); body.addWidget(right, 2)
        rl = QVBoxLayout(right); rl.setContentsMargins(6,6,6,6)
        rl.addWidget(QLabel("Righe commessa"))
        self.list_items = QListWidget()
        rl.addWidget(self.list_items, 1)

        act = QHBoxLayout()
        btn_add = QPushButton("Aggiungi riga"); btn_add.clicked.connect(self._add_item)
        btn_del = QPushButton("Elimina riga"); btn_del.clicked.connect(self._del_item)
        act.addWidget(btn_add); act.addWidget(btn_del); act.addStretch(1)
        rl.addLayout(act)

    def on_show(self):
        if self._current_id:
            self._refresh_items()

    # CRUD commessa
    def _new_commessa(self):
        self._current_id = cdao.insert("", "")
        self.lbl_comm_id.setText(str(self._current_id))
        self.ed_cliente.setText("")
        self.ed_note.setText("")
        self.list_items.clear()
        QMessageBox.information(self, "Commesse", "Nuova commessa creata.")

    def _open_commessa(self):
        cid = CommessaPicker.pick(self)
        if cid is None:
            return
        row = cdao.get_by_id(cid)
        if not row:
            QMessageBox.warning(self, "Commesse", "Commessa non trovata.")
            return
        self._current_id = int(row["id"])
        self.lbl_comm_id.setText(str(self._current_id))
        self.ed_cliente.setText(str(row.get("cliente","")))
        self.ed_note.setText(str(row.get("note","")))
        self._refresh_items()

    def _save_commessa(self):
        if not self._current_id:
            QMessageBox.information(self, "Commesse", "Nessuna commessa attiva.")
            return
        cdao.update(self._current_id, self.ed_cliente.text().strip(), self.ed_note.text().strip())
        QMessageBox.information(self, "Commesse", "Commessa salvata.")

    # Righe
    def _refresh_items(self):
        self.list_items.clear()
        for r in cdao.items_for_commessa(self._current_id):
            tipon = r.get("tipologia_nome") or "-"
            self.list_items.addItem(f"#{r['id']} • {tipon} • {r['len_mm']} mm • x{r['qty']}")

    def _add_item(self):
        if not self._current_id:
            QMessageBox.information(self, "Commesse", "Crea o apri una commessa prima.")
            return
        data = {}
        if RigaDialog.edit(self, data):
            cdao.add_item(
                cid=self._current_id,
                tipologia_id=data.get("tipologia_id"),
                len_mm=float(data["len_mm"]),
                qty=int(data["qty"]),
            )
            self._refresh_items()

    def _del_item(self):
        it = self.list_items.currentItem()
        if not it:
            QMessageBox.information(self, "Commesse", "Seleziona una riga.")
            return
        # Parse id dalla stringa iniziale "#<id> • ..."
        try:
            txt = it.text()
            rid = int(txt.split("•",1)[0].strip()[1:])
        except Exception:
            QMessageBox.warning(self, "Commesse", "Formato riga non riconosciuto.")
            return
        if QMessageBox.question(self, "Conferma", f"Eliminare riga #{rid}?") == QMessageBox.Yes:
            cdao.delete_item(rid)
            self._refresh_items()

class CommessaPicker(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Seleziona commessa")
        lay = QVBoxLayout(self)
        self.list = QListWidget()
        self._rows = cdao.list_all()
        for r in self._rows:
            self.list.addItem(f"#{r['id']} • {r.get('cliente','')}")
        lay.addWidget(self.list, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    @staticmethod
    def pick(parent) -> int | None:
        dlg = CommessaPicker(parent)
        if dlg.exec() == QDialog.Accepted:
            i = dlg.list.currentRow()
            if i >= 0:
                return int(dlg._rows[i]["id"])
        return None

class RigaDialog(QDialog):
    def __init__(self, parent, data: dict):
        super().__init__(parent)
        self.setWindowTitle("Riga commessa")
        self.data = data
        lay = QFormLayout(self)

        # Tipologia (opzionale)
        self.cb_tipo = QComboBox()
        self._tipos = tdao.search()  # tutte
        self.cb_tipo.addItem("-", None)
        for r in self._tipos:
            self.cb_tipo.addItem(f"#{r['id']} {r['nome']}", int(r["id"]))
        lay.addRow("Tipologia:", self.cb_tipo)

        self.spin_len = QDoubleSpinBox(); self.spin_len.setRange(0.0, 1e7); self.spin_len.setDecimals(1); self.spin_len.setValue(500.0)
        lay.addRow("Lunghezza (mm):", self.spin_len)

        self.spin_qty = QSpinBox(); self.spin_qty.setRange(1, 100000); self.spin_qty.setValue(1)
        lay.addRow("Quantità:", self.spin_qty)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addRow(buttons)

    def _accept(self):
        self.data["tipologia_id"] = self.cb_tipo.currentData()
        self.data["len_mm"] = float(self.spin_len.value())
        self.data["qty"] = int(self.spin_qty.value())
        if self.data["len_mm"] <= 0 or self.data["qty"] <= 0:
            return
        self.accept()

    @staticmethod
    def edit(parent, data: dict) -> bool:
        dlg = RigaDialog(parent, data)
        return dlg.exec() == QDialog.Accepted
