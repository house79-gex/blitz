from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

from PySide6.QtCore import Qt, QRect, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QListWidget, QListWidgetItem,
    QLineEdit, QPushButton, QGridLayout, QSizePolicy, QAbstractItemView, QStackedWidget,
    QFileDialog, QToolButton, QStyle, QComboBox, QCheckBox, QSpinBox
)

from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel

# Store profili (comune a Utility/Semi-automatico/Tipologie)
try:
    from ui_qt.services.profiles_store import ProfilesStore
except Exception:
    ProfilesStore = None

# Preview sezione
try:
    from ui_qt.widgets.section_preview_popup import SectionPreviewPopup
except Exception:
    SectionPreviewPopup = None

# Dialog profilo modale
try:
    from ui_qt.dialogs.profile_save_dialog import ProfileSaveDialog
except Exception:
    ProfileSaveDialog = None

# Integrazione QCAD (esterno)
try:
    from ui_qt.services.qcad_integration import suggest_qcad_paths, launch_qcad, find_export_file, parse_export_json, compute_dxf_bbox
except Exception:
    suggest_qcad_paths = lambda: []
    def launch_qcad(*args, **kwargs): raise RuntimeError("qcad_integration non disponibile")
    def find_export_file(workspace_dir: str): return None
    def parse_export_json(path: str): return (None, {})
    def compute_dxf_bbox(path: str): return None

# Temi (store + applicazione runtime)
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

# Settings
try:
    from ui_qt.utils.settings import read_settings, write_settings
except Exception:
    def read_settings() -> Dict[str, Any]: return {}
    def write_settings(d: Dict[str, Any]) -> None: pass

# RS485 Manager (opzionale, robusto a dipendenze mancanti)
try:
    from ui_qt.services.rs485_manager import RS485Manager, list_serial_ports_safe
except Exception:
    RS485Manager = None  # type: ignore
    def list_serial_ports_safe() -> List[str]: return ["COM3", "COM4", "/dev/ttyUSB0"]

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

        # Menu sinistro
        menu = QFrame()
        menu.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        menu.setFixedWidth(200)
        menu.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius: 6px; }")
        menu_layout = QVBoxLayout(menu)
        menu_layout.setContentsMargins(8, 8, 8, 8)
        menu_layout.setSpacing(6)
        self.lst_menu = QListWidget()
        self.lst_menu.setSelectionMode(QAbstractItemView.SingleSelection)
        for label in ("Profili", "QCAD", "Backup", "Configurazione", "Temi"):
            self.lst_menu.addItem(QListWidgetItem(label))
        self.lst_menu.setCurrentRow(0)
        menu_layout.addWidget(QLabel("Sottomenu"))
        menu_layout.addWidget(self.lst_menu, 1)

        # Stack centrale
        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.page_profiles = ProfilesSubPage(self.appwin, self.profiles_store)
        self.page_qcad = QcadSubPage(self.appwin, self.profiles_store)
        self.page_backup = BackupSubPage(self.appwin)
        self.page_config = ConfigSubPage(self.appwin)
        self.page_themes = ThemesSubPage(self.appwin)

        self.stack.addWidget(self.page_profiles)  # 0
        self.stack.addWidget(self.page_qcad)      # 1
        self.stack.addWidget(self.page_backup)    # 2
        self.stack.addWidget(self.page_config)    # 3
        self.stack.addWidget(self.page_themes)    # 4

        # Status destro
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
        self.stack.setCurrentIndex(1)  # QCAD
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
        dxf_path = self._get_profile_dxf_path(name)
        self._show_profile_preview_ephemeral(name)
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
        it = self.lst_profiles.takeItem(row)
        del it
        if self.lst_profiles.count() > 0:
            self.lst_profiles.setCurrentRow(min(row, self.lst_profiles.count() - 1))
        else:
            self.edit_prof_name.clear()
            self.edit_prof_th.clear()
        self.close_preview()

    def _open_cad_for_current(self):
        name = self._get_selected_name()
        if not name:
            return
        dxf_path = self._get_profile_dxf_path(name)
        if dxf_path:
            self.openInCadRequested.emit(dxf_path)

    def close_preview(self):
        try:
            if self._section_popup:
                self._section_popup.close()
                self._section_popup = None
        except Exception:
            self._section_popup = None

    def _ensure_popup(self) -> Optional[SectionPreviewPopup]:
        if SectionPreviewPopup is None:
            return None
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
        if not name or SectionPreviewPopup is None:
            return
        shape = self._get_profile_shape(name)
        if not shape or not shape.get("dxf_path"):
            self.close_preview()
            return
        popup = self._ensure_popup()
        if not popup:
            return
        try:
            popup.load_path(shape["dxf_path"])
        except Exception:
            self.close_preview()
            return
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
    """
    Configurazione tecnica macchina:
      - Porta RS485 (USB<->RS485 Waveshare)
      - Baudrate, Parità, Stopbit
      - Indirizzo modulo A/B (Waveshare 8 IN ciascuno, Modbus RTU)
      - Test lettura IN
    Salva in settings:
      io.rs485.port, io.rs485.baud, io.rs485.parity, io.rs485.stopbits, io.modA.addr, io.modB.addr
    """
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

        # Pulsantiera connessione
        btns = QHBoxLayout()
        self.btn_connect = QPushButton("Connetti")
        self.btn_connect.clicked.connect(self._connect_now)
        btns.addWidget(self.btn_connect)
        self.btn_disconnect = QPushButton("Disconnetti")
        self.btn_disconnect.clicked.connect(self._disconnect_now)
        btns.addWidget(self.btn_disconnect)
        self.btn_save = QPushButton("Salva impostazioni")
        self.btn_save.clicked.connect(self._save_to_settings)
        btns.addWidget(self.btn_save)
        btns.addStretch(1)
        root.addLayout(btns, row, 0, 1, 4)
        row += 1

        # Pannello test IN (16 ingressi)
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
        self.btn_read = QPushButton("Leggi ingressi")
        self.btn_read.clicked.connect(self._read_inputs_once)
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
            # Assicura che la porta sia elencata
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
        # Aggiorna 16 label
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
        row2.addWidget(btn_light)
        row2.addWidget(btn_dark)
        row2.addStretch(1)
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
            # Applica globalmente
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
        # Se non esiste ancora, salva un combo minimo (usa preset interni del theme_store)
        combos = read_themes()
        if name not in combos:
            save_theme_combo(name, palette={}, icons={})
        # Applica e persisti
        self._apply_theme_by_name(name, persist=True)
