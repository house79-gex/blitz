from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QLineEdit, QCheckBox, QTreeWidget, QTreeWidgetItem, QMessageBox, QDialog, QFormLayout, QDialogButtonBox, QComboBox
)
from PySide6.QtCore import Qt
from ui_qt.widgets.header import Header
from ui_qt.data import tipologie_dao as dao

class TipologiePage(QWidget):
    COLS = ("id", "nome", "categoria", "materiale", "rif", "extra", "attiva", "comp")
    HEADINGS = {
        "id":"ID","nome":"NOME","categoria":"CATEGORIA","materiale":"MATERIALE",
        "rif":"RIF","extra":"EXTRA","attiva":"ATTIVA","comp":"#COMP"
    }
    WIDTHS = {"id":70,"nome":200,"categoria":140,"materiale":140,"rif":70,"extra":160,"attiva":70,"comp":70}

    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine
        self._build()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(8,8,8,8); root.setSpacing(6)
        root.addWidget(Header(self.appwin, "TIPOLOGIE"))

        # Filtri
        filters = QHBoxLayout(); filters.setSpacing(8)
        root.addLayout(filters)
        filters.addWidget(QLabel("Categoria:"))
        self.ed_cat = QLineEdit(); filters.addWidget(self.ed_cat)
        filters.addWidget(QLabel("Materiale:"))
        self.ed_mat = QLineEdit(); filters.addWidget(self.ed_mat)
        filters.addWidget(QLabel("Cerca:"))
        self.ed_search = QLineEdit(); filters.addWidget(self.ed_search, 2)
        self.chk_only_active = QCheckBox("Solo Attive"); filters.addWidget(self.chk_only_active)
        btn_apply = QPushButton("APPLICA FILTRO"); btn_apply.clicked.connect(self.populate_tree)
        filters.addWidget(btn_apply); filters.addStretch(1)

        # Body
        body = QHBoxLayout(); body.setSpacing(8); root.addLayout(body, 1)

        left = QFrame(); body.addWidget(left, 2)
        llay = QVBoxLayout(left); llay.setContentsMargins(6,6,6,6)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([self.HEADINGS[c] for c in self.COLS])
        for i, c in enumerate(self.COLS):
            self.tree.setColumnWidth(i, self.WIDTHS[c])
        self.tree.itemSelectionChanged.connect(self.update_detail)
        llay.addWidget(self.tree, 1)

        crud = QHBoxLayout()
        btn_new = QPushButton("NUOVA"); btn_new.clicked.connect(self.create_tipologia)
        btn_edit = QPushButton("MODIFICA"); btn_edit.clicked.connect(self.edit_tipologia)
        btn_del = QPushButton("ELIMINA"); btn_del.clicked.connect(self.delete_tipologia)
        crud.addWidget(btn_new); crud.addWidget(btn_edit); crud.addWidget(btn_del); crud.addStretch(1)
        llay.addLayout(crud)

        right = QFrame(); body.addWidget(right, 1)
        rlay = QVBoxLayout(right); rlay.setContentsMargins(6,6,6,6)
        self.lbl_detail = QLabel("Dettagli selezione"); self.lbl_detail.setStyleSheet("font-weight:700;")
        rlay.addWidget(self.lbl_detail)
        self.lbl_detail_body = QLabel("-")
        self.lbl_detail_body.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.lbl_detail_body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        rlay.addWidget(self.lbl_detail_body, 1)

    def on_show(self):
        self.populate_tree()

    def _filters(self):
        return dict(
            categoria=self.ed_cat.text().strip(),
            materiale=self.ed_mat.text().strip(),
            search=self.ed_search.text().strip(),
            only_active=bool(self.chk_only_active.isChecked()),
        )

    def populate_tree(self):
        items = dao.search(**self._filters())
        self.tree.clear()
        for row in items:
            values = [
                str(row.get("id","")),
                str(row.get("nome","")),
                str(row.get("categoria","")),
                str(row.get("materiale","")),
                str(row.get("rif","")),
                str(row.get("extra","")),
                "Sì" if row.get("attiva", 0) else "No",
                str(row.get("comp", "")),
            ]
            it = QTreeWidgetItem(values)
            it.setData(0, Qt.UserRole, row)
            self.tree.addTopLevelItem(it)

    def _current_row(self):
        it = self.tree.currentItem()
        return it.data(0, Qt.UserRole) if it else None

    def update_detail(self):
        row = self._current_row()
        if not row:
            self.lbl_detail_body.setText("-"); return
        lines = []
        for c in self.COLS:
            v = "Sì" if c == "attiva" and row.get(c, 0) else row.get(c, "")
            lines.append(f"{self.HEADINGS[c]}: {v}")
        self.lbl_detail_body.setText("\n".join(map(str, lines)))

    # CRUD
    def create_tipologia(self):
        data = dict(nome="", categoria="", materiale="", rif="", extra="", attiva=1, comp=0)
        if TipologiaDialog.edit(self, data, title="Nuova tipologia"):
            tid = dao.insert(data)
            self.populate_tree()
            self._select_id(tid)

    def edit_tipologia(self):
        row = self._current_row()
        if not row:
            QMessageBox.information(self, "Tipologie", "Seleziona una tipologia.")
            return
        data = dict(row)
        if TipologiaDialog.edit(self, data, title=f"Modifica #{row['id']}"):
            dao.update(int(row["id"]), data)
            self.populate_tree()
            self._select_id(int(row["id"]))

    def delete_tipologia(self):
        row = self._current_row()
        if not row:
            QMessageBox.information(self, "Tipologie", "Seleziona una tipologia.")
            return
        if QMessageBox.question(self, "Conferma", f"Eliminare '{row.get('nome','')}'?") == QMessageBox.Yes:
            dao.delete(int(row["id"]))
            self.populate_tree()

    def _select_id(self, tid: int):
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            row = it.data(0, Qt.UserRole)
            if row and int(row.get("id", 0)) == tid:
                self.tree.setCurrentItem(it); break

