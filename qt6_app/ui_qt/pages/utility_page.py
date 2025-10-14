from __future__ import annotations
from typing import Optional, Dict, Any, List

from PySide6.QtCore import Qt, QSize, QRect, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QListWidget, QListWidgetItem,
    QLineEdit, QPushButton, QGridLayout, QSizePolicy, QAbstractItemView, QStackedWidget,
    QFileDialog, QToolButton, QStyle, QButtonGroup
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
    - Profili è un sottomenu dedicato alla gestione (nome/spessore), preview DXF popup auto-hide, e "Apri in CAD".
    - CAD 2D integra il viewer avanzato (misure, rotazione, snap, ecc.).
    - Backup/Configurazione/Temi sono pagine placeholder pronte per essere estese.
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
        self.page_cad = CadSubPage(self.appwin)
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
        # passa alla pagina CAD e carica il file
        self.stack.setCurrentIndex(1)
        # sincronizza lista menu
        items = self.lst_menu.findItems("CAD 2D", Qt.MatchExactly)
        if items:
            self.lst_menu.setCurrentItem(items[0])
        try:
            self.page_cad.load_dxf_path(dxf_path)
        except Exception:
            pass

    # ---------- Lifecycle ----------
    def on_show(self):
        # refresh profili all'apertura Utility
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

        self.lst_profiles: Optional[ListWidget] = None
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

        # Apri in CAD
        self.btn_open_cad = QPushButton("Apri in CAD")
        self.btn_open_cad.setEnabled(False)
        self.btn_open_cad.clicked.connect(self._open_cad_for_current)
        btns.addWidget(self.btn_open_cad)

        rl.addLayout(btns, row, 0, 1, 3)
        row += 1

        # Tip
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
        # abilita "Apri in CAD" solo se presente DXF
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
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.viewer: Optional[DxfViewerWidget] = None
        self._build()

    def _build(self):
        self.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius: 6px; }")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # Toolbar
        bar = QHBoxLayout()
        bar.setSpacing(6)

        btn_open = QToolButton()
        btn_open.setText("Apri DXF")
        btn_open.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        btn_open.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
        btn_open.clicked.connect(self._choose_and_load)
        bar.addWidget(btn_open)

        # Tools group: distanza, perpendicolare, angolo
        grp = QButtonGroup(self)
        btn_dist = QPushButton("Distanza (G)")
        btn_perp = QPushButton("Perp. (P)")
        btn_ang = QPushButton("Angolo (O)")
        for b in (btn_dist, btn_perp, btn_ang):
            b.setCheckable(True)
            bar.addWidget(b)
        grp.addButton(btn_dist, 1)
        grp.addButton(btn_perp, 2)
        grp.addButton(btn_ang, 3)
        btn_dist.setChecked(True)

        # Rotazione vista
        btn_rot_l = QPushButton("↺ (R)")
        btn_rot_r = QPushButton("↻ (E)")
        btn_align = QPushButton("Allinea (A)")
        bar.addWidget(btn_rot_l)
        bar.addWidget(btn_rot_r)
        bar.addWidget(btn_align)
        bar.addStretch(1)
        root.addLayout(bar)

        # Viewer
        if DxfViewerWidget is None:
            root.addWidget(QLabel("Modulo CAD non disponibile in questa build."), 1)
            return

        self.viewer = DxfViewerWidget(self)
        root.addWidget(self.viewer, 1)

        # Wiring tools
        btn_dist.toggled.connect(lambda on: (on and self.viewer and self.viewer.set_tool_distance()))
        btn_perp.toggled.connect(lambda on: (on and self.viewer and self.viewer.set_tool_perpendicular()))
        btn_ang.toggled.connect(lambda on: (on and self.viewer and self.viewer.set_tool_angle()))
        btn_rot_l.clicked.connect(lambda: self.viewer and self.viewer.rotate_view(+5.0))
        btn_rot_r.clicked.connect(lambda: self.viewer and self.viewer.rotate_view(-5.0))
        btn_align.clicked.connect(lambda: self.viewer and self.viewer.align_vertical_to_segment_under_cursor())

    def _choose_and_load(self):
        if DxfViewerWidget is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Apri DXF", "", "DXF Files (*.dxf);;All Files (*)")
        if not path:
            return
        self.load_dxf_path(path)

    def load_dxf_path(self, path: str):
        if self.viewer is None:
            return
        try:
            self.viewer.load_dxf(path)
        except Exception:
            # visualizza errore minimale
            pass


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

        # Placeholder note
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

        # Placeholder opzioni (da collegare al backend config)
        root.addWidget(QLabel("Opzione A:"), row, 0)
        root.addWidget(QLineEdit(), row, 1)
        row += 1

        root.addWidget(QLabel("Opzione B:"), row, 0)
        root.addWidget(QLineEdit(), row, 1)
        row += 1

        root.addWidget(QLabel("Opzione C:"), row, 0)
        root.addWidget(QLineEdit(), row, 1)
        row += 1

        # Pulsanti
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
        # elenco temi placeholder
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
