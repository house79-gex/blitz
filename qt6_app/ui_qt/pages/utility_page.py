from __future__ import annotations
from typing import Optional, Dict, Any, List

from PySide6.QtCore import Qt, QSize, QRect, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QListWidget, QListWidgetItem,
    QLineEdit, QPushButton, QGridLayout, QSizePolicy, QAbstractItemView, QStackedWidget,
    QFileDialog, QToolButton, QStyle, QButtonGroup, QComboBox
)

from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel

# Store profili (DB condiviso con Utility/Tipologie)
try:
    from ui_qt.services.profiles_store import ProfilesStore
except Exception:
    ProfilesStore = None

# CAD viewer avanzato (QGraphicsView)
try:
    from ui_qt.widgets.dxf_viewer import AdvancedDxfCadView as DxfViewerWidget
except Exception:
    DxfViewerWidget = None

# Popup anteprima sezione ridotto e temporaneo (usato nella pagina Profili)
try:
    from ui_qt.widgets.section_preview_popup import SectionPreviewPopup
except Exception:
    SectionPreviewPopup = None


STATUS_W = 260


class UtilityPage(QWidget):
    """
    Utility (hub con sottomenu)
    - Colonna sinistra: menu (Profili, CAD 2D, Backup, Configurazione, Temi)
    - Centro: contenuto pagine (QStackedWidget)
    - Destra: StatusPanel
    - Profili: gestione (nome/spessore), preview DXF popup auto-hide, “Apri in CAD”
    - CAD 2D: apertura DXF/DWG (converter ODA opzionale), misure e quota allineata, “Imposta spessore = quota”
    """
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = getattr(appwin, "machine", None)

        self.profiles_store = ProfilesStore() if ProfilesStore else None

        self._poll: Optional[QTimer] = None

        self._build()
        self._start_poll()

    # ---------- UI ----------
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

        # Menu (sinistra)
        menu = QFrame()
        menu.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        menu.setFixedWidth(200)
        menu.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius: 6px; }")
        menu_layout = QVBoxLayout(menu)
        menu_layout.setContentsMargins(8, 8, 8, 8)
        menu_layout.setSpacing(6)

        self.lst_menu = QListWidget()
        self.lst_menu.setSelectionMode(QAbstractItemView.SingleSelection)
        for label in ("Profili", "CAD 2D", "Backup", "Configurazione", "Temi"):
            self.lst_menu.addItem(QListWidgetItem(label))
        self.lst_menu.setCurrentRow(0)
        menu_layout.addWidget(QLabel("Sottomenu"))
        menu_layout.addWidget(self.lst_menu, 1)

        # Contenuto (centro)
        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Pagine
        self.page_profiles = ProfilesSubPage(self.appwin, self.profiles_store)
        self.page_cad = CadSubPage(self.appwin, self.profiles_store)
        self.page_backup = BackupSubPage(self.appwin)
        self.page_config = ConfigSubPage(self.appwin)
        self.page_themes = ThemesSubPage(self.appwin)

        self.stack.addWidget(self.page_profiles)  # 0
        self.stack.addWidget(self.page_cad)       # 1
        self.stack.addWidget(self.page_backup)    # 2
        self.stack.addWidget(self.page_config)    # 3
        self.stack.addWidget(self.page_themes)    # 4

        # Status (destra)
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

        # Montaggio
        main.addWidget(menu, 0)
        main.addWidget(self.stack, 1)
        main.addWidget(right, 0)

        # Wiring
        self.lst_menu.currentRowChanged.connect(self.stack.setCurrentIndex)

        # Apertura DXF dal sottomenu Profili
        self.page_profiles.openInCadRequested.connect(self._open_in_cad)

    # ---------- Status poll ----------
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

    # ---------- Actions ----------
    def _open_in_cad(self, dxf_path: str):
        if not dxf_path:
            return
        self.stack.setCurrentIndex(1)
        items = self.lst_menu.findItems("CAD 2D", Qt.MatchExactly)
        if items:
            self.lst_menu.setCurrentItem(items[0])
        try:
            self.page_cad.load_path(dxf_path)
        except Exception:
            pass

    # ---------- Lifecycle ----------
    def on_show(self):
        try:
            self.page_profiles.reload_profiles()
            self.page_cad.reload_profiles_list()
        except Exception:
            pass

    def hideEvent(self, ev):
        try:
            self.page_profiles.close_preview()
        except Exception:
            pass
        super().hideEvent(ev)


