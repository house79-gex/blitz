# v3 — Labels: associazioni multi-template per profilo ed elemento, UI QR code nei template
from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
import time

from PySide6.QtCore import Qt, QRect, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QListWidget, QListWidgetItem,
    QLineEdit, QPushButton, QGridLayout, QSizePolicy, QAbstractItemView, QStackedWidget,
    QFileDialog, QToolButton, QStyle, QComboBox, QCheckBox, QSpinBox,
    QTableWidget, QHeaderView, QTableWidgetItem, QMessageBox
)

from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel

try:
    from ui_qt.services.profiles_store import ProfilesStore
except Exception:
    ProfilesStore = None

try:
    from ui_qt.widgets.section_preview_popup import SectionPreviewPopup
except Exception:
    SectionPreviewPopup = None

try:
    from ui_qt.dialogs.profile_save_dialog import ProfileSaveDialog
except Exception:
    ProfileSaveDialog = None

try:
    from ui_qt.services.qcad_integration import suggest_qcad_paths, launch_qcad, find_export_file, parse_export_json, compute_dxf_bbox
except Exception:
    suggest_qcad_paths = lambda: []
    def launch_qcad(*args, **kwargs): raise RuntimeError("qcad_integration non disponibile")
    def find_export_file(workspace_dir: str): return None
    def parse_export_json(path: str): return (None, {})
    def compute_dxf_bbox(path: str): return None

try:
    from ui_qt.utils.theme_store import read_themes, get_active_theme, set_current_theme_name, save_theme_combo, get_current_theme_name
except Exception:
    def read_themes(): return {"Dark": {"palette": {}, "icons": {}}, "Light": {"palette": {}, "icons": {}}}
    def get_active_theme(): return {"palette": {}, "icons": {}}
    def set_current_theme_name(_n: str): pass
    def save_theme_combo(_n: str, _p: Dict[str, str], _i: Dict[str, str] | None = None): pass
    def get_current_theme_name(): return "Dark"

try:
    from ui_qt.theme import set_palette_from_dict, apply_global_stylesheet
except Exception:
    def set_palette_from_dict(_p: dict): pass
    def apply_global_stylesheet(_app): pass

try:
    from ui_qt.utils.settings import read_settings, write_settings
except Exception:
    def read_settings() -> Dict[str, Any]: return {}
    def write_settings(d: Dict[str, Any]) -> None: pass

try:
    from ui_qt.services.rs485_manager import RS485Manager, list_serial_ports_safe
except Exception:
    RS485Manager = None  # type: ignore
    def list_serial_ports_safe() -> List[str]: return ["COM3", "COM4", "/dev/ttyUSB0"]

# Store template etichette
try:
    from ui_qt.utils.label_templates_store import (
        list_templates, get_template, upsert_template, delete_template,
        duplicate_template, list_associations,
        set_profile_association, remove_profile_association, clear_profile_association,
        set_element_association, remove_element_association, clear_element_association
    )
except Exception:
    def list_templates(): return [{"name":"DEFAULT","paper":"DK-11201","rotate":0,"font_size":32,"cut":True,"lines":["{profile}"],"updated_at":None}]
    def get_template(name:str): return list_templates()[0]
    def upsert_template(*args, **kwargs): pass
    def delete_template(name:str): return False
    def duplicate_template(src:str,new:str): return False
    def list_associations(): return {"by_profile": {}, "by_element": {}}
    def set_profile_association(*args, **kwargs): pass
    def remove_profile_association(*args, **kwargs): pass
    def clear_profile_association(*args, **kwargs): pass
    def set_element_association(*args, **kwargs): pass
    def remove_element_association(*args, **kwargs): pass
    def clear_element_association(*args, **kwargs): pass

STATUS_W = 260


