# v4.1 — Etichette: anteprima render, placeholder cliccabili, simulazione a video.
# Fix: ProfilesSubPage completo (con _build), costruttori QFrame corretti.

from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
import time, contextlib, json

from PySide6.QtCore import Qt, QRect, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QListWidget, QListWidgetItem,
    QLineEdit, QPushButton, QGridLayout, QSizePolicy, QAbstractItemView, QStackedWidget,
    QFileDialog, QToolButton, QStyle, QComboBox, QCheckBox, QSpinBox,
    QTableWidget, QHeaderView, QTableWidgetItem, QMessageBox, QTextEdit, QSplitter
)

from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel

try:
    from ui_qt.services.profiles_store import ProfilesStore
except Exception:
    ProfilesStore = None  # type: ignore

try:
    from ui_qt.widgets.section_preview_popup import SectionPreviewPopup
except Exception:
    SectionPreviewPopup = None  # type: ignore

try:
    from ui_qt.dialogs.profile_save_dialog import ProfileSaveDialog
except Exception:
    ProfileSaveDialog = None  # type: ignore

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

# Store template etichette (multi-template profilo/elemento)
try:
    from ui_qt.utils.label_templates_store import (
        list_templates, get_template, upsert_template, delete_template,
        duplicate_template, list_associations,
        set_profile_association, remove_profile_association, clear_profile_association,
        set_element_association, remove_element_association, clear_element_association,
        resolve_templates
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
    def resolve_templates(p,e=None): return [get_template("DEFAULT")]

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

    def __init__(self, appwin, profiles_store):
        super().__init__()
        self.appwin = appwin
        self.profiles = profiles_store
        self._profiles_index: Dict[str, float] = {}
        self._section_popup: Optional[SectionPreviewPopup] = None

        self.lst_profiles: Optional[QListWidget] = None
        self.edit_prof_name: Optional[QLineEdit] = None
        self.edit_prof_th: Optional[QLineEdit] = None
        self.btn_open_cad: Optional[QPushButton] = None

        self._build()
        self.reload_profiles()

    def _build(self):
        self.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius: 6px; }")
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        left = QFrame()
        left.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        left.setFixedWidth(260)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(6, 6, 6, 6)
        ll.setSpacing(6)
        ll.addWidget(QLabel("Profili"))
        self.lst_profiles = QListWidget()
        self.lst_profiles.setSelectionMode(QAbstractItemView.SingleSelection)
        self.lst_profiles.currentItemChanged.connect(self._on_select_profile)
        ll.addWidget(self.lst_profiles, 1)

        right = QFrame()
        rl = QGridLayout(right)
        rl.setContentsMargins(6, 6, 6, 6)
        rl.setHorizontalSpacing(8)
        rl.setVerticalSpacing(6)
        row = 0

        rl.addWidget(QLabel("Dettagli"), row, 0, 1, 4, alignment=Qt.AlignLeft)
        row += 1

        rl.addWidget(QLabel("Nome:"), row, 0)
        self.edit_prof_name = QLineEdit()
        rl.addWidget(self.edit_prof_name, row, 1, 1, 3)
        row += 1

        rl.addWidget(QLabel("Spessore (mm):"), row, 0)
        self.edit_prof_th = QLineEdit()
        self.edit_prof_th.setPlaceholderText("0.0")
        rl.addWidget(self.edit_prof_th, row, 1, 1, 3)
        row += 1

        btns = QHBoxLayout()
        btns.setSpacing(6)
        self.btn_new = QPushButton("Nuovo")
        self.btn_new.clicked.connect(self._new_profile)
        btns.addWidget(self.btn_new)
        self.btn_save = QPushButton("Salva")
        self.btn_save.clicked.connect(self._save_profile)
        btns.addWidget(self.btn_save)
        self.btn_delete = QPushButton("Elimina")
        self.btn_delete.clicked.connect(self._delete_profile)
        btns.addWidget(self.btn_delete)
        self.btn_open_cad = QPushButton("Apri in QCAD")
        self.btn_open_cad.setEnabled(False)
        self.btn_open_cad.clicked.connect(self._open_cad_for_current)
        btns.addWidget(self.btn_open_cad)
        rl.addLayout(btns, row, 0, 1, 4)
        row += 1

        tip = QLabel("Suggerimento: seleziona un profilo per la preview DXF (popup).")
        tip.setStyleSheet("color:#7f8c8d;")
        rl.addWidget(tip, row, 0, 1, 4)
        row += 1

        root.addWidget(left, 0)
        root.addWidget(right, 1)

    def reload_profiles(self):
        self._profiles_index.clear()
        if self.profiles:
            try:
                rows = self.profiles.list_profiles()
                for r in rows:
                    name = str(r.get("name"))
                    th = float(r.get("thickness") or 0.0)
                    if name:
                        self._profiles_index[name] = th
            except Exception:
                pass
        if not self._profiles_index:
            self._profiles_index = {"Nessuno": 0.0}
        if self.lst_profiles:
            self.lst_profiles.blockSignals(True)
            self.lst_profiles.clear()
            for name in sorted(self._profiles_index.keys()):
                self.lst_profiles.addItem(QListWidgetItem(name))
            self.lst_profiles.blockSignals(False)
            if self.lst_profiles.count() > 0:
                self.lst_profiles.setCurrentRow(0)

    def _get_selected_name(self) -> Optional[str]:
        it = self.lst_profiles.currentItem() if self.lst_profiles else None
        return it.text() if it else None

    def _on_select_profile(self, cur: Optional[QListWidgetItem], prev: Optional[QListWidgetItem]):
        if not cur:
            return
        name = cur.text()
        th = self._profiles_index.get(name, 0.0)
        self.edit_prof_name.setText(name)
        self.edit_prof_th.setText(str(th))
        self._show_profile_preview_ephemeral(name)
        # abilita bottone QCAD se c'è un DXF associato
        dxf_path = self._get_profile_dxf_path(name)
        self.btn_open_cad.setEnabled(bool(dxf_path))

    def _new_profile(self):
        base = "Nuovo"
        i = 1
        name = base
        while name in self._profiles_index:
            i += 1
            name = f"{base} {i}"
        self._profiles_index[name] = 0.0
        self.lst_profiles.addItem(QListWidgetItem(name))
        self.lst_profiles.setCurrentRow(self.lst_profiles.count() - 1)
        self.edit_prof_name.setText(name)
        self.edit_prof_th.setText("0.0")

    def _save_profile(self):
        name = (self.edit_prof_name.text() or "").strip()
        ths = (self.edit_prof_th.text() or "").strip()
        try:
            th = float((ths or "0").replace(",", "."))
        except Exception:
            th = 0.0
        if not name:
            return
        if self.profiles and hasattr(self.profiles, "upsert_profile"):
            try:
                self.profiles.upsert_profile(name, th)
            except Exception:
                pass
        self._profiles_index[name] = th
        names = {self.lst_profiles.item(i).text() for i in range(self.lst_profiles.count())}
        if name not in names:
            self.lst_profiles.addItem(QListWidgetItem(name))
        self._sort_list_widget(self.lst_profiles)
        items = self.lst_profiles.findItems(name, Qt.MatchExactly)
        if items:
            self.lst_profiles.setCurrentItem(items[0])

    def _delete_profile(self):
        name = self._get_selected_name()
        if not name:
            return
        if self.profiles and hasattr(self.profiles, "delete_profile"):
            try:
                self.profiles.delete_profile(name)
            except Exception:
                pass
        if name in self._profiles_index:
            del self._profiles_index[name]
        row = self.lst_profiles.currentRow()
        it = self.lst_profiles.takeItem(row); del it
        if self.lst_profiles.count() > 0:
            self.lst_profiles.setCurrentRow(min(row, self.lst_profiles.count() - 1))
        else:
            self.edit_prof_name.clear(); self.edit_prof_th.clear()
        self.close_preview()

    def _open_cad_for_current(self):
        name = self._get_selected_name()
        if not name: return
        dxf_path = self._get_profile_dxf_path(name)
        if dxf_path: self.openInCadRequested.emit(dxf_path)

    def close_preview(self):
        try:
            if self._section_popup:
                self._section_popup.close()
                self._section_popup = None
        except Exception:
            self._section_popup = None

    def _ensure_popup(self) -> Optional[SectionPreviewPopup]:
        if SectionPreviewPopup is None: return None
        if self._section_popup is None:
            self._section_popup = SectionPreviewPopup(self.appwin, "Sezione profilo")
        return self._section_popup

    def _get_profile_shape(self, name: str) -> Optional[Dict[str, Any]]:
        if not self.profiles or not hasattr(self.profiles, "get_profile_shape"):
            return None
        try:
            return self.profiles.get_profile_shape(name)
        except Exception:
            return None

    def _get_profile_dxf_path(self, name: str) -> Optional[str]:
        shape = self._get_profile_shape(name)
        return shape.get("dxf_path") if shape and shape.get("dxf_path") else None

    def _show_profile_preview_ephemeral(self, name: str, auto_hide_ms: int = 1200):
        if not name or SectionPreviewPopup is None: return
        shape = self._get_profile_shape(name)
        if not shape or not shape.get("dxf_path"):
            self.close_preview(); return
        popup = self._ensure_popup()
        if not popup: return
        try:
            popup.load_path(shape["dxf_path"])
        except Exception:
            self.close_preview(); return
        try:
            bw = float(shape.get("bbox_w") or 0.0)
            bh = float(shape.get("bbox_h") or 0.0)
        except Exception:
            bw = bh = 0.0
        if bw > 0.0 and bh > 0.0:
            screen = QGuiApplication.primaryScreen()
            scr = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
            max_w = int(scr.width() * 0.25)
            max_h = int(scr.height() * 0.25)
            desired_w = max(160, int(min(bw, max_w)))
            desired_h = max(120, int(min(bh, max_h)))
            try:
                popup.resize(desired_w, desired_h)
            except Exception:
                pass
        try:
            popup.show_top_left_of(self.window(), auto_hide_ms=auto_hide_ms)
        except TypeError:
            popup.show_top_left_of(self.window())
            QTimer.singleShot(auto_hide_ms, self.close_preview)

    @staticmethod
    def _sort_list_widget(lw: QListWidget):
        texts = [lw.item(i).text() for i in range(lw.count())]
        texts.sort()
        lw.clear()
        for t in texts:
            lw.addItem(QListWidgetItem(t))