# ======================================================================
# Subpage: Profili (sottomenu)
# ======================================================================
class ProfilesSubPage(QFrame):
    openInCadRequested = Signal(str)  # dxf_path

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

        # Lista profili (sx)
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

        # Dettagli (dx)
        right = QFrame()
        rl = QGridLayout(right)
        rl.setContentsMargins(6, 6, 6, 6)
        rl.setHorizontalSpacing(8)
        rl.setVerticalSpacing(6)

        row = 0
        rl.addWidget(QLabel("Dettagli"), row, 0, 1, 3, alignment=Qt.AlignLeft)
        row += 1

        rl.addWidget(QLabel("Nome:"), row, 0)
        self.edit_prof_name = QLineEdit()
        rl.addWidget(self.edit_prof_name, row, 1, 1, 2)
        row += 1

        rl.addWidget(QLabel("Spessore (mm):"), row, 0)
        self.edit_prof_th = QLineEdit()
        self.edit_prof_th.setPlaceholderText("0.0")
        rl.addWidget(self.edit_prof_th, row, 1, 1, 2)
        row += 1

        # Bottoni CRUD + CAD
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

        self.btn_open_cad = QPushButton("Apri in CAD")
        self.btn_open_cad.setEnabled(False)
        self.btn_open_cad.clicked.connect(self._open_cad_for_current)
        btns.addWidget(self.btn_open_cad)

        rl.addLayout(btns, row, 0, 1, 3)
        row += 1

        tip = QLabel("Suggerimento: seleziona un profilo per la preview DXF (popup).")
        tip.setStyleSheet("color:#7f8c8d;")
        rl.addWidget(tip, row, 0, 1, 3)
        row += 1

        root.addWidget(left, 0)
        root.addWidget(right, 1)

    # ------ Data ops ------
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

    # ------ Actions ------
    def _on_select_profile(self, cur: Optional[QListWidgetItem], prev: Optional[QListWidgetItem]):
        if not cur:
            return
        name = cur.text()
        th = self._profiles_index.get(name, 0.0)
        self.edit_prof_name.setText(name)
        self.edit_prof_th.setText(str(th))

        # Preview popup (ridotta e temporanea)
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
        th_s = (self.edit_prof_th.text() or "").strip()
        try:
            th = float((th_s or "0").replace(",", "."))
        except Exception:
            th = 0.0
        if not name:
            return

        if self.profiles and hasattr(self.profiles, "upsert_profile"):
            try:
                self.profiles.upsert_profile(name, th)
            except Exception:
                pass

        # aggiorna indice + lista
        self._profiles_index[name] = th
        names_in_ui = {self.lst_profiles.item(i).text() for i in range(self.lst_profiles.count())}
        if name not in names_in_ui:
            self.lst_profiles.addItem(QListWidgetItem(name))
        # riordina
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

    # ------ Preview DXF (popup) ------
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

    def _show_profile_preview_ephemeral(self, profile_name: str, auto_hide_ms: int = 1200):
        if not profile_name or SectionPreviewPopup is None:
            return
        shape = self._get_profile_shape(profile_name)
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

        # Dimensiona alla bbox (ridotto, max 25% schermo, non ingrandire oltre sezione)
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
            desired_w = int(min(bw, max_w))
            desired_h = int(min(bh, max_h))
            desired_w = max(160, desired_w)
            desired_h = max(120, desired_h)
            try:
                popup.resize(desired_w, desired_h)
            except Exception:
                pass

        try:
            popup.show_top_left_of(self.window(), auto_hide_ms=auto_hide_ms)
        except TypeError:
            popup.show_top_left_of(self.window())
            QTimer.singleShot(auto_hide_ms, self.close_preview)

    # ------ helpers ------
    @staticmethod
    def _sort_list_widget(lw: QListWidget):
        texts = [lw.item(i).text() for i in range(lw.count())]
        texts.sort()
        lw.clear()
        for t in texts:
            lw.addItem(QListWidgetItem(t))