class UtilityPage(QWidget):
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = getattr(appwin, "machine", None)
        self.profiles_store = ProfilesStore() if ProfilesStore else None
        self._poll: Optional[QTimer] = None
        self._build()
        self._start_poll()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(8)
        header = Header(self.appwin, "UTILITY")
        root.addWidget(header, 0)

        main = QHBoxLayout()
        main.setSpacing(10)
        main.setContentsMargins(0, 0, 0, 0)
        root.addLayout(main, 1)

        menu = QFrame()
        menu.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        menu.setFixedWidth(200)
        menu.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius: 6px; }")
        menu_layout = QVBoxLayout(menu)
        menu_layout.setContentsMargins(8, 8, 8, 8)
        menu_layout.setSpacing(6)
        self.lst_menu = QListWidget()
        self.lst_menu.setSelectionMode(QAbstractItemView.SingleSelection)
        for label in ("Profili", "QCAD", "Backup", "Configurazione", "Temi", "Etichette"):
            self.lst_menu.addItem(QListWidgetItem(label))
        self.lst_menu.setCurrentRow(0)
        menu_layout.addWidget(QLabel("Sottomenu"))
        menu_layout.addWidget(self.lst_menu, 1)

        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.page_profiles = ProfilesSubPage(self.appwin, self.profiles_store)
        self.page_qcad = QcadSubPage(self.appwin, self.profiles_store)
        self.page_backup = BackupSubPage(self.appwin)
        self.page_config = ConfigSubPage(self.appwin)
        self.page_themes = ThemesSubPage(self.appwin)
        self.page_labels = LabelsSubPage(self.appwin, self.profiles_store)

        self.stack.addWidget(self.page_profiles)  # 0
        self.stack.addWidget(self.page_qcad)      # 1
        self.stack.addWidget(self.page_backup)    # 2
        self.stack.addWidget(self.page_config)    # 3
        self.stack.addWidget(self.page_themes)    # 4
        self.stack.addWidget(self.page_labels)    # 5

        right = QFrame()
        right.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        right.setFixedWidth(STATUS_W)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        self.status_panel = StatusPanel(self.machine, title="STATO")
        self.status_panel.setFixedWidth(STATUS_W)
        self.status_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        right_layout.addWidget(self.status_panel, 1)

        main.addWidget(menu, 0)
        main.addWidget(self.stack, 1)
        main.addWidget(right, 0)

        self.lst_menu.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.page_profiles.openInCadRequested.connect(self._open_in_qcad_on_profile)

    def _start_poll(self):
        self._poll = QTimer(self)
        self._poll.setInterval(250)
        self._poll.timeout.connect(self._tick)
        self._poll.start()

    def _tick(self):
        try:
            self.status_panel.refresh()
        except Exception:
            pass

    def _open_in_qcad_on_profile(self, dxf_path: str):
        self.stack.setCurrentIndex(1)
        items = self.lst_menu.findItems("QCAD", Qt.MatchExactly)
        if items:
            self.lst_menu.setCurrentItem(items[0])
        try:
            self.page_qcad.open_qcad_with_path(dxf_path)
        except Exception:
            pass

    def on_show(self):
        try:
            self.page_profiles.reload_profiles()
        except Exception:
            pass
        try:
            self.page_labels.reload_profiles_combo()
            self.page_labels.reload_assoc_ui()
            self.page_labels.reload_templates_list()
        except Exception:
            pass

    def hideEvent(self, ev):
        try:
            self.page_profiles.close_preview()
        except Exception:
            pass
        super().hideEvent(ev)


class ProfilesSubPage(QFrame):
    openInCadRequested = Signal(str)
    # ... copia invariata dal file già in uso (omesso per brevità) ...


class QcadSubPage(QFrame):
    # ... copia invariata dal file già in uso (omesso per brevità) ...
    pass


class BackupSubPage(QFrame):
    # ... copia invariata dal file già in uso (omesso per brevità) ...
    pass


class ConfigSubPage(QFrame):
    # ... copia invariata dal file già in uso (omesso per brevità) ...
    pass


class ThemesSubPage(QFrame):
    # ... copia invariata dal file già in uso (omesso per brevità) ...
    pass