class QcadSubPage(QFrame):
    def __init__(self, appwin, profiles_store):
        super().__init__()
        self.appwin = appwin
        self.profiles = profiles_store
        self._monitor_timer: Optional[QTimer] = None
        self._last_mtime: float = 0.0
        self._build()

    def _build(self):
        self.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius: 6px; }")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        row = 0

        grid.addWidget(QLabel("Eseguibile QCAD:"), row, 0)
        self.edit_qcad = QLineEdit()
        sugg = next((p for p in suggest_qcad_paths() if Path(p).exists()), "")
        if sugg:
            self.edit_qcad.setText(sugg)
        grid.addWidget(self.edit_qcad, row, 1)
        btn_qcad = QToolButton()
        btn_qcad.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
        btn_qcad.clicked.connect(self._browse_qcad)
        grid.addWidget(btn_qcad, row, 2)
        row += 1

        grid.addWidget(QLabel("Cartella di lavoro:"), row, 0)
        self.edit_ws = QLineEdit()
        grid.addWidget(self.edit_ws, row, 1)
        btn_ws = QToolButton()
        btn_ws.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
        btn_ws.clicked.connect(self._browse_ws)
        grid.addWidget(btn_ws, row, 2)
        row += 1

        grid.addWidget(QLabel("Profilo target:"), row, 0)
        self.cmb_profile = QComboBox()
        self._reload_profiles_combo()
        grid.addWidget(self.cmb_profile, row, 1, 1, 2)
        row += 1

        root.addLayout(grid)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_open_blank = QPushButton("Apri QCAD (vuoto)")
        self.btn_open_blank.clicked.connect(self._open_qcad_blank)
        btn_row.addWidget(self.btn_open_blank)
        self.btn_open_prof = QPushButton("Apri QCAD su DXF profilo")
        self.btn_open_prof.clicked.connect(self._open_qcad_on_profile)
        btn_row.addWidget(self.btn_open_prof)
        self.btn_import = QPushButton("Importa export.blitz.json")
        self.btn_import.clicked.connect(self._import_export_now)
        btn_row.addWidget(self.btn_import)
        self.btn_monitor = QPushButton("Avvia monitor")
        self.btn_monitor.setCheckable(True)
        self.btn_monitor.clicked.connect(self._toggle_monitor)
        btn_row.addWidget(self.btn_monitor)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        assoc_row = QHBoxLayout()
        assoc_row.setSpacing(8)
        self.btn_assoc = QPushButton("Associa DXF al profilo…")
        self.btn_assoc.clicked.connect(self._associate_dxf_to_profile)
        assoc_row.addWidget(self.btn_assoc)
        self.btn_new_from_dxf = QPushButton("Crea profilo da DXF…")
        self.btn_new_from_dxf.clicked.connect(self._create_profile_from_dxf)
        assoc_row.addWidget(self.btn_new_from_dxf)
        assoc_row.addStretch(1)
        root.addLayout(assoc_row)

        self.lbl_info = QLabel("Ultima quota: —")
        self.lbl_info.setStyleSheet("color:#0a0a0a;")
        root.addWidget(self.lbl_info, 0)

        root.addStretch(1)

    def _reload_profiles_combo(self):
        self.cmb_profile.clear()
        if self.profiles:
            try:
                rows = self.profiles.list_profiles()
                for r in rows:
                    n = str(r.get("name") or "")
                    if n:
                        self.cmb_profile.addItem(n)
            except Exception:
                pass
        if self.cmb_profile.count() == 0:
            self.cmb_profile.addItem("Nessuno")

    def _browse_qcad(self):
        path, _ = QFileDialog.getOpenFileName(self, "Seleziona QCAD", "", "Eseguibili (*)")
        if path:
            self.edit_qcad.setText(path)

    def _browse_ws(self):
        path = QFileDialog.getExistingDirectory(self, "Seleziona cartella di lavoro", "")
        if path:
            self.edit_ws.setText(path)

    def _qcad_exe(self) -> str:
        return (self.edit_qcad.text() or "").strip()

    def _workspace(self) -> str:
        return (self.edit_ws.text() or "").strip()

    def _open_qcad_blank(self):
        exe = self._qcad_exe()
        ws = self._workspace() or None
        if not exe:
            return
        try:
            launch_qcad(exe, None, ws)
        except Exception:
            pass

    def _open_qcad_on_profile(self):
        prof = (self.cmb_profile.currentText() or "").strip()
        dxf_path = None
        if self.profiles and prof and hasattr(self.profiles, "get_profile_shape"):
            try:
                shape = self.profiles.get_profile_shape(prof)
                dxf_path = shape.get("dxf_path") if shape and shape.get("dxf_path") else None
            except Exception:
                dxf_path = None
        if not dxf_path:
            dxf_path, _ = QFileDialog.getOpenFileName(self, "Scegli DXF", "", "DXF Files (*.dxf);;Tutti i file (*)")
        self.open_qcad_with_path(dxf_path)

    def open_qcad_with_path(self, dxf_path: Optional[str]):
        exe = self._qcad_exe()
        ws = self._workspace() or None
        if not exe:
            return
        try:
            launch_qcad(exe, dxf_path, ws)
        except Exception:
            pass

    def _toggle_monitor(self, on: bool):
        if on:
            if not self._monitor_timer:
                self._monitor_timer = QTimer(self)
                self._monitor_timer.setInterval(1500)
                self._monitor_timer.timeout.connect(self._check_export)
            self._monitor_timer.start()
            self.btn_monitor.setText("Ferma monitor")
        else:
            if self._monitor_timer:
                self._monitor_timer.stop()
            self.btn_monitor.setText("Avvia monitor")

    def _export_path(self) -> Optional[str]:
        ws = self._workspace()
        if not ws:
            return None
        p = find_export_file(ws)
        return str(p) if p else None

    def _check_export(self):
        p = self._export_path()
        if not p:
            return
        try:
            st = Path(p).stat()
            if st.st_mtime > self._last_mtime:
                self._last_mtime = st.st_mtime
                self._import_export_now()
        except Exception:
            pass

    def _import_export_now(self):
        p = self._export_path()
        if not p:
            p, _ = QFileDialog.getOpenFileName(self, "Scegli export.blitz.json", self._workspace() or "", "JSON (*.json);;Tutti i file (*)")
            if not p:
                return
        try:
            last_dim, data = parse_export_json(p)
        except Exception:
            last_dim, data = None, {}
        if last_dim is not None:
            self.lbl_info.setText(f"Ultima quota: {last_dim:.3f} mm")
            prof = (self.cmb_profile.currentText() or "").strip()
            if self.profiles and prof:
                try:
                    self.profiles.upsert_profile(prof, float(last_dim))
                except Exception:
                    pass
        else:
            self.lbl_info.setText("Ultima quota: — (export non valido)")

    def _associate_dxf_to_profile(self):
        prof = (self.cmb_profile.currentText() or "").strip()
        if not prof or prof == "Nessuno":
            return
        dxf, _ = QFileDialog.getOpenFileName(self, "Seleziona DXF da associare", "", "DXF Files (*.dxf);;Tutti i file (*)")
        if not dxf:
            return
        bbox = compute_dxf_bbox(dxf)
        self._store_profile_dxf(prof, dxf, bbox)

    def _create_profile_from_dxf(self):
        dxf, _ = QFileDialog.getOpenFileName(self, "Seleziona DXF", "", "DXF Files (*.dxf);;Tutti i file (*)")
        if not dxf:
            return
        name, ok = QFileDialog.getSaveFileName(self, "Nome profilo (salva per confermare)", "", "Profilo (*)")
        if not ok or not name:
            return
        name = Path(name).stem
        if self.profiles and hasattr(self.profiles, "upsert_profile"):
            try:
                self.profiles.upsert_profile(name, 0.0)
            except Exception:
                pass
        bbox = compute_dxf_bbox(dxf)
        self._store_profile_dxf(name, dxf, bbox)
        self._reload_profiles_combo()

    def _store_profile_dxf(self, name: str, dxf_path: str, bbox: Optional[Tuple[float, float]]):
        if not self.profiles or not name or not dxf_path:
            return
        shape: Dict[str, Any] = {"dxf_path": dxf_path}
        if bbox:
            shape["bbox_w"], shape["bbox_h"] = float(bbox[0]), float(bbox[1])
        for m, args in [
            ("set_profile_shape", (name, shape)),
            ("set_profile_dxf", (name, dxf_path)),
            ("upsert_profile_shape", (name, shape)),
            ("upsert_profile_meta", (name, shape)),
        ]:
            if hasattr(self.profiles, m):
                try:
                    getattr(self.profiles, m)(*args)
                    return
                except Exception:
                    pass
        if hasattr(self.profiles, "upsert_profile"):
            try:
                getattr(self.profiles, "upsert_profile")(name, float(0.0), shape)
            except Exception:
                pass


