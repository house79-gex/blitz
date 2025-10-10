from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QTabWidget, QLineEdit, QColorDialog, QMessageBox, QGridLayout, QCheckBox, QFileDialog,
    QListWidget, QListWidgetItem, QGroupBox, QFormLayout
)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtWidgets import QApplication
from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel
from ui_qt.theme import THEME, set_palette_from_dict, apply_global_stylesheet

# theme_store tollerante
try:
    from ui_qt.utils.theme_store import save_theme_combo, read_themes
except Exception:
    def save_theme_combo(name, palette, icons):  # fallback
        pass
    def read_themes():
        return {}

# app settings (flag tastatore)
try:
    from ui_qt.utils.app_settings import get_bool as settings_get_bool, set_bool as settings_set_bool
except Exception:
    def settings_get_bool(key: str, default: bool = False) -> bool: return default
    def settings_set_bool(key: str, value: bool): pass

# servizi profili / dxf / tastatore
try:
    from ui_qt.services.profiles_store import ProfilesStore
except Exception:
    ProfilesStore = None

try:
    from ui_qt.services.dxf_importer import analyze_dxf
except Exception:
    analyze_dxf = None

try:
    from ui_qt.services.probe_service import ProbeService
except Exception:
    ProbeService = None

# CAD misura (opzionale)
try:
    from ui_qt.dialogs.dxf_measure_dialog import DxfMeasureDialog
except Exception:
    DxfMeasureDialog = None

# Popup anteprima sezione (opzionale)
try:
    from ui_qt.widgets.section_preview_popup import SectionPreviewPopup
except Exception:
    SectionPreviewPopup = None