class LabelsSubPage(QFrame):
    """
    Gestione template etichette + associazioni
    - Per profilo: multi-template
    - Per elemento (scoped al profilo): multi-template
    - QR code opzionale in template
    Placeholder disponibili: campi base + meta elemento, es.:
      {profile} {element} {length_mm:.2f} {ang_sx:.1f} {ang_dx:.1f} {seq_id} {timestamp}
      {commessa} {element_id} {infisso_id} {misura_elem} ecc...
    """
    def __init__(self, appwin, profiles_store):
        super().__init__()
        self.appwin = appwin
        self.profiles_store = profiles_store
        self._current_tmpl_name: Optional[str] = None
        self._build()
        self.reload_templates_list()
        self.reload_profiles_combo()
        self.reload_assoc_ui()

    # compat nome usato in on_show
    def reload_templates_list(self):
        self._reload_templates()
    def reload_assoc_ui(self):
        self._reload_assoc_list()

    def _build(self):
        self.setStyleSheet("QFrame { border:1px solid #3b4b5a; border-radius:6px; }")
        root = QVBoxLayout(self); root.setContentsMargins(8,8,8,8); root.setSpacing(8)

        title = QLabel("Etichette - Template & Associazioni (Profilo/Elemento)")
        title.setStyleSheet("font-weight:800; font-size:16px;")
        root.addWidget(title, 0)

        top = QHBoxLayout()
        self.lst_templates = QListWidget()
        self.lst_templates.setMinimumWidth(240)
        self.lst_templates.currentItemChanged.connect(self._on_select_template)
        top.addWidget(self.lst_templates, 0)

        editor_box = QFrame()
        eb = QGridLayout(editor_box); eb.setContentsMargins(6,6,6,6); eb.setHorizontalSpacing(8); eb.setVerticalSpacing(6)
        r = 0
        eb.addWidget(QLabel("Nome:"), r,0)
        self.ed_name = QLineEdit(); eb.addWidget(self.ed_name, r,1,1,3); r+=1
        eb.addWidget(QLabel("Carta:"), r,0)
        self.cmb_paper = QComboBox(); self.cmb_paper.addItems(["DK-11201","DK-11202","DK-11209","DK-22205"])
        eb.addWidget(self.cmb_paper, r,1)
        eb.addWidget(QLabel("Rotazione:"), r,2)
        self.cmb_rotate = QComboBox(); self.cmb_rotate.addItems(["0","90","180","270"])
        eb.addWidget(self.cmb_rotate, r,3); r+=1
        eb.addWidget(QLabel("Font size:"), r,0)
        self.ed_font = QLineEdit("32"); eb.addWidget(self.ed_font, r,1)
        self.chk_cut = QCheckBox("Taglio automatico"); self.chk_cut.setChecked(True)
        eb.addWidget(self.chk_cut, r,2,1,2); r+=1

        eb.addWidget(QLabel("Linee (una per riga):"), r,0,1,4); r+=1
        self.tbl_lines = QTableWidget(0,1)
        self.tbl_lines.setHorizontalHeaderLabels(["Contenuto"])
        self.tbl_lines.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        eb.addWidget(self.tbl_lines, r,0,1,4); r+=1

        # QR settings
        eb.addWidget(QLabel("QR data (opzionale, formattabile):"), r,0,1,4); r+=1
        self.ed_qr_data = QLineEdit(); eb.addWidget(self.ed_qr_data, r,0,1,3)
        self.spin_qr_mod = QSpinBox(); self.spin_qr_mod.setRange(2,10); self.spin_qr_mod.setValue(4)
        eb.addWidget(QLabel("Modulo:"), r,3); r+=1
        eb.addWidget(self.spin_qr_mod, r,3); r+=1

        row_btn = QHBoxLayout()
        btn_add_line = QPushButton("+ Linea"); btn_add_line.clicked.connect(self._add_line)
        btn_del_line = QPushButton("- Linea"); btn_del_line.clicked.connect(self._del_line)
        row_btn.addWidget(btn_add_line); row_btn.addWidget(btn_del_line); row_btn.addStretch(1)
        eb.addLayout(row_btn, r,0,1,4); r+=1

        actions_row = QHBoxLayout()
        btn_new = QPushButton("Nuovo"); btn_new.clicked.connect(self._new_template)
        btn_dup = QPushButton("Duplica"); btn_dup.clicked.connect(self._duplicate_template)
        btn_save = QPushButton("Salva"); btn_save.clicked.connect(self._save_template)
        btn_delete = QPushButton("Elimina"); btn_delete.clicked.connect(self._delete_template)
        btn_test = QPushButton("Test stampa"); btn_test.clicked.connect(self._test_print_current)
        actions_row.addWidget(btn_new); actions_row.addWidget(btn_dup)
        actions_row.addWidget(btn_save); actions_row.addWidget(btn_delete)
        actions_row.addWidget(btn_test); actions_row.addStretch(1)
        eb.addLayout(actions_row, r,0,1,4); r+=1

        # Associazioni
        assoc_box = QFrame()
        assoc_box.setStyleSheet("QFrame { border:1px solid #3b4b5a; border-radius:6px; }")
        al = QGridLayout(assoc_box); al.setContentsMargins(6,6,6,6); al.setHorizontalSpacing(8); al.setVerticalSpacing(6)
        rr = 0
        al.addWidget(QLabel("Associazioni"), rr,0,1,4); rr+=1
        # per profilo
        al.addWidget(QLabel("Profilo:"), rr,0)
        self.cmb_profile = QComboBox(); al.addWidget(self.cmb_profile, rr,1)
        al.addWidget(QLabel("Template:"), rr,2)
        self.cmb_template_assoc = QComboBox(); al.addWidget(self.cmb_template_assoc, rr,3); rr+=1
        btn_set_prof = QPushButton("Imposta su profilo"); btn_set_prof.clicked.connect(self._set_assoc_prof)
        btn_rem_prof = QPushButton("Rimuovi da profilo"); btn_rem_prof.clicked.connect(self._remove_assoc_prof)
        al.addWidget(btn_set_prof, rr,0,1,2); al.addWidget(btn_rem_prof, rr,2,1,2); rr+=1
        # per elemento
        al.addWidget(QLabel("Elemento (nome):"), rr,0)
        self.ed_element = QLineEdit(); self.ed_element.setPlaceholderText("es. Montante, Traverso...")
        al.addWidget(self.ed_element, rr,1)
        al.addWidget(QLabel("Template:"), rr,2)
        self.cmb_template_elem = QComboBox(); al.addWidget(self.cmb_template_elem, rr,3); rr+=1
        btn_set_el = QPushButton("Imposta su elemento"); btn_set_el.clicked.connect(self._set_assoc_elem)
        btn_rem_el = QPushButton("Rimuovi da elemento"); btn_rem_el.clicked.connect(self._remove_assoc_elem)
        al.addWidget(btn_set_el, rr,0,1,2); al.addWidget(btn_rem_el, rr,2,1,2); rr+=1

        self.lbl_assoc_prof = QLabel("Profili: —")
        self.lbl_assoc_prof.setStyleSheet("color:#7f8c8d;")
        self.lbl_assoc_elem = QLabel("Elementi: —")
        self.lbl_assoc_elem.setStyleSheet("color:#7f8c8d;")
        al.addWidget(QLabel("Associazioni profilo:"), rr,0,1,1); al.addWidget(self.lbl_assoc_prof, rr,1,1,3); rr+=1
        al.addWidget(QLabel("Associazioni elemento:"), rr,0,1,1); al.addWidget(self.lbl_assoc_elem, rr,1,1,3); rr+=1

        wrapper = QVBoxLayout()
        wrapper.addWidget(editor_box,0)
        wrapper.addWidget(assoc_box,0)
        top.addLayout(wrapper, 1)

        root.addLayout(top,1)
        hint = QLabel("Placeholder: {profile} {element} {length_mm:.2f} {ang_sx:.1f} {ang_dx:.1f} {seq_id} {timestamp} + meta (es. {commessa} {element_id} {infisso_id} ...).")
        hint.setStyleSheet("color:#7f8c8d;")
        root.addWidget(hint,0)
        root.addStretch(1)

    def _reload_templates(self):
        self.lst_templates.blockSignals(True)
        self.lst_templates.clear()
        for t in list_templates():
            self.lst_templates.addItem(t["name"])
        self.lst_templates.blockSignals(False)
        self._reload_assoc_list()
        self._reload_assoc_template_combos()

    def _reload_assoc_template_combos(self):
        self.cmb_template_assoc.clear()
        self.cmb_template_elem.clear()
        for t in list_templates():
            self.cmb_template_assoc.addItem(t["name"])
            self.cmb_template_elem.addItem(t["name"])

    def reload_profiles_combo(self):
        self.cmb_profile.clear()
        if self.profiles_store:
            try:
                for r in self.profiles_store.list_profiles():
                    n = str(r.get("name") or "").strip()
                    if n:
                        self.cmb_profile.addItem(n)
            except Exception:
                pass
        if self.cmb_profile.count() == 0:
            self.cmb_profile.addItem("Nessuno")

    def _reload_assoc_list(self):
        assoc = list_associations()
        # Profili
        bp = assoc.get("by_profile", {}) or {}
        if not bp:
            self.lbl_assoc_prof.setText("—")
        else:
            txt = ", ".join(f"{p}→{','.join(v if isinstance(v,list) else [v])}" for p, v in sorted(bp.items()))
            self.lbl_assoc_prof.setText(txt)
        # Elementi
        be = assoc.get("by_element", {}) or {}
        if not be:
            self.lbl_assoc_elem.setText("—")
        else:
            parts: List[str] = []
            for prof, emap in sorted(be.items()):
                if not isinstance(emap, dict): continue
                for el, lst in sorted(emap.items()):
                    v = ",".join(lst if isinstance(lst, list) else [lst])
                    parts.append(f"{prof}/{el}→{v}")
            self.lbl_assoc_elem.setText(", ".join(parts) if parts else "—")

    def _on_select_template(self, cur, prev):
        if not cur: return
        name = cur.text().strip()
        t = get_template(name)
        if not t: return
        self._current_tmpl_name = name
        self.ed_name.setText(name)
        self.cmb_paper.setCurrentText(str(t.get("paper","DK-11201")))
        self.cmb_rotate.setCurrentText(str(int(t.get("rotate",0))))
        self.ed_font.setText(str(int(t.get("font_size",32))))
        self.chk_cut.setChecked(bool(t.get("cut",True)))
        # QR
        qr = t.get("qrcode") or {}
        self.ed_qr_data.setText(str(qr.get("data","")) if isinstance(qr, dict) else "")
        try: self.spin_qr_mod.setValue(int(qr.get("module_size", 4)))
        except Exception: self.spin_qr_mod.setValue(4)
        # lines
        self.tbl_lines.setRowCount(0)
        for line in t.get("lines", []):
            r = self.tbl_lines.rowCount()
            self.tbl_lines.insertRow(r)
            it = QTableWidgetItem(line)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsEditable | Qt.ItemIsSelectable)
            self.tbl_lines.setItem(r, 0, it)

    def _collect_lines(self) -> List[str]:
        lines = []
        for r in range(self.tbl_lines.rowCount()):
            it = self.tbl_lines.item(r,0)
            if it:
                txt = (it.text() or "").rstrip()
                if txt:
                    lines.append(txt)
        return lines

    def _new_template(self):
        base = "Nuovo"; name = base; i = 1
        while get_template(name): i += 1; name = f"{base}_{i}"
        upsert_template(name,"DK-11201",0,32,True,["{profile}","{element}","L={length_mm:.2f}","SEQ:{seq_id}"], qrcode=None)
        self._reload_templates()
        items = self.lst_templates.findItems(name, Qt.MatchExactly)
        if items: self.lst_templates.setCurrentItem(items[0])

    def _duplicate_template(self):
        if not self._current_tmpl_name: return
        base = f"{self._current_tmpl_name}_COPY"; name = base; i = 1
        while get_template(name): i += 1; name = f"{base}_{i}"
        duplicate_template(self._current_tmpl_name, name)
        self._reload_templates()
        items = self.lst_templates.findItems(name, Qt.MatchExactly)
        if items: self.lst_templates.setCurrentItem(items[0])

    def _save_template(self):
        name = (self.ed_name.text() or "").strip()
        if not name:
            QMessageBox.information(self,"Template","Nome mancante."); return
        paper = self.cmb_paper.currentText()
        rotate = int(self.cmb_rotate.currentText())
        try: font_size = int(float((self.ed_font.text() or "32").replace(",", ".")))
        except Exception: font_size = 32
        cut = bool(self.chk_cut.isChecked())
        lines = self._collect_lines()
        qr_data = (self.ed_qr_data.text() or "").strip()
        qrcode = {"data": qr_data, "module_size": int(self.spin_qr_mod.value())} if qr_data else None
        upsert_template(name, paper, rotate, font_size, cut, lines, qrcode=qrcode)
        self._reload_templates()
        items = self.lst_templates.findItems(name, Qt.MatchExactly)
        if items: self.lst_templates.setCurrentItem(items[0])
        QMessageBox.information(self,"Template","Salvato.")

    def _delete_template(self):
        if not self._current_tmpl_name: return
        if not delete_template(self._current_tmpl_name):
            QMessageBox.information(self,"Template","Impossibile eliminare (DEFAULT o inesistente)."); return
        self._current_tmpl_name = None
        self._reload_templates()
        self.tbl_lines.setRowCount(0)
        self.ed_name.clear()

    def _add_line(self):
        r = self.tbl_lines.rowCount()
        self.tbl_lines.insertRow(r)
        it = QTableWidgetItem("{profile}")
        it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsEditable | Qt.ItemIsSelectable)
        self.tbl_lines.setItem(r,0,it)

    def _del_line(self):
        r = self.tbl_lines.currentRow()
        if r >= 0: self.tbl_lines.removeRow(r)

    # Associazioni
    def _set_assoc_prof(self):
        prof = (self.cmb_profile.currentText() or "").strip()
        tmpl = (self.cmb_template_assoc.currentText() or "").strip()
        if not prof or prof == "Nessuno" or not tmpl: return
        try:
            set_profile_association(prof, tmpl)
        except Exception as e:
            QMessageBox.critical(self,"Assoc profilo",str(e)); return
        self._reload_assoc_list()
        QMessageBox.information(self,"Assoc","Associato al profilo.")

    def _remove_assoc_prof(self):
        prof = (self.cmb_profile.currentText() or "").strip()
        tmpl = (self.cmb_template_assoc.currentText() or "").strip()
        if not prof or prof == "Nessuno" or not tmpl: return
        remove_profile_association(prof, tmpl)
        self._reload_assoc_list()
        QMessageBox.information(self,"Assoc","Rimosso dal profilo.")

    def _set_assoc_elem(self):
        prof = (self.cmb_profile.currentText() or "").strip()
        elem = (self.ed_element.text() or "").strip()
        tmpl = (self.cmb_template_elem.currentText() or "").strip()
        if not prof or prof == "Nessuno" or not elem or not tmpl: return
        try:
            set_element_association(prof, elem, tmpl)
        except Exception as e:
            QMessageBox.critical(self,"Assoc elemento",str(e)); return
        self._reload_assoc_list()
        QMessageBox.information(self,"Assoc","Associato all'elemento.")

    def _remove_assoc_elem(self):
        prof = (self.cmb_profile.currentText() or "").strip()
        elem = (self.ed_element.text() or "").strip()
        tmpl = (self.cmb_template_elem.currentText() or "").strip()
        if not prof or prof == "Nessuno" or not elem or not tmpl: return
        remove_element_association(prof, elem, tmpl)
        self._reload_assoc_list()
        QMessageBox.information(self,"Assoc","Rimosso dall'elemento.")

    def _test_print_current(self):
        name = (self.ed_name.text() or "").strip()
        if not name:
            QMessageBox.information(self,"Test","Seleziona/Salva prima un template."); return
        tmpl = get_template(name)
        if not tmpl:
            QMessageBox.information(self,"Test","Template non trovato."); return
        piece = {"profile":"DEMO-PROFILO","element":"Montante #1",
                 "length_mm":1234.56,"ang_sx":45.0,"ang_dx":0.0,"seq_id":999,
                 "qty_remaining":7,
                 "commessa":"JOB-2025-001","element_id":"E-0001","infisso_id":"W-42","misura_elem":1234.56}
        fmt = dict(piece)
        lines = []
        for raw in tmpl.get("lines", []):
            try:
                lines.append(str(raw).format(**fmt))
            except Exception:
                lines.append(str(raw))
        # Usa appwin.label_printer se presente, altrimenti solo messaggio
        lp = getattr(self.appwin, "label_printer", None)
        if lp and hasattr(lp, "print_label"):
            qr = tmpl.get("qrcode") or {}
            data = None
            if isinstance(qr, dict) and qr.get("data"):
                try: data = str(qr["data"]).format(**fmt)
                except Exception: data = str(qr["data"])
            ok = lp.print_label(lines,
                                paper=tmpl.get("paper"),
                                rotate=int(tmpl.get("rotate",0)),
                                font_size=int(tmpl.get("font_size",32)),
                                cut=bool(tmpl.get("cut",True)),
                                qrcode_data=data,
                                qrcode_module_size=int(qr.get("module_size",4)) if isinstance(qr, dict) else 4)
            QMessageBox.information(self,"Test","Etichetta stampata." if ok else "Stampa fallita.")
        else:
            QMessageBox.information(self,"Test","Printer non disponibile (integra appwin.label_printer).")