class BackupSubPage(QFrame):
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self._build()

    def _build(self):
        self.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius: 6px; }")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        root.addWidget(QLabel("Backup"), 0)
        row = QHBoxLayout()
        btn_make = QPushButton("Crea backup")
        btn_restore = QPushButton("Ripristina backup")
        row.addWidget(btn_make)
        row.addWidget(btn_restore)
        row.addStretch(1)
        root.addLayout(row)
        note = QLabel("Configura qui la strategia di backup (destinazione, schedulazione, retention...).")
        note.setStyleSheet("color:#7f8c8d;")
        root.addWidget(note, 0)
        root.addStretch(1)


class ConfigSubPage(QFrame):
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self._mgr = RS485Manager() if RS485Manager else None
        self._build()
        self._load_from_settings()

    def _build(self):
        self.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius: 6px; }")
        root = QGridLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setHorizontalSpacing(8)
        root.setVerticalSpacing(6)
        row = 0
        root.addWidget(QLabel("Configurazione I/O RS485 (Waveshare)"), row, 0, 1, 4, alignment=Qt.AlignLeft)
        row += 1

        root.addWidget(QLabel("Porta seriale:"), row, 0)
        self.cmb_port = QComboBox()
        self._refresh_ports()
        root.addWidget(self.cmb_port, row, 1)
        btn_ref = QToolButton(); btn_ref.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        btn_ref.clicked.connect(self._refresh_ports)
        root.addWidget(btn_ref, row, 2)
        row += 1

        root.addWidget(QLabel("Baud:"), row, 0)
        self.cmb_baud = QComboBox(); self.cmb_baud.addItems([str(b) for b in (9600, 19200, 38400, 57600, 115200)])
        self.cmb_baud.setCurrentText("115200")
        root.addWidget(self.cmb_baud, row, 1)
        row += 1

        root.addWidget(QLabel("Parità:"), row, 0)
        self.cmb_par = QComboBox(); self.cmb_par.addItems(["N", "E", "O"])
        root.addWidget(self.cmb_par, row, 1)
        row += 1

        root.addWidget(QLabel("Stop bits:"), row, 0)
        self.cmb_stop = QComboBox(); self.cmb_stop.addItems(["1", "2"])
        root.addWidget(self.cmb_stop, row, 1)
        row += 1

        root.addWidget(QLabel("Modulo A addr:"), row, 0)
        self.spin_addr_a = QSpinBox(); self.spin_addr_a.setRange(1, 247); self.spin_addr_a.setValue(1)
        root.addWidget(self.spin_addr_a, row, 1)
        row += 1

        root.addWidget(QLabel("Modulo B addr:"), row, 0)
        self.spin_addr_b = QSpinBox(); self.spin_addr_b.setRange(1, 247); self.spin_addr_b.setValue(2)
        root.addWidget(self.spin_addr_b, row, 1)
        row += 1

        self.chk_autoconnect = QCheckBox("Autoconnetti all'avvio Utility"); self.chk_autoconnect.setChecked(True)
        root.addWidget(self.chk_autoconnect, row, 0, 1, 2)
        row += 1

        btns = QHBoxLayout()
        self.btn_connect = QPushButton("Connetti"); self.btn_connect.clicked.connect(self._connect_now); btns.addWidget(self.btn_connect)
        self.btn_disconnect = QPushButton("Disconnetti"); self.btn_disconnect.clicked.connect(self._disconnect_now); btns.addWidget(self.btn_disconnect)
        self.btn_save = QPushButton("Salva impostazioni"); self.btn_save.clicked.connect(self._save_to_settings); btns.addWidget(self.btn_save)
        btns.addStretch(1)
        root.addLayout(btns, row, 0, 1, 4)
        row += 1

        self.lbl_state: List[QLabel] = []
        test = QGridLayout()
        test.setHorizontalSpacing(8); test.setVerticalSpacing(6)
        test.addWidget(QLabel("Test ingressi digitali (A: IN1..IN8, B: IN1..IN8)"), 0, 0, 1, 4)
        for i in range(8):
            lab = QLabel(f"A IN{i+1}: —"); lab.setStyleSheet("color:#7f8c8d;")
            self.lbl_state.append(lab)
            test.addWidget(lab, 1 + i // 4, (i % 4))
        for i in range(8):
            lab = QLabel(f"B IN{i+1}: —"); lab.setStyleSheet("color:#7f8c8d;")
            self.lbl_state.append(lab)
            test.addWidget(lab, 3 + i // 4, (i % 4))
        row += 1
        root.addLayout(test, row, 0, 1, 4)
        row += 1

        read_row = QHBoxLayout()
        self.btn_read = QPushButton("Leggi ingressi"); self.btn_read.clicked.connect(self._read_inputs_once)
        read_row.addWidget(self.btn_read)
        read_row.addStretch(1)
        root.addLayout(read_row, row, 0, 1, 4)

    def _refresh_ports(self):
        self.cmb_port.clear()
        for p in list_serial_ports_safe():
            self.cmb_port.addItem(p)

    def _cfg(self) -> Dict[str, Any]:
        return {
            "port": (self.cmb_port.currentText() or "").strip(),
            "baud": int(self.cmb_baud.currentText()),
            "par": (self.cmb_par.currentText() or "N").strip()[:1],
            "stop": int(self.cmb_stop.currentText()),
            "addr_a": int(self.spin_addr_a.value()),
            "addr_b": int(self.spin_addr_b.value()),
            "autoconn": bool(self.chk_autoconnect.isChecked()),
        }

    def _save_to_settings(self):
        cfg = dict(read_settings())
        io = dict(cfg.get("io", {}))
        io["rs485"] = {
            "port": self._cfg()["port"],
            "baud": self._cfg()["baud"],
            "parity": self._cfg()["par"],
            "stopbits": self._cfg()["stop"],
        }
        io["modA"] = {"addr": self._cfg()["addr_a"]}
        io["modB"] = {"addr": self._cfg()["addr_b"]}
        io["autoconnect"] = self._cfg()["autoconn"]
        cfg["io"] = io
        write_settings(cfg)

    def _load_from_settings(self):
        cfg = read_settings()
        io = cfg.get("io", {}) or {}
        rs = io.get("rs485", {}) or {}
        if rs.get("port"):
            ports = [self.cmb_port.itemText(i) for i in range(self.cmb_port.count())]
            if rs["port"] not in ports:
                self.cmb_port.addItem(rs["port"])
            self.cmb_port.setCurrentText(rs["port"])
        if rs.get("baud"):
            self.cmb_baud.setCurrentText(str(rs.get("baud")))
        if rs.get("parity"):
            self.cmb_par.setCurrentText(str(rs.get("parity")).upper()[:1])
        if rs.get("stopbits"):
            self.cmb_stop.setCurrentText(str(int(rs.get("stopbits"))))
        self.spin_addr_a.setValue(int((io.get("modA", {}) or {}).get("addr", 1)))
        self.spin_addr_b.setValue(int((io.get("modB", {}) or {}).get("addr", 2)))
        self.chk_autoconnect.setChecked(bool(io.get("autoconnect", True)))

        if self.chk_autoconnect.isChecked():
            self._connect_now(silent=True)

    def _connect_now(self, silent: bool = False):
        if not self._mgr:
            if not silent:
                try: self._toast("RS485 non disponibile (manca libreria).", "warn")
                except Exception: pass
            return
        ok = self._mgr.connect(
            port=self._cfg()["port"],
            baudrate=self._cfg()["baud"],
            parity=self._cfg()["par"],
            stopbits=self._cfg()["stop"],
            timeout=0.5,
        )
        if not silent:
            try: self._toast("Connesso RS485" if ok else "Connessione RS485 fallita", "ok" if ok else "warn")
            except Exception: pass

    def _disconnect_now(self):
        if not self._mgr:
            return
        self._mgr.disconnect()
        try: self._toast("RS485 disconnesso", "ok")
        except Exception: pass

    def _read_inputs_once(self):
        if not self._mgr or not self._mgr.is_connected():
            try: self._toast("Non connesso RS485", "warn")
            except Exception: pass
            return
        addr_a = self._cfg()["addr_a"]
        addr_b = self._cfg()["addr_b"]
        a = self._mgr.read_discrete_inputs(unit=addr_a, address=0, count=8)
        b = self._mgr.read_discrete_inputs(unit=addr_b, address=0, count=8)
        for i in range(8):
            self._set_state_label(i, "A", i + 1, bool(a[i] if i < len(a) else False))
        for i in range(8):
            self._set_state_label(8 + i, "B", i + 1, bool(b[i] if i < len(b) else False))

    def _set_state_label(self, idx: int, mod: str, ch: int, val: bool):
        if 0 <= idx < len(self.lbl_state):
            lab = self.lbl_state[idx]
            lab.setText(f"{mod} IN{ch}: {'ON' if val else 'OFF'}")
            lab.setStyleSheet(f"color:{('#2ecc71' if val else '#7f8c8d')};")

    def _toast(self, msg: str, level: str = "info"):
        if hasattr(self.appwin, "toast"):
            try: self.appwin.toast.show(msg, level, 2200)
            except Exception: pass


class ThemesSubPage(QFrame):
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self._build()

    def _build(self):
        self.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius: 6px; }")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        root.addWidget(QLabel("Temi"), 0)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Seleziona preset:"))
        self.cmb_theme = QComboBox()
        self._reload_theme_list()
        row1.addWidget(self.cmb_theme, 1)
        btn_apply = QPushButton("Applica")
        btn_apply.clicked.connect(self._apply_selected)
        row1.addWidget(btn_apply)
        btn_set = QPushButton("Imposta come predefinito")
        btn_set.clicked.connect(self._set_default_selected)
        row1.addWidget(btn_set)
        row1.addStretch(1)
        root.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Rapidi:"))
        btn_light = QPushButton("Chiaro")
        btn_dark = QPushButton("Scuro")
        btn_light.clicked.connect(lambda: self._quick_apply("Light"))
        btn_dark.clicked.connect(lambda: self._quick_apply("Dark"))
        row2.addWidget(btn_light); row2.addWidget(btn_dark); row2.addStretch(1)
        root.addLayout(row2)

        tip = QLabel("Seleziona un tema e premi Applica per vedere l'effetto. 'Imposta come predefinito' lo manterrà ai prossimi avvii.")
        tip.setStyleSheet("color:#7f8c8d;")
        root.addWidget(tip, 0)
        root.addStretch(1)

    def _reload_theme_list(self):
        combos = read_themes()
        names = sorted(combos.keys())
        cur = get_current_theme_name() if callable(get_current_theme_name) else None
        self.cmb_theme.clear()
        for n in names:
            self.cmb_theme.addItem(n)
        if cur and cur in names:
            self.cmb_theme.setCurrentText(cur)

    def _apply_theme_by_name(self, name: str, persist: bool = False):
        combos = read_themes()
        combo = combos.get(name) or {}
        pal = combo.get("palette") or {}
        try:
            set_palette_from_dict(pal)
            from PySide6.QtWidgets import QApplication
            apply_global_stylesheet(QApplication.instance())
        except Exception:
            pass
        if persist:
            try:
                set_current_theme_name(name)
            except Exception:
                pass

    def _apply_selected(self):
        name = (self.cmb_theme.currentText() or "").strip()
        if not name:
            return
        self._apply_theme_by_name(name, persist=False)

    def _set_default_selected(self):
        name = (self.cmb_theme.currentText() or "").strip()
        if not name:
            return
        self._apply_theme_by_name(name, persist=True)

    def _quick_apply(self, name: str):
        combos = read_themes()
        if name not in combos:
            save_theme_combo(name, palette={}, icons={})
        self._apply_theme_by_name(name, persist=True)