# ======================================================================
# Subpage: CAD 2D (sottomenu)
# ======================================================================
class CadSubPage(QFrame):
    def __init__(self, appwin, profiles_store):
        super().__init__()
        self.appwin = appwin
        self.profiles = profiles_store

        self.viewer: Optional[DxfViewerWidget] = None
        self.cmb_profiles: Optional[QComboBox] = None
        self.edit_oda_path: Optional[QLineEdit] = None

        self._profiles_names: List[str] = []

        self._build()
        self.reload_profiles_list()

    def _build(self):
        self.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius: 6px; }")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # Toolbar riga 1: apertura file e converter
        bar1 = QHBoxLayout()
        bar1.setSpacing(6)

        btn_open = QToolButton()
        btn_open.setText("Apri DXF/DWG")
        btn_open.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        btn_open.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
        btn_open.clicked.connect(self._choose_and_load)
        bar1.addWidget(btn_open)

        bar1.addWidget(QLabel("ODA Converter:"))
        self.edit_oda_path = QLineEdit()
        self.edit_oda_path.setPlaceholderText("Percorso ODA/Teigha File Converter (opz.) o lascia vuoto")
        bar1.addWidget(self.edit_oda_path, 1)
        btn_browse_oda = QToolButton()
        btn_browse_oda.setText("…")
        btn_browse_oda.clicked.connect(self._browse_oda)
        bar1.addWidget(btn_browse_oda)
        btn_apply_oda = QPushButton("Applica")
        btn_apply_oda.clicked.connect(self._apply_oda_path)
        bar1.addWidget(btn_apply_oda)

        bar1.addStretch(1)
        root.addLayout(bar1)

        # Toolbar riga 2: strumenti CAD e integrazione profili
        bar2 = QHBoxLayout()
        bar2.setSpacing(6)

        grp = QButtonGroup(self)
        btn_dist = QPushButton("Distanza (G)")
        btn_perp = QPushButton("Perp. (P)")
        btn_ang = QPushButton("Angolo (O)")
        btn_dim = QPushButton("Quota allineata (D)")
        for b in (btn_dist, btn_perp, btn_ang, btn_dim):
            b.setCheckable(True)
            bar2.addWidget(b)
        grp.addButton(btn_dist, 1)
        grp.addButton(btn_perp, 2)
        grp.addButton(btn_ang, 3)
        grp.addButton(btn_dim, 4)
        btn_dist.setChecked(True)

        btn_rot_l = QPushButton("↺ (R)")
        btn_rot_r = QPushButton("↻ (E)")
        btn_align = QPushButton("Allinea (A)")
        bar2.addWidget(btn_rot_l)
        bar2.addWidget(btn_rot_r)
        bar2.addWidget(btn_align)

        bar2.addSpacing(12)
        bar2.addWidget(QLabel("Profilo:"))
        self.cmb_profiles = QComboBox()
        bar2.addWidget(self.cmb_profiles)

        btn_set_th = QPushButton("Imposta spessore = quota")
        btn_set_th.clicked.connect(self._apply_thickness_from_dimension)
        bar2.addWidget(btn_set_th)

        bar2.addStretch(1)
        root.addLayout(bar2)

        # Viewer
        if DxfViewerWidget is None:
            root.addWidget(QLabel("Modulo CAD non disponibile in questa build."), 1)
            return

        self.viewer = DxfViewerWidget(self)
        self.viewer.dimensionCommitted.connect(self._on_dimension_committed)
        root.addWidget(self.viewer, 1)

        # Wiring tools
        btn_dist.toggled.connect(lambda on: (on and self.viewer and self.viewer.set_tool_distance()))
        btn_perp.toggled.connect(lambda on: (on and self.viewer and self.viewer.set_tool_perpendicular()))
        btn_ang.toggled.connect(lambda on: (on and self.viewer and self.viewer.set_tool_angle()))
        btn_dim.toggled.connect(lambda on: (on and self.viewer and self.viewer.set_tool_dim_aligned()))
        btn_rot_l.clicked.connect(lambda: self.viewer and self.viewer.rotate_view(+5.0))
        btn_rot_r.clicked.connect(lambda: self.viewer and self.viewer.rotate_view(-5.0))
        btn_align.clicked.connect(lambda: self.viewer and self.viewer.align_vertical_to_segment_under_cursor()))

    # ---------- Profili ----------
    def reload_profiles_list(self):
        self._profiles_names = []
        self.cmb_profiles.blockSignals(True)
        self.cmb_profiles.clear()
        if self.profiles:
            try:
                rows = self.profiles.list_profiles()
                for r in rows:
                    name = str(r.get("name"))
                    if name:
                        self._profiles_names.append(name)
                for n in sorted(self._profiles_names):
                    self.cmb_profiles.addItem(n)
            except Exception:
                pass
        if not self._profiles_names:
            self.cmb_profiles.addItem("Nessuno")
        self.cmb_profiles.blockSignals(False)

    # ---------- Apertura file ----------
    def _choose_and_load(self):
        if DxfViewerWidget is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Apri DXF/DWG", "", "CAD Files (*.dxf *.dwg);;Tutti i file (*)")
        if not path:
            return
        self.load_path(path)

    def load_path(self, path: str):
        if self.viewer is None:
            return
        # applica converter se impostato
        if self.edit_oda_path and self.edit_oda_path.text().strip():
            try:
                self.viewer.set_oda_converter_path(self.edit_oda_path.text().strip())
            except Exception:
                pass
        try:
            # Gestione automatica DXF/DWG
            self.viewer.load_file(path)
        except Exception as e:
            # fallback DXF puro
            try:
                if path.lower().endswith(".dxf"):
                    self.viewer.load_dxf(path)
            except Exception:
                pass

    def _browse_oda(self):
        path, _ = QFileDialog.getOpenFileName(self, "Seleziona ODA/Teigha File Converter", "", "Eseguibili (*)")
        if not path:
            return
        if self.edit_oda_path:
            self.edit_oda_path.setText(path)

    def _apply_oda_path(self):
        if self.viewer and self.edit_oda_path:
            self.viewer.set_oda_converter_path(self.edit_oda_path.text().strip() or None)

    # ---------- Quota → spessore ----------
    def _on_dimension_committed(self, value: float):
        # si aggiorna solo internamente; l'utente deve premere il bottone per scrivere sul profilo
        pass

    def _apply_thickness_from_dimension(self):
        if self.viewer is None or self.profiles is None:
            return
        name = (self.cmb_profiles.currentText() or "").strip()
        if not name:
            return
        val = float(self.viewer.last_dimension_value())
        if val <= 0:
            # tenta con ultima misura lineare
            val = float(self.viewer.last_measure_value())
        if val <= 0:
            return
        try:
            self.profiles.upsert_profile(name, float(val))
        except Exception:
            pass
        # feedback leggero (potresti aggiungere un banner in futuro)

