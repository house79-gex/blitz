from __future__ import annotations
from typing import Optional, Dict, Any, List

from PySide6.QtCore import Qt, QSize, QRect, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QListWidget, QListWidgetItem,
    QLineEdit, QPushButton, QGridLayout, QSizePolicy
)

from ui_qt.widgets.header import Header

# Store profili (DB condiviso con Utility/Tipologie)
try:
    from ui_qt.services.profiles_store import ProfilesStore
except Exception:
    ProfilesStore = None

# Popup anteprima sezione ridotto e temporaneo
try:
    from ui_qt.widgets.section_preview_popup import SectionPreviewPopup
except Exception:
    SectionPreviewPopup = None


class UtilityPage(QWidget):
    """
    Utility:
    - Gestione profili base: elenco a sinistra, dettagli (nome, spessore) a destra.
    - Preview DXF della sezione (se presente in archivio): popup ridotto, posizionato in alto-sinistra della pagina, temporaneo (auto-hide).
    Note:
    - Questo modulo non gestisce l'assegnazione/rimozione del file DXF ai profili (dipende dall'implementazione del ProfilesStore).
      Se un profilo ha una shape con 'dxf_path', la anteprima mostrerà il DXF in popup.
    """
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin

        # Backend profili
        self.profiles = ProfilesStore() if ProfilesStore else None
        self._profiles_index: Dict[str, float] = {}  # name -> thickness

        # UI refs
        self.lst_profiles: Optional[QListWidget] = None
        self.edit_prof_name: Optional[QLineEdit] = None
        self.edit_prof_th: Optional[QLineEdit] = None

        # Popup anteprima
        self._section_popup: Optional[SectionPreviewPopup] = None

        self._build()
        self._load_profiles()

    # --------------------- Build UI ---------------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(8)

        header = Header(self.appwin, "UTILITY")
        root.addWidget(header, 0)

        content = QHBoxLayout()
        content.setSpacing(12)
        root.addLayout(content, 1)

        # Colonna sinistra: elenco profili
        left = QFrame()
        left.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        left.setFixedWidth(260)
        left.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius: 6px; }")

        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(8)

        left_layout.addWidget(QLabel("Profili"), 0)
        self.lst_profiles = QListWidget()
        self.lst_profiles.setSelectionMode(self.lst_profiles.SingleSelection)
        self.lst_profiles.currentItemChanged.connect(self._on_select_profile)
        left_layout.addWidget(self.lst_profiles, 1)

        content.addWidget(left, 0)

        # Colonna destra: dettagli
        right = QFrame()
        right.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius: 6px; }")

        form = QGridLayout(right)
        form.setContentsMargins(8, 8, 8, 8)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)

        row = 0
        form.addWidget(QLabel("Dettagli profilo"), row, 0, 1, 3, alignment=Qt.AlignLeft)
        row += 1

        form.addWidget(QLabel("Nome:"), row, 0)
        self.edit_prof_name = QLineEdit()
        form.addWidget(self.edit_prof_name, row, 1, 1, 2)
        row += 1

        form.addWidget(QLabel("Spessore (mm):"), row, 0)
        self.edit_prof_th = QLineEdit()
        self.edit_prof_th.setPlaceholderText("0.0")
        form.addWidget(self.edit_prof_th, row, 1, 1, 2)
        row += 1

        # Bottoni
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_new = QPushButton("Nuovo")
        self.btn_new.clicked.connect(self._new_profile)
        btn_row.addWidget(self.btn_new)

        self.btn_save = QPushButton("Salva")
        self.btn_save.clicked.connect(self._save_profile)
        btn_row.addWidget(self.btn_save)

        # Nota: eliminazione profilo richiede API del ProfilesStore; non sempre disponibile
        self.btn_delete = QPushButton("Elimina")
        self.btn_delete.clicked.connect(self._delete_profile)
        btn_row.addWidget(self.btn_delete)

        form.addLayout(btn_row, row, 0, 1, 3)
        row += 1

        # Tip: messaggio contestuale
        self.lbl_tip = QLabel("Suggerimento: seleziona un profilo nell'elenco per vedere la preview DXF (se presente).")
        self.lbl_tip.setStyleSheet("color:#7f8c8d;")
        form.addWidget(self.lbl_tip, row, 0, 1, 3)
        row += 1

        content.addWidget(right, 1)

    # --------------------- Data ---------------------
    def _load_profiles(self):
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

        # Fallback se lista vuota
        if not self._profiles_index:
            self._profiles_index = {"Nessuno": 0.0}

        # Popola la lista
        if self.lst_profiles:
            self.lst_profiles.blockSignals(True)
            self.lst_profiles.clear()
            for name in sorted(self._profiles_index.keys()):
                self.lst_profiles.addItem(QListWidgetItem(name))
            self.lst_profiles.blockSignals(False)

        # Seleziona primo elemento di default
        if self.lst_profiles and self.lst_profiles.count() > 0:
            self.lst_profiles.setCurrentRow(0)

    def _get_selected_name(self) -> Optional[str]:
        if not self.lst_profiles:
            return None
        it = self.lst_profiles.currentItem()
        return it.text() if it else None

    # --------------------- Actions ---------------------
    def _on_select_profile(self, cur: Optional[QListWidgetItem], prev: Optional[QListWidgetItem]):
        if cur is None:
            return
        name = cur.text()
        th = self._profiles_index.get(name, 0.0)
        if self.edit_prof_name:
            self.edit_prof_name.setText(name)
        if self.edit_prof_th:
            self.edit_prof_th.setText(str(th))

        # Mostra anteprima DXF (ridotta, temporanea) se shape presente
        self._show_profile_preview_ephemeral(name)

    def _new_profile(self):
        # Genera un nome univoco
        base = "Nuovo"
        i = 1
        name = base
        while name in self._profiles_index:
            i += 1
            name = f"{base} {i}"
        # Inserisci in memoria e UI
        self._profiles_index[name] = 0.0
        if self.lst_profiles:
            self.lst_profiles.addItem(QListWidgetItem(name))
            self.lst_profiles.setCurrentRow(self.lst_profiles.count() - 1)
        if self.edit_prof_name:
            self.edit_prof_name.setText(name)
        if self.edit_prof_th:
            self.edit_prof_th.setText("0.0")

    def _save_profile(self):
        name = (self.edit_prof_name.text() if self.edit_prof_name else "").strip()
        th_s = (self.edit_prof_th.text() if self.edit_prof_th else "").strip()
        try:
            th = float((th_s or "0").replace(",", "."))
        except Exception:
            th = 0.0
        if not name:
            return

        # Aggiorna store
        if self.profiles and hasattr(self.profiles, "upsert_profile"):
            try:
                self.profiles.upsert_profile(name, th)
            except Exception:
                pass

        # Aggiorna indice e lista
        self._profiles_index[name] = th
        if self.lst_profiles:
            names_in_list = set(self._iter_list_items(self.lst_profiles))
            if name not in names_in_list:
                self.lst_profiles.addItem(QListWidgetItem(name))
            # ordina per nome
            self._sort_list_widget(self.lst_profiles)
            # seleziona la voce
            items = self.lst_profiles.findItems(name, Qt.MatchExactly)
            if items:
                self.lst_profiles.setCurrentItem(items[0])

    def _delete_profile(self):
        name = self._get_selected_name()
        if not name:
            return
        # Prova ad eliminare da store se disponibile
        deleted = False
        if self.profiles and hasattr(self.profiles, "delete_profile"):
            try:
                self.profiles.delete_profile(name)
                deleted = True
            except Exception:
                deleted = False
        # Se nessuna API di delete: rimuovi solo dalla lista in UI
        if name in self._profiles_index:
            del self._profiles_index[name]
        if self.lst_profiles:
            row = self.lst_profiles.currentRow()
            it = self.lst_profiles.takeItem(row)
            del it
            # seleziona altro elemento
            if self.lst_profiles.count() > 0:
                self.lst_profiles.setCurrentRow(min(row, self.lst_profiles.count() - 1))
            else:
                # svuota form
                if self.edit_prof_name:
                    self.edit_prof_name.clear()
                if self.edit_prof_th:
                    self.edit_prof_th.clear()
        # Chiudi eventuale preview
        self._close_preview()

    # --------------------- Preview DXF ---------------------
    def _close_preview(self):
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

    def _show_profile_preview_ephemeral(self, profile_name: str, auto_hide_ms: int = 1200):
        # Mostra popup piccolo e temporaneo in alto-sinistra della pagina
        if not profile_name or SectionPreviewPopup is None:
            return
        shape = self._get_profile_shape(profile_name)
        if not shape or not shape.get("dxf_path"):
            self._close_preview()
            return

        popup = self._ensure_popup()
        if not popup:
            return
        try:
            popup.load_path(shape["dxf_path"])
        except Exception:
            self._close_preview()
            return

        # Dimensiona alla bbox, non oltre ~25% dello schermo e non ingrandire oltre la sezione
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

        # Posiziona in alto-sinistra della pagina e auto-chiudi
        try:
            popup.show_top_left_of(self, auto_hide_ms=auto_hide_ms)
        except TypeError:
            # Fallback per versioni senza auto_hide_ms nel metodo
            popup.show_top_left_of(self)
            QTimer.singleShot(auto_hide_ms, lambda: self._close_preview())

    # --------------------- Helpers ---------------------
    def _iter_list_items(self, lw: QListWidget) -> List[str]:
        return [lw.item(i).text() for i in range(lw.count())]

    def _sort_list_widget(self, lw: QListWidget):
        texts = self._iter_list_items(lw)
        texts.sort()
        lw.clear()
        for t in texts:
            lw.addItem(QListWidgetItem(t))

    # --------------------- Lifecycle ---------------------
    def on_show(self):
        # Ricarica elenco (nel caso l'altro modulo Profili abbia creato o aggiornato voci)
        self._load_profiles()

    def hideEvent(self, ev):
        self._close_preview()
        super().hideEvent(ev)