class UtilityPage(QWidget):
    """
    Utility: configurazioni, backup, profili/DXF, tema + StatusPanel.
    - Import DXF con analisi bbox (ezdxf) e salvataggio profilo (DB condiviso).
    - Archivio profili con modifica spessore/eliminazione.
    - CAD di misura (viewer DXF con snap e modalità perpendicolare) opzionale.
    - Tastatore profili (simulato) opzionale, abilitabile da Configurazione.
    - Anteprima sezione come popup quando scorri i profili.
    """
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine
        self.color_vars = {}
        self.icon_vars = {}
        self._diag_timer: QTimer | None = None

        # servizi
        self.profiles = ProfilesStore() if ProfilesStore else None
        self.probe = ProbeService(self.machine) if ProbeService else None

        # cache UI handle
        self.lst_profiles: QListWidget | None = None
        self.edit_prof_name: QLineEdit | None = None
        self.edit_prof_th: QLineEdit | None = None

        self._section_popup = None  # popup anteprima per Utility

        self._build()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(8, 8, 8, 8); root.setSpacing(6)
        root.addWidget(Header(self.appwin, "UTILITY"))

        body = QHBoxLayout(); body.setSpacing(8); root.addLayout(body, 1)

        # Tabs a sinistra
        tabs = QTabWidget(); body.addWidget(tabs, 3)
        tabs.addTab(self._build_conf_tab(), "Configurazione")
        tabs.addTab(self._build_backup_tab(), "Backup")
        tabs.addTab(self._build_dxf_tab(), "Profili / DXF")
        tabs.addTab(self._build_theme_tab(), "Tema")

        # Stato a destra
        side = QFrame(); body.addWidget(side, 1)
        side_l = QVBoxLayout(side); side_l.setContentsMargins(4, 4, 4, 4)
        self.status = StatusPanel(machine_state=self.machine, title="STATO", parent=side)
        side_l.addWidget(self.status)

    # --- Configurazione ---
    def _build_conf_tab(self):
        from PySide6.QtWidgets import QVBoxLayout as VB, QHBoxLayout as HB
        pg = QFrame()
        lay = VB(pg); lay.setContentsMargins(8, 8, 8, 8); lay.setSpacing(8)

        # Tastatore profili (sperimentale, disabilitato di default)
        row_probe = HB()
        chk_probe = QCheckBox("Abilita tastatore profili (sperimentale)")
        chk_probe.setChecked(settings_get_bool("probe_profiles_enabled", False))
        def on_probe_toggle(checked: bool):
            settings_set_bool("probe_profiles_enabled", bool(checked))
            QMessageBox.information(self, "Tastatore profili", ("Abilitato" if checked else "Disabilitato") + ".")
        chk_probe.toggled.connect(on_probe_toggle)
        row_probe.addWidget(chk_probe)
        row_probe.addStretch(1)
        lay.addLayout(row_probe)

        lay.addStretch(1)
        return pg

    # --- Backup ---
    def _build_backup_tab(self):
        pg = QFrame()
        lay = QVBoxLayout(pg); lay.setContentsMargins(8, 8, 8, 8); lay.setSpacing(8)
        lay.addWidget(QLabel("Backup e Ripristino"), 0, alignment=Qt.AlignLeft)
        btns = QHBoxLayout()
        btn_backup = QPushButton("Esegui backup"); btn_restore = QPushButton("Ripristina da file…")
        btn_backup.clicked.connect(self._do_backup); btn_restore.clicked.connect(self._do_restore)
        btns.addWidget(btn_backup); btns.addWidget(btn_restore); btns.addStretch(1)
        lay.addLayout(btns)
        lay.addStretch(1)
        return pg

    # --- Profili / DXF ---
    def _build_dxf_tab(self):
        pg = QFrame()
        lay = QVBoxLayout(pg); lay.setContentsMargins(8, 8, 8, 8); lay.setSpacing(10)

        # --- Import DXF ---
        grp_import = QGroupBox("Importa profilo da DXF")
        f = QFormLayout(grp_import); f.setLabelAlignment(Qt.AlignRight)
        edit_path = QLineEdit(); edit_path.setPlaceholderText("Seleziona un file DXF…")
        btn_browse = QPushButton("Sfoglia…")
        def pick_file():
            fn, _ = QFileDialog.getOpenFileName(self, "Seleziona DXF", "", "Disegni DXF (*.dxf);;Tutti i file (*)")
            if fn:
                edit_path.setText(fn)
        btn_browse.clicked.connect(pick_file)

        row1 = QHBoxLayout(); row1.addWidget(edit_path, 1); row1.addWidget(btn_browse)
        f.addRow("File DXF:", row1)

        edit_name = QLineEdit(); edit_name.setPlaceholderText("Nome profilo (es. Alluminio 50)")
        f.addRow("Nome profilo:", edit_name)

        edit_th = QLineEdit(); edit_th.setPlaceholderText("Spessore (mm) — opzionale")
        f.addRow("Spessore (mm):", edit_th)

        lbl_meta = QLabel("—"); lbl_meta.setWordWrap(True)
        f.addRow("Analisi:", lbl_meta)

        btn_analyze = QPushButton("Analizza DXF")
        btn_save = QPushButton("Salva in archivio")
        btn_save.setEnabled(False)

        def analyze_now():
            p = (edit_path.text() or "").strip()
            if not p:
                QMessageBox.warning(self, "DXF", "Seleziona un file DXF.")
                return
            if analyze_dxf is None:
                QMessageBox.warning(self, "DXF", "Analizzatore DXF non disponibile. Installa 'ezdxf'.")
                return
            try:
                info = analyze_dxf(p)
                if not (edit_name.text() or "").strip():
                    edit_name.setText(info.get("name_suggestion", ""))
                lbl_meta.setText(f"Entità: {info['entities']} | BBox: {info['bbox_w']:.1f} x {info['bbox_h']:.1f} mm")
                btn_save.setEnabled(True)
                btn_save._last_info = info  # type: ignore
            except Exception as e:
                QMessageBox.warning(self, "DXF", f"Errore analisi: {e!s}")

        def save_now():
            name = (edit_name.text() or "").strip()
            if not name:
                QMessageBox.warning(self, "Profili", "Inserisci un nome profilo.")
                return
            try:
                th = float((edit_th.text() or "0").replace(",", "."))
            except Exception:
                th = 0.0
            if not self.profiles:
                QMessageBox.warning(self, "Profili", "Archivio profili non disponibile.")
                return
            info = getattr(btn_save, "_last_info", None)
            try:
                self.profiles.upsert_profile(name, th)
                if info:
                    self.profiles.upsert_profile_shape(
                        name=name,
                        dxf_path=info.get("path"),
                        bbox_w=info.get("bbox_w"),
                        bbox_h=info.get("bbox_h"),
                        meta=info
                    )
                QMessageBox.information(self, "Profili", f"Profilo '{name}' salvato.")
                self._refresh_profiles_list()
            except Exception as e:
                QMessageBox.warning(self, "Profili", f"Errore salvataggio: {e!s}")

        btn_analyze.clicked.connect(analyze_now)
        btn_save.clicked.connect(save_now)

        row_btns = QHBoxLayout(); row_btns.addStretch(1); row_btns.addWidget(btn_analyze); row_btns.addWidget(btn_save)

        # CAD misura (opzionale)
        btn_open_cad = QPushButton("Apri CAD di misura…")
        def open_cad():
            if DxfMeasureDialog is None:
                QMessageBox.information(self, "DXF", "CAD di misura non disponibile in questa build.")
                return
            path = (getattr(btn_save, "_last_info", {}) or {}).get("path", (edit_path.text() or "").strip())
            if not path:
                QMessageBox.information(self, "DXF", "Seleziona e analizza un DXF prima.")
                return
            try:
                dlg = DxfMeasureDialog(self, path=path)
                if dlg.exec():
                    th = dlg.result_thickness_mm()
                    if th > 0:
                        edit_th.setText(f"{th:.2f}")
                        QMessageBox.information(self, "Misura", f"Spessore misurato: {th:.2f} mm")
            except Exception as e:
                QMessageBox.warning(self, "DXF", f"Errore apertura CAD: {e!s}")
        btn_open_cad.clicked.connect(open_cad)
        row_btns.addWidget(btn_open_cad)

        lay.addWidget(grp_import)
        lay.addLayout(row_btns)

        # --- Archivio profili ---
        grp_arch = QGroupBox("Archivio profili")
        arch_l = QHBoxLayout(grp_arch)
        self.lst_profiles = QListWidget()
        self.lst_profiles.setMinimumSize(QSize(240, 260))
        arch_l.addWidget(self.lst_profiles, 1)

        edit_box = QFrame(); eb_l = QFormLayout(edit_box)
        self.edit_prof_name = QLineEdit(); self.edit_prof_name.setReadOnly(True)
        self.edit_prof_th = QLineEdit()
        eb_l.addRow("Nome:", self.edit_prof_name)
        eb_l.addRow("Spessore (mm):", self.edit_prof_th)

        btns_box = QHBoxLayout()
        btn_update = QPushButton("Aggiorna spessore")
        btn_delete = QPushButton("Elimina profilo")
        btns_box.addWidget(btn_delete); btns_box.addStretch(1); btns_box.addWidget(btn_update)
        eb_l.addRow(btns_box)
        arch_l.addWidget(edit_box, 0)

        def on_select():
            if not self.profiles:
                return
            it = self.lst_profiles.currentItem()
            if not it:
                return
            name = it.text()
            rec = self.profiles.get_profile(name)
            if not rec:
                return
            self.edit_prof_name.setText(rec["name"])
            self.edit_prof_th.setText(str(rec["thickness"]))
            # popup anteprima sezione DXF
            try:
                if SectionPreviewPopup:
                    shape = self.profiles.get_profile_shape(name)
                    if shape and shape.get("dxf_path"):
                        if self._section_popup is None:
                            self._section_popup = SectionPreviewPopup(self.appwin, "Sezione profilo")
                        self._section_popup.load_path(shape["dxf_path"])
                        self._section_popup.show_top_right_of(self.window())
                    else:
                        if self._section_popup:
                            self._section_popup.close(); self._section_popup = None
            except Exception:
                pass

        self.lst_profiles.currentItemChanged.connect(lambda cur, prev: on_select())

        def do_update():
            if not self.profiles:
                return
            name = (self.edit_prof_name.text() or "").strip()
            if not name:
                return
            try:
                th = float((self.edit_prof_th.text() or "0").replace(",", "."))
            except Exception:
                QMessageBox.warning(self, "Profili", "Spessore non valido.")
                return
            try:
                self.profiles.upsert_profile(name, th)
                QMessageBox.information(self, "Profili", "Spessore aggiornato.")
                self._refresh_profiles_list(select=name)
            except Exception as e:
                QMessageBox.warning(self, "Profili", f"Errore aggiornamento: {e!s}")

        def do_delete():
            if not self.profiles:
                return
            it = self.lst_profiles.currentItem()
            if not it:
                return
            name = it.text()
            if QMessageBox.question(self, "Conferma", f"Eliminare il profilo '{name}'?") != QMessageBox.Yes:
                return
            try:
                if self.profiles.delete_profile(name):
                    self._refresh_profiles_list()
                    self.edit_prof_name.setText("")
                    self.edit_prof_th.setText("")
                    if self._section_popup:
                        self._section_popup.close(); self._section_popup = None
                    QMessageBox.information(self, "Profili", "Profilo eliminato.")
            except Exception as e:
                QMessageBox.warning(self, "Profili", f"Errore eliminazione: {e!s}")

        btn_update.clicked.connect(do_update)
        btn_delete.clicked.connect(do_delete)

        lay.addWidget(grp_arch)

        # --- Tastatore profili (test, visibile solo se abilitato e servizio presente) ---
        grp_probe = QGroupBox("Tastatore profili (test)")
        enable_probe = settings_get_bool("probe_profiles_enabled", False) and (self.probe is not None)
        grp_probe.setVisible(bool(enable_probe))
        pr_l = QHBoxLayout(grp_probe)
        btn_probe = QPushButton("Misura spessore (test)")
        lbl_probe = QLabel("—")
        pr_l.addWidget(btn_probe); pr_l.addWidget(lbl_probe, 1, alignment=Qt.AlignLeft)

        def do_probe():
            if not self.probe:
                QMessageBox.information(self, "Tastatore", "Servizio tastatore non disponibile.")
                return
            if self.probe.is_busy():
                QMessageBox.information(self, "Tastatore", "Misura in corso…")
                return
            btn_probe.setEnabled(False); lbl_probe.setText("Misuro…")
            def done(ok: bool, value: float | None, msg: str):
                btn_probe.setEnabled(True)
                if ok and value is not None:
                    lbl_probe.setText(f"Spessore: {value:.1f} mm")
                    cur = self.lst_profiles.currentItem() if self.lst_profiles else None
                    if cur and self.edit_prof_name:
                        self.edit_prof_th.setText(f"{value:.1f}")
                else:
                    lbl_probe.setText(f"Errore: {msg}")
            self.probe.measure_thickness_async(done_cb=done)

        btn_probe.clicked.connect(do_probe)
        lay.addWidget(grp_probe)

        # popolamento iniziale
        self._refresh_profiles_list()

        return pg

    def _refresh_profiles_list(self, select: str | None = None):
        if not self.lst_profiles or not self.profiles:
            return
        self.lst_profiles.clear()
        try:
            rows = self.profiles.list_profiles()
            for r in rows:
                self.lst_profiles.addItem(QListWidgetItem(str(r["name"])))
            if select:
                items = self.lst_profiles.findItems(select, Qt.MatchExactly)
                if items:
                    self.lst_profiles.setCurrentItem(items[0])
        except Exception:
            pass

    # --- Tema ---
    def _build_theme_tab(self):
        pg = QFrame()
        lay = QVBoxLayout(pg)
        pal_box = QFrame()
        pal_l = QVBoxLayout(pal_box)
        pal_l.addWidget(QLabel("Palette Tema"))
        grid = QGridLayout()
        fields = [
            ("APP_BG", "Sfondo app"), ("SURFACE_BG", "Superficie"), ("PANEL_BG", "Pannello"),
            ("CARD_BG", "Card"), ("TILE_BG", "Tile Home"),
            ("ACCENT", "Accento 1"), ("ACCENT_2", "Accento 2"),
            ("OK", "OK"), ("WARN", "Warn"), ("ERR", "Errore"),
            ("TEXT", "Testo"), ("TEXT_MUTED", "Testo attenuato"),
            ("OUTLINE", "Bordo1"), ("OUTLINE_SOFT", "Bordo2"),
            ("HEADER_BG", "Header BG"), ("HEADER_FG", "Header FG"),
        ]
        for i, (key, lbl) in enumerate(fields):
            grid.addWidget(QLabel(lbl), i, 0)
            default_value = getattr(THEME, "SURFACE_BG")
            value = str(getattr(THEME, key, default_value))
            edit = QLineEdit(value); edit.setFixedWidth(120)
            btn = QPushButton("Scegli…"); btn.setFixedWidth(90)
            def picker(k=key, e=edit):
                col = QColorDialog.getColor()
                if col.isValid():
                    e.setText(col.name())
            btn.clicked.connect(picker)
            grid.addWidget(edit, i, 1); grid.addWidget(btn, i, 2)
            self.color_vars[key] = edit

        actions = QHBoxLayout()
        btn_apply = QPushButton("Applica ora"); btn_apply.clicked.connect(self._apply_theme_now)
        btn_save = QPushButton("Salva combinazione"); btn_save.clicked.connect(self._save_theme_combo)
        actions.addWidget(btn_apply); actions.addWidget(btn_save); actions.addStretch(1)
        pal_l.addLayout(grid); pal_l.addLayout(actions)
        lay.addWidget(pal_box); lay.addStretch(1)
        return pg

    def _apply_theme_now(self):
        pal = {k: e.text().strip() for k, e in self.color_vars.items()}
        set_palette_from_dict(pal)
        apply_global_stylesheet(QApplication.instance())
        QMessageBox.information(self, "Tema", "Tema applicato (live).")

    def _save_theme_combo(self):
        pal = {k: e.text().strip() for k, e in self.color_vars.items()}
        save_theme_combo("Custom", pal, {})
        QMessageBox.information(self, "Tema", "Combinazione salvata come 'Custom' in data/themes.json.")

    # --- Polling diagnostica/StatusPanel ---
    def on_show(self):
        if self._diag_timer is None:
            self._diag_timer = QTimer(self)
            self._diag_timer.timeout.connect(self._tick_diag)
            self._diag_timer.start(300)

    def hideEvent(self, ev):
        if self._diag_timer is not None:
            try:
                self._diag_timer.stop()
            except Exception:
                pass
            self._diag_timer = None
        # chiudi eventuale popup anteprima quando lasci Utility
        try:
            if self._section_popup:
                self._section_popup.close()
                self._section_popup = None
        except Exception:
            pass
        super().hideEvent(ev)

    def _tick_diag(self):
        try:
            self.status.refresh()
        except Exception:
            pass

    def _do_backup(self):
        QMessageBox.information(self, "Backup", "Funzione backup: da collegare al backend.")

    def _do_restore(self):
        QMessageBox.information(self, "Ripristino", "Funzione ripristino: da collegare al backend.")