# ======================================================================
# Subpage: Backup (sottomenu)
# ======================================================================
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


# ======================================================================
# Subpage: Configurazione (sottomenu)
# ======================================================================
class ConfigSubPage(QFrame):
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self._build()

    def _build(self):
        self.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius: 6px; }")
        root = QGridLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setHorizontalSpacing(8)
        root.setVerticalSpacing(6)

        row = 0
        root.addWidget(QLabel("Configurazione"), row, 0, 1, 2, alignment=Qt.AlignLeft)
        row += 1

        root.addWidget(QLabel("Opzione A:"), row, 0)
        root.addWidget(QLineEdit(), row, 1)
        row += 1

        root.addWidget(QLabel("Opzione B:"), row, 0)
        root.addWidget(QLineEdit(), row, 1)
        row += 1

        root.addWidget(QLabel("Opzione C:"), row, 0)
        root.addWidget(QLineEdit(), row, 1)
        row += 1

        buttons = QHBoxLayout()
        btn_save = QPushButton("Salva configurazione")
        buttons.addWidget(btn_save)
        buttons.addStretch(1)
        root.addLayout(buttons, row, 0, 1, 2)


# ======================================================================
# Subpage: Temi (sottomenu)
# ======================================================================
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

        row = QHBoxLayout()
        row.addWidget(QLabel("Seleziona tema:"))
        btn_light = QPushButton("Chiaro")
        btn_dark = QPushButton("Scuro")
        row.addWidget(btn_light)
        row.addWidget(btn_dark)
        row.addStretch(1)
        root.addLayout(row)

        tip = QLabel("Qui puoi applicare temi globali all'interfaccia.")
        tip.setStyleSheet("color:#7f8c8d;")
        root.addWidget(tip, 0)
        root.addStretch(1)
