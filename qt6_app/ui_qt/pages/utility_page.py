from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame, QPushButton, QTabWidget,
    QGridLayout, QLineEdit, QColorDialog, QComboBox, QSpinBox, QMessageBox, QCheckBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication
from ui_qt.theme import THEME, set_palette_from_dict, apply_global_stylesheet
from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel
from ui_qt.utils.settings import read_themes, save_theme_combo

class UtilityPage(QWidget):
    """
    Porting fedele della pagina Utility:
    - Configurazione contapezzi (API MachineState identiche)
    - Diagnostica I/O con polling
    - Backup/DXF (placeholder)
    - Tema (editor palette e salvataggio combinazioni)
    """
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine
        self.color_vars = {}
        self.icon_vars = {}
        self._diag_timer = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        header = Header(self.appwin, "UTILITY")
        root.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(8)
        root.addLayout(body, 1)

        # Tabs a sinistra
        tabs = QTabWidget()
        body.addWidget(tabs, 3)

        self._conf_tab = self._build_conf_tab()
        self._backup_tab = self._build_backup_tab()
        self._dxf_tab = self._build_dxf_tab()
        self._theme_tab = self._build_theme_tab()

        tabs.addTab(self._conf_tab, "Configurazione")
        tabs.addTab(self._backup_tab, "Backup")
        tabs.addTab(self._dxf_tab, "DXF Import")
        tabs.addTab(self._theme_tab, "Tema")

        # Stato a destra
        side = QFrame()
        body.addWidget(side, 1)
        side_l = QVBoxLayout(side)
        side_l.setContentsMargins(4, 4, 4, 4)
        self.status = StatusPanel(machine_state=self.machine, title="STATO", parent=side)
        side_l.addWidget(self.status)

    def _build_conf_tab(self):
        pg = QFrame()
        lay = QVBoxLayout(pg)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)

        # Stato attivo su contatto chiuso/aperto
        form.addWidget(QLabel("Contatto attivo su:"), 0, 0)
        self.cb_active_state = QComboBox()
        self.cb_active_state.addItems(["chiuso", "aperto"])
        cur_state = "chiuso" if getattr(self.machine, "count_active_on_closed", True) else "aperto"
        self.cb_active_state.setCurrentText(cur_state)
        form.addWidget(self.cb_active_state, 0, 1)

        # Inversione sensori
        self.chk_invert_left = QCheckBox("Inverti sensore sinistro")
        self.chk_invert_right = QCheckBox("Inverti sensore destro")
        self.chk_invert_left.setChecked(bool(getattr(self.machine, "invert_left_switch", False)))
        self.chk_invert_right.setChecked(bool(getattr(self.machine, "invert_right_switch", False)))
        form.addWidget(self.chk_invert_left, 1, 0, 1, 2)
        form.addWidget(self.chk_invert_right, 2, 0, 1, 2)

        # Debounce e raggruppamento impulsi
        form.addWidget(QLabel("Debounce impulso (ms):"), 3, 0)
        self.spin_debounce = QSpinBox()
        self.spin_debounce.setRange(0, 2000)
        self.spin_debounce.setValue(int(getattr(self.machine, "cut_pulse_debounce_ms", 50)))
        form.addWidget(self.spin_debounce, 3, 1)

        form.addWidget(QLabel("Raggruppamento impulsi (ms):"), 4, 0)
        self.spin_group = QSpinBox()
        self.spin_group.setRange(0, 5000)
        self.spin_group.setValue(int(getattr(self.machine, "cut_pulse_group_ms", 300)))
        form.addWidget(self.spin_group, 4, 1)

        lay.addLayout(form)

        # Azioni
        actions = QHBoxLayout()
        btn_save = QPushButton("Salva parametri")
        btn_save.clicked.connect(self._save_counter_settings)
        actions.addWidget(btn_save)
        actions.addStretch(1)
        lay.addLayout(actions)

        # Diagnostica I/O
        diag_box = QFrame()
        diag_l = QGridLayout(diag_box)
        diag_l.setHorizontalSpacing(10)
        diag_l.setVerticalSpacing(6)
        diag_l.addWidget(QLabel("Diagnostica I/O"), 0, 0, 1, 2, alignment=Qt.AlignLeft)

        diag_l.addWidget(QLabel("Sensore sinistro:"), 1, 0)
        self.lbl_diag_left = QLabel("-")
        diag_l.addWidget(self.lbl_diag_left, 1, 1)

        diag_l.addWidget(QLabel("Sensore destro:"), 2, 0)
        self.lbl_diag_right = QLabel("-")
        diag_l.addWidget(self.lbl_diag_right, 2, 1)

        lay.addWidget(diag_box)
        lay.addStretch(1)
        return pg

    def _build_backup_tab(self):
        pg = QFrame()
        lay = QVBoxLayout(pg)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        lay.addWidget(QLabel("Backup e Ripristino"), 0, alignment=Qt.AlignLeft)

        btns = QHBoxLayout()
        btn_backup = QPushButton("Esegui backup")
        btn_restore = QPushButton("Ripristina da file…")
        btn_backup.clicked.connect(self._do_backup)
        btn_restore.clicked.connect(self._do_restore)
        btns.addWidget(btn_backup)
        btns.addWidget(btn_restore)
        btns.addStretch(1)
        lay.addLayout(btns)

        lay.addStretch(1)
        return pg

    def _build_dxf_tab(self):
        pg = QFrame()
        lay = QVBoxLayout(pg)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        lay.addWidget(QLabel("Importazione DXF"), 0, alignment=Qt.AlignLeft)

        btn = QPushButton("Importa DXF…")
        btn.clicked.connect(self._import_dxf)
        lay.addWidget(btn, 0, alignment=Qt.AlignLeft)

        lay.addStretch(1)
        return pg

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
            edit = QLineEdit(value)
            edit.setFixedWidth(120)
            btn = QPushButton("Scegli…")
            btn.setFixedWidth(90)

            def picker(k=key, e=edit):
                col = QColorDialog.getColor()
                if col.isValid():
                    e.setText(col.name())

            btn.clicked.connect(picker)
            grid.addWidget(edit, i, 1)
            grid.addWidget(btn, i, 2)
            self.color_vars[key] = edit;

        pal_l.addLayout(grid)

        actions = QHBoxLayout()
        btn_apply = QPushButton("Applica ora")
        btn_apply.clicked.connect(self._apply_theme_now)
        btn_save = QPushButton("Salva combinazione")
        btn_save.clicked.connect(self._save_theme_combo)
        btn_load = QPushButton("Carica combinazione…")
        btn_load.clicked.connect(self._load_theme_combo)
        actions.addWidget(btn_apply)
        actions.addWidget(btn_save)
        actions.addWidget(btn_load)
        actions.addStretch(1)
        pal_l.addLayout(actions)

        lay.addWidget(pal_box)
        lay.addStretch(1)
        return pg

    def _apply_theme_now(self):
        pal = {k: e.text().strip() for k, e in self.color_vars.items()}
        set_palette_from_dict(pal)
        apply_global_stylesheet(QApplication.instance())
        QMessageBox.information(self, "Tema", "Tema applicato (live).")

    def _save_theme_combo(self):
        pal = {k: e.text().strip() for k, e in self.color_vars.items()}
        icons = {k: e.text().strip() for k, e in self.icon_vars.items()} if self.icon_vars else {}
        save_theme_combo("Custom", pal, icons)
        QMessageBox.information(self, "Tema", "Combinazione salvata come 'Custom' in data/themes.json.")

    def _load_theme_combo(self):
        data = read_themes()
        names = list(data.keys())
        if not names:
            QMessageBox.information(self, "Tema", "Nessuna combinazione salvata.")
            return
        name = names[0]
        combo = data.get(name, {})
        pal = combo.get("palette", {})
        for k, e in self.color_vars.items():
            if k in pal:
                e.setText(str(pal[k]))
        QMessageBox.information(self, "Tema", f"Combinazione '{name}' caricata (non applicata).")

    def _save_counter_settings(self):
        try:
            setattr(self.machine, "count_active_on_closed", self.cb_active_state.currentText().strip().lower() == "chiuso")
            setattr(self.machine, "invert_left_switch", bool(self.chk_invert_left.isChecked()))
            setattr(self.machine, "invert_right_switch", bool(self.chk_invert_right.isChecked()))
            setattr(self.machine, "cut_pulse_debounce_ms", int(self.spin_debounce.value()))
            setattr(self.machine, "cut_pulse_group_ms", int(self.spin_group.value()))
            QMessageBox.information(self, "Configurazione", "Parametri salvati.")
        except Exception as e:
            QMessageBox.warning(self, "Configurazione", f"Errore salvataggio: {e!s}")

    def _do_backup(self):
        QMessageBox.information(self, "Backup", "Funzione backup: da collegare al backend come in Tk.")

    def _do_restore(self):
        QMessageBox.information(self, "Ripristino", "Funzione ripristino: da collegare al backend come in Tk.")

    def _import_dxf(self):
        QMessageBox.information(self, "DXF Import", "Import DXF: da collegare al backend come in Tk.")

    def _tick_diag(self):
        # Aggiornamento diagnostica I/O: tenta nomi comuni; fallback '-'
        m = self.machine
        left = None
        right = None
        for name in ("left_switch_active", "left_sensor_active", "conta_left_active"):
            if hasattr(m, name):
                left = getattr(m, name, None)
                break
        for name in ("right_switch_active", "right_sensor_active", "conta_right_active"):
            if hasattr(m, name):
                right = getattr(m, name, None)
                break
        self.lbl_diag_left.setText("ATTIVO" if left else "—" if left is not None else "-")
        self.lbl_diag_right.setText("ATTIVO" if right else "—" if right is not None else "-")
        self.status.refresh()

    def on_show(self):
        self.status.refresh()
        if self._diag_timer is None:
            self._diag_timer = QTimer(self)
            self._diag_timer.timeout.connect(self._tick_diag)
            self._diag_timer.start(200)

    def hideEvent(self, ev):
        if self._diag_timer:
            self._diag_timer.stop()
            self._diag_timer = None
        super().hideEvent(ev)