class LabelsSubPage(QFrame):
    """
    Etichette:
    - Editor template
    - Associazioni (profilo / elemento)
    - Lista placeholder cliccabile
    - Anteprima (render con Pillow) anche senza stampante
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

    # compat con on_show
    def reload_templates_list(self): self._reload_templates()
    def reload_assoc_ui(self): self._reload_assoc_list()

    def _build(self):
        self.setStyleSheet("QFrame { border:1px solid #3b4b5a; border-radius:6px; }")

        root = QVBoxLayout(self); root.setContentsMargins(8,8,8,8); root.setSpacing(8)
        title = QLabel("Etichette — Template, Associazioni, Anteprima")
        title.setStyleSheet("font-weight:800; font-size:16px;")
        root.addWidget(title, 0)

        splitter = QSplitter(Qt.Horizontal)

        # Colonna sinistra: lista template + placeholder
        left_col = QFrame(); llay = QVBoxLayout(left_col); llay.setContentsMargins(6,6,6,6); llay.setSpacing(6)
        self.lst_templates = QListWidget()
        self.lst_templates.setMinimumWidth(220)
        self.lst_templates.currentItemChanged.connect(self._on_select_template)
        llay.addWidget(QLabel("Template"))
        llay.addWidget(self.lst_templates, 1)

        llay.addWidget(QLabel("Placeholder (doppio click per inserire)"))
        self.lst_tokens = QListWidget()
        self.lst_tokens.setSelectionMode(QAbstractItemView.SingleSelection)
        for t in ["{profile}", "{element}", "{length_mm:.2f}", "{ang_sx:.1f}", "{ang_dx:.1f}",
                  "{seq_id}", "{timestamp}", "{qty_remaining}",
                  "{commessa}", "{element_id}", "{infisso_id}", "{misura_elem}"]:
            self.lst_tokens.addItem(QListWidgetItem(t))
        self.lst_tokens.itemDoubleClicked.connect(self._insert_token_into_line)
        llay.addWidget(self.lst_tokens, 0)

        splitter.addWidget(left_col)

        # Colonna centrale: editor template + associazioni
        center = QFrame(); ceb = QGridLayout(center); ceb.setContentsMargins(6,6,6,6); ceb.setHorizontalSpacing(8); ceb.setVerticalSpacing(6)
        r = 0
        ceb.addWidget(QLabel("Nome:"), r,0); self.ed_name = QLineEdit(); ceb.addWidget(self.ed_name, r,1,1,3); r+=1
        ceb.addWidget(QLabel("Carta:"), r,0); self.cmb_paper = QComboBox(); self.cmb_paper.addItems(["DK-11201","DK-11202","DK-11209","DK-22205"]); ceb.addWidget(self.cmb_paper, r,1)
        ceb.addWidget(QLabel("Rotazione:"), r,2); self.cmb_rotate = QComboBox(); self.cmb_rotate.addItems(["0","90","180","270"]); ceb.addWidget(self.cmb_rotate, r,3); r+=1
        ceb.addWidget(QLabel("Font size:"), r,0); self.ed_font = QLineEdit("32"); ceb.addWidget(self.ed_font, r,1)
        self.chk_cut = QCheckBox("Taglio automatico"); self.chk_cut.setChecked(True); ceb.addWidget(self.chk_cut, r,2,1,2); r+=1

        ceb.addWidget(QLabel("Linee (una per riga):"), r,0,1,4); r+=1
        self.tbl_lines = QTableWidget(0,1); self.tbl_lines.setHorizontalHeaderLabels(["Contenuto"]); self.tbl_lines.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        ceb.addWidget(self.tbl_lines, r,0,1,4); r+=1

        ceb.addWidget(QLabel("QR data (opzionale):"), r,0,1,4); r+=1
        self.ed_qr_data = QLineEdit(); ceb.addWidget(self.ed_qr_data, r,0,1,3)
        self.spin_qr_mod = QSpinBox(); self.spin_qr_mod.setRange(2,10); self.spin_qr_mod.setValue(4); ceb.addWidget(QLabel("Modulo:"), r,3); r+=1
        ceb.addWidget(self.spin_qr_mod, r,3); r+=1

        row_btn = QHBoxLayout()
        btn_add_line = QPushButton("+ Linea"); btn_add_line.clicked.connect(self._add_line)
        btn_del_line = QPushButton("- Linea"); btn_del_line.clicked.connect(self._del_line)
        row_btn.addWidget(btn_add_line); row_btn.addWidget(btn_del_line); row_btn.addStretch(1)
        ceb.addLayout(row_btn, r,0,1,4); r+=1

        actions_row = QHBoxLayout()
        btn_new = QPushButton("Nuovo"); btn_new.clicked.connect(self._new_template)
        btn_dup = QPushButton("Duplica"); btn_dup.clicked.connect(self._duplicate_template)
        btn_save = QPushButton("Salva"); btn_save.clicked.connect(self._save_template)
        btn_delete = QPushButton("Elimina"); btn_delete.clicked.connect(self._delete_template)
        btn_test = QPushButton("Render anteprima"); btn_test.clicked.connect(self._render_preview_current)
        actions_row.addWidget(btn_new); actions_row.addWidget(btn_dup); actions_row.addWidget(btn_save); actions_row.addWidget(btn_delete); actions_row.addWidget(btn_test); actions_row.addStretch(1)
        ceb.addLayout(actions_row, r,0,1,4); r+=1

        assoc_box = QFrame(); assoc_box.setStyleSheet("QFrame { border:1px solid #3b4b5a; border-radius:6px; }")
        al = QGridLayout(assoc_box); al.setContentsMargins(6,6,6,6); al.setHorizontalSpacing(8); al.setVerticalSpacing(6)
        rr = 0
        al.addWidget(QLabel("Associazioni"), rr,0,1,4); rr+=1
        al.addWidget(QLabel("Profilo:"), rr,0); self.cmb_profile = QComboBox(); al.addWidget(self.cmb_profile, rr,1)
        al.addWidget(QLabel("Template:"), rr,2); self.cmb_template_assoc = QComboBox(); al.addWidget(self.cmb_template_assoc, rr,3); rr+=1
        btn_set_prof = QPushButton("Imposta su profilo"); btn_set_prof.clicked.connect(self._set_assoc_prof)
        btn_rem_prof = QPushButton("Rimuovi da profilo"); btn_rem_prof.clicked.connect(self._remove_assoc_prof)
        al.addWidget(btn_set_prof, rr,0,1,2); al.addWidget(btn_rem_prof, rr,2,1,2); rr+=1
        al.addWidget(QLabel("Elemento (nome):"), rr,0); self.ed_element = QLineEdit(); self.ed_element.setPlaceholderText("es. Montante, Traverso..."); al.addWidget(self.ed_element, rr,1)
        al.addWidget(QLabel("Template:"), rr,2); self.cmb_template_elem = QComboBox(); al.addWidget(self.cmb_template_elem, rr,3); rr+=1
        btn_set_el = QPushButton("Imposta su elemento"); btn_set_el.clicked.connect(self._set_assoc_elem)
        btn_rem_el = QPushButton("Rimuovi da elemento"); btn_rem_el.clicked.connect(self._remove_assoc_elem)
        al.addWidget(btn_set_el, rr,0,1,2); al.addWidget(btn_rem_el, rr,2,1,2); rr+=1
        self.lbl_assoc_prof = QLabel("Profili: —"); self.lbl_assoc_prof.setStyleSheet("color:#7f8c8d;")
        self.lbl_assoc_elem = QLabel("Elementi: —"); self.lbl_assoc_elem.setStyleSheet("color:#7f8c8d;")
        al.addWidget(QLabel("Associazioni profilo:"), rr,0,1,1); al.addWidget(self.lbl_assoc_prof, rr,1,1,3); rr+=1
        al.addWidget(QLabel("Associazioni elemento:"), rr,0,1,1); al.addWidget(self.lbl_assoc_elem, rr,1,1,3); rr+=1
        ceb.addWidget(assoc_box, r,0,1,4); r+=1

        splitter.addWidget(center)

        # Colonna destra: anteprima e dati esempio
        right_col = QFrame(); rlay = QVBoxLayout(right_col); rlay.setContentsMargins(6,6,6,6); rlay.setSpacing(6)
        rlay.addWidget(QLabel("Anteprima etichetta"))
        self.lbl_preview = QLabel("— anteprima —")
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        self.lbl_preview.setStyleSheet("QLabel { background:#fafafa; border:1px dashed #8e9; }")
        self.lbl_preview.setMinimumSize(320, 220)
        rlay.addWidget(self.lbl_preview, 1)

        rlay.addWidget(QLabel("Dati di esempio (JSON per placeholder)"))
        self.txt_sample = QTextEdit()
        self.txt_sample.setPlaceholderText('{"profile":"P","element":"Montante","length_mm":1234.5,"ang_sx":45,"ang_dx":0,"commessa":"JOB-1","element_id":"E1","infisso_id":"W1","misura_elem":1234.5}')
        self.txt_sample.setPlainText('{"profile":"DEMO","element":"Montante","length_mm":1234.50,"ang_sx":45,"ang_dx":0,"seq_id":999,"commessa":"JOB-2025-001","element_id":"E-0001","infisso_id":"W-42","misura_elem":1234.50}')
        rlay.addWidget(self.txt_sample, 0)

        btn_render = QPushButton("Render anteprima"); btn_render.clicked.connect(self._render_preview_current)
        rlay.addWidget(btn_render, 0)

        splitter.addWidget(right_col)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 1)

        root.addWidget(splitter, 1)

        hint = QLabel("Suggerimento: doppio click su un placeholder per inserirlo nella riga selezionata.")
        hint.setStyleSheet("color:#7f8c8d;")
        root.addWidget(hint, 0)

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
        qr = t.get("qrcode") or {}
        self.ed_qr_data.setText(str(qr.get("data","")) if isinstance(qr, dict) else "")
        try: self.spin_qr_mod.setValue(int(qr.get("module_size", 4)))
        except Exception: self.spin_qr_mod.setValue(4)
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

    def _insert_token_into_line(self, it: QListWidgetItem):
        token = it.text()
        r = self.tbl_lines.currentRow()
        if r < 0:
            r = self.tbl_lines.rowCount()
            self.tbl_lines.insertRow(r)
            self.tbl_lines.setItem(r, 0, QTableWidgetItem(""))
        cell = self.tbl_lines.item(r, 0)
        if not cell:
            cell = QTableWidgetItem("")
            self.tbl_lines.setItem(r, 0, cell)
        txt = cell.text() or ""
        cell.setText(txt + (("" if txt.endswith(" ") or txt == "" else " ") + token))

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

    # Anteprima — render a video
    def _render_preview_current(self):
        name = (self.ed_name.text() or "").strip()
        if not name:
            QMessageBox.information(self,"Anteprima","Seleziona/salva un template."); return
        tmpl = get_template(name)
        if not tmpl:
            QMessageBox.information(self,"Anteprima","Template non trovato."); return

        sample = {"profile":"DEMO","element":"Montante","length_mm":1234.50,"ang_sx":45,"ang_dx":0,
                  "seq_id":999,"timestamp":time.strftime("%H:%M:%S"),
                  "commessa":"JOB-2025-001","element_id":"E-0001","infisso_id":"W-42","misura_elem":1234.50}
        try:
            parsed = json.loads(self.txt_sample.toPlainText() or "{}")
            if isinstance(parsed, dict):
                sample.update(parsed)
        except Exception:
            pass

        lines = []
        for raw in tmpl.get("lines", []):
            try:
                lines.append(str(raw).format(**sample))
            except Exception:
                lines.append(str(raw))
        qr = tmpl.get("qrcode") or {}
        qr_data = None
        if isinstance(qr, dict) and qr.get("data"):
            try:
                qr_data = str(qr["data"]).format(**sample)
            except Exception:
                qr_data = str(qr["data"])

        try:
            from PIL import Image, ImageDraw, ImageFont
            import qrcode
            paper_map = {"DK-11201": (29.0, 90.0), "DK-11202": (62.0, 100.0), "DK-11209": (62.0, 29.0), "DK-22205": (62.0, 100.0)}
            w_mm, h_mm = paper_map.get(tmpl.get("paper","DK-11201"), (29.0, 90.0))
            W = int(round((w_mm/25.4)*300)); H = int(round((h_mm/25.4)*300))
            img = Image.new("1", (W, H), 1); draw = ImageDraw.Draw(img)
            fs = int(tmpl.get("font_size", 32))
            with contextlib.suppress(Exception): font = ImageFont.truetype("arial.ttf", fs)
            if 'font' not in locals(): font = ImageFont.load_default()
            x_offset = 8; y = 8
            if qr_data:
                qr = qrcode.QRCode(border=0, box_size= max(2, int((tmpl.get("qrcode") or {}).get("module_size", 4))))
                qr.add_data(qr_data); qr.make(fit=True)
                qrim = qr.make_image(fill_color="black", back_color="white").convert("1")
                qrw, qrh = qrim.size; img.paste(qrim, (8, 8)); x_offset = 8 + qrw + 8
            for line in lines:
                draw.text((x_offset, y), str(line), fill=0, font=font)
                y += int(fs * 1.2)
            if int(tmpl.get("rotate", 0)) in (90,180,270):
                with contextlib.suppress(Exception): img = img.rotate(int(tmpl.get("rotate",0)), expand=True)

            # Mostra in QLabel
            qimg = QImage(img.tobytes(), img.size[0], img.size[1], img.size[0], QImage.Format_Mono)
            self.lbl_preview.setPixmap(QPixmap.fromImage(qimg).scaled(self.lbl_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception as e:
            QMessageBox.information(self,"Anteprima", f"Errore render: {e}")