class TipologiaDialog(QDialog):
    def __init__(self, parent, data: dict, title: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.data = data
        lay = QFormLayout(self)

        self.ed_nome = QLineEdit(str(data.get("nome",""))); lay.addRow("Nome:", self.ed_nome)
        self.ed_cat = QLineEdit(str(data.get("categoria",""))); lay.addRow("Categoria:", self.ed_cat)
        self.ed_mat = QLineEdit(str(data.get("materiale",""))); lay.addRow("Materiale:", self.ed_mat)
        self.ed_rif = QLineEdit(str(data.get("rif",""))); lay.addRow("Rif:", self.ed_rif)
        self.ed_extra = QLineEdit(str(data.get("extra",""))); lay.addRow("Extra:", self.ed_extra)
        self.cb_attiva = QComboBox(); self.cb_attiva.addItems(["No","Sì"]); self.cb_attiva.setCurrentIndex(1 if int(data.get("attiva",1)) else 0)
        lay.addRow("Attiva:", self.cb_attiva)
        self.ed_comp = QLineEdit(str(data.get("comp",0))); lay.addRow("#Comp:", self.ed_comp)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addRow(buttons)

    def _accept(self):
        try:
            self.data["nome"] = self.ed_nome.text().strip()
            self.data["categoria"] = self.ed_cat.text().strip()
            self.data["materiale"] = self.ed_mat.text().strip()
            self.data["rif"] = self.ed_rif.text().strip()
            self.data["extra"] = self.ed_extra.text().strip()
            self.data["attiva"] = 1 if self.cb_attiva.currentIndex() == 1 else 0
            self.data["comp"] = int(self.ed_comp.text().strip() or "0")
            if not self.data["nome"]:
                raise ValueError("Nome obbligatorio")
        except Exception as e:
            QMessageBox.warning(self, "Errore", str(e))
            return
        self.accept()

    @staticmethod
    def edit(parent, data: dict, title: str) -> bool:
        dlg = TipologiaDialog(parent, data, title)
        return dlg.exec() == QDialog.Accepted
