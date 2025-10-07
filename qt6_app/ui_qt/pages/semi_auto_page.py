from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QSpinBox, QGridLayout, QDoubleSpinBox, QLineEdit, QComboBox,
    QSizePolicy, QCheckBox, QAbstractSpinBox, QToolButton
)
from PySide6.QtCore import Qt, QTimer, QSize, QLocale
from PySide6.QtGui import QIcon, QKeyEvent
from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel
from ui_qt.widgets.heads_view import HeadsView
import math

# Moduli opzionali per salvataggio profili su SQLite
try:
    from ui_qt.dialogs.profile_edit_dialog import ProfileEditDialog
    from ui_qt.services.profiles_store import ProfilesStore
except Exception:
    ProfileEditDialog = None
    ProfilesStore = None

SX_COLOR = "#2980b9"
DX_COLOR = "#9b59b6"


class SemiAutoPage(QWidget):
    """
    Semi-Automatico: layout a due colonne.
    - Colonna sinistra (expanding):
      • Alto: Contapezzi 190x190 + cornice grafica (HeadsView) massimizzata.
      • Sotto: Profilo/Spessore (con salvataggio su DB profili) | Inclinazione SX/DX (decimi, senza frecce).
      • Basso: Misura esterna (input grande) e, sotto, riga comandi: [BLOCCA/SBLOCCA] | [Quota live (+ dettagli FQ)] | [START].
    - Colonna destra (fissa 180px): StatusPanel (riempie altezza) + box Fuori Quota (offset) + pulsante INTESTATURA.
    Funzioni:
    - Fuori Quota (FQ): mostra Pezzo reale e Pos. testa (quota+offset); in FQ inibisce sempre la lama DX (mobile).
    - Intestatura (singola, pulsante “INTESTATURA”):
        DX -> 45°, posiziona alla minima, blocca freno, inibisce lama SX e abilita lama DX;
        attende incremento conteggio pezzi DX (da pulsantiera reale oppure simulazione via tastiera).
        Al termine: ripristina angolo DX precedente; se FQ attivo re-inibisce lama DX e riposiziona a (quota+offset).
    - TASTI DI SVILUPPO (simulazione):
        F6 (oppure K): simula conteggio pezzo DX (+1) per chiudere l’intestatura.
    - Nota: per evitare crash in sviluppo, questa pagina usa banner interni al posto di finestre modali.
    """
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine

        # Store profili/spessori
        self.profiles_store = ProfilesStore() if ProfilesStore else None
        self._profiles = self._load_profiles_dict()

        # Stato intestatura
        self._intest_in_progress = False
        self._intest_prev_ang_dx = 0.0
        self._intest_dx_count_before = None

        # Cache ultimo calcolo Fuori Quota
        self._last_internal = None
        self._last_target = None

        self._poll = None
        self._build()

    # ---------- Profili ----------
    def _load_profiles_dict(self):
        profs = {}
        try:
            if self.profiles_store:
                rows = self.profiles_store.list_profiles()
                for row in rows:
                    profs[row["name"]] = float(row["thickness"] or 0.0)
                if not profs:
                    # seed iniziale
                    for n, t in (("Nessuno", 0.0), ("Alluminio 50", 50.0), ("PVC 60", 60.0), ("Legno 40", 40.0)):
                        self.profiles_store.upsert_profile(n, t)
                    for row in self.profiles_store.list_profiles():
                        profs[row["name"]] = float(row["thickness"] or 0.0)
            else:
                profs = {"Nessuno": 0.0}
        except Exception:
            profs = {"Nessuno": 0.0}
        return profs

    # ---------- UI ----------
    def _build(self):
        # Abilita cattura tasti (per simulazioni)
        self.setFocusPolicy(Qt.StrongFocus)

        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(8)

        # Colonna sinistra
        left_container = QFrame()
        left_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        left_col = QVBoxLayout(left_container)
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(8)

        header = Header(self.appwin, "SEMI-AUTOMATICO")
        left_col.addWidget(header, 0)

        # Banner dinamico per messaggi (info/warn/errore)
        self.banner = QLabel("")
        self.banner.setVisible(False)
        self.banner.setWordWrap(True)
        self._style_banner_warn()
        left_col.addWidget(self.banner, 0)

        # Riga alta: contapezzi + grafica
        top_left = QHBoxLayout()
        top_left.setSpacing(8)
        top_left.setContentsMargins(0, 0, 0, 0)

        # Contapezzi 190x190
        cnt_container = QFrame()
        cnt_container.setFixedSize(QSize(190, 190))
        cnt_container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        cnt_container.setStyleSheet("QFrame { border:1px solid #3b4b5a; border-radius:6px; }")
        cnt = QGridLayout(cnt_container)
        cnt.setHorizontalSpacing(6)
        cnt.setVerticalSpacing(4)
        title_cnt = QLabel("CONTAPEZZI")
        title_cnt.setStyleSheet("font-weight:600;")
        cnt.addWidget(title_cnt, 0, 0, 1, 2, alignment=Qt.AlignLeft)
        cnt.addWidget(QLabel("Target:"), 1, 0)
        self.spin_target = QSpinBox()
        self.spin_target.setRange(0, 999999)
        self.spin_target.setButtonSymbols(QAbstractSpinBox.NoButtons)  # no frecce
        self.spin_target.setValue(int(getattr(self.machine, "semi_auto_target_pieces", 0)))
        self.spin_target.valueChanged.connect(self._update_target_pieces)
        cnt.addWidget(self.spin_target, 1, 1)
        self.lbl_counted = QLabel("Contati: 0")
        cnt.addWidget(self.lbl_counted, 2, 0, 1, 2)
        self.lbl_remaining = QLabel("Rimanenti: 0")
        cnt.addWidget(self.lbl_remaining, 3, 0, 1, 2)
        self.btn_cnt_reset = QPushButton("Reset")
        self.btn_cnt_reset.clicked.connect(self._reset_counter)
        cnt.addWidget(self.btn_cnt_reset, 4, 0, 1, 2)
        top_left.addWidget(cnt_container, 0, alignment=Qt.AlignTop | Qt.AlignLeft)

        # Cornice grafica
        graph_frame = QFrame()
        graph_frame.setObjectName("GraphFrame")
        graph_frame.setStyleSheet("QFrame#GraphFrame { border: 1px solid #3b4b5a; border-radius: 8px; }")
        graph_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        graph_layout = QVBoxLayout(graph_frame)
        graph_layout.setContentsMargins(0, 0, 0, 0)
        graph_layout.setSpacing(0)

        self.heads = HeadsView(self.machine, graph_frame)
        self.heads.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        graph_layout.addWidget(self.heads)  # riempie il frame
        top_left.addWidget(graph_frame, 1)

        top_left.setStretch(0, 0)
        top_left.setStretch(1, 1)
        left_col.addLayout(top_left, 1)

        # Riga intermedia: Profilo/Spessore | Inclinazione
        mid = QHBoxLayout()
        mid.setSpacing(8)

        # Profilo/Spessore + icona salvataggio (modal)
        prof_box = QFrame()
        prof_box.setStyleSheet("QFrame { border:1px solid #3b4b5a; border-radius:6px; }")
        prof = QGridLayout(prof_box)
        prof.setHorizontalSpacing(8)
        prof.setVerticalSpacing(6)
        prof.addWidget(QLabel("Profilo"), 0, 0, 1, 5, alignment=Qt.AlignLeft)
        prof.addWidget(QLabel("Nome:"), 1, 0)
        self.cb_profilo = QComboBox()
        self.cb_profilo.setEditable(True)
        for name in sorted(self._profiles.keys()):
            self.cb_profilo.addItem(name)
        self.cb_profilo.setCurrentText(next(iter(self._profiles.keys())))
        self.cb_profilo.currentTextChanged.connect(self._on_profile_changed)
        prof.addWidget(self.cb_profilo, 1, 1, 1, 3)

        self.btn_save_profile = QToolButton()
        self.btn_save_profile.setIcon(QIcon.fromTheme("document-save"))
        if self.btn_save_profile.icon().isNull():
            self.btn_save_profile.setText("💾")
        self.btn_save_profile.setToolTip("Salva profilo/spessore")
        self.btn_save_profile.clicked.connect(self._open_save_profile_dialog)
        prof.addWidget(self.btn_save_profile, 1, 4)

        prof.addWidget(QLabel("Spessore (mm):"), 2, 0)
        self.thickness = QLineEdit()
        self.thickness.setPlaceholderText("0.0")
        cur_prof = self.cb_profilo.currentText().strip()
        self.thickness.setText(str(self._profiles.get(cur_prof, 0.0)))
        self.thickness.textChanged.connect(self._recalc_displays)
        prof.addWidget(self.thickness, 2, 1)
        mid.addWidget(prof_box, 1)

        # Inclinazione (decimali, senza frecce). Accetta . e , (converte a .).
        ang_container = QFrame()
        ang_container.setStyleSheet("QFrame { border:1px solid #3b4b5a; border-radius:6px; }")
        ang = QGridLayout(ang_container)
        ang.setHorizontalSpacing(8)
        ang.setVerticalSpacing(6)

        # SX
        sx_block = QFrame()
        sx_block.setStyleSheet(f"QFrame {{ border:2px solid {SX_COLOR}; border-radius:6px; }}")
        from PySide6.QtWidgets import QVBoxLayout as VB, QHBoxLayout as HB
        sx_lay = VB(sx_block); sx_lay.setContentsMargins(8, 8, 8, 8)
        sx_lay.addWidget(QLabel("Testa SX (0–45°)"))
        sx_row = HB()
        self.btn_sx_45 = QPushButton("45°"); self.btn_sx_45.setStyleSheet("background:#8e44ad; color:white;")
        self.btn_sx_45.clicked.connect(lambda: self._set_angle_quick('sx', 45.0))
        self.btn_sx_0 = QPushButton("0°"); self.btn_sx_0.setStyleSheet("background:#2c3e50; color:#ecf0f1;")
        self.btn_sx_0.clicked.connect(lambda: self._set_angle_quick('sx', 0.0))
        self.spin_sx = QDoubleSpinBox()
        self.spin_sx.setRange(0.0, 45.0)
        self.spin_sx.setDecimals(1)
        self.spin_sx.setSingleStep(0.1)
        self.spin_sx.setLocale(QLocale(QLocale.C))  # accetta il punto
        self.spin_sx.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_sx.setValue(float(getattr(self.machine, "left_head_angle", 0.0)))
        self.spin_sx.valueChanged.connect(self._apply_angles)
        self.spin_sx.lineEdit().textEdited.connect(lambda s: self._force_decimal_point(self.spin_sx, s))
        sx_row.addWidget(self.btn_sx_45); sx_row.addWidget(self.btn_sx_0); sx_row.addWidget(self.spin_sx)
        sx_lay.addLayout(sx_row)

        # DX
        dx_block = QFrame()
        dx_block.setStyleSheet(f"QFrame {{ border:2px solid {DX_COLOR}; border-radius:6px; }}")
        dx_lay = VB(dx_block); dx_lay.setContentsMargins(8, 8, 8, 8)
        dx_lay.addWidget(QLabel("Testa DX (0–45°)"))
        dx_row = HB()
        self.spin_dx = QDoubleSpinBox()
        self.spin_dx.setRange(0.0, 45.0)
        self.spin_dx.setDecimals(1)
        self.spin_dx.setSingleStep(0.1)
        self.spin_dx.setLocale(QLocale(QLocale.C))
        self.spin_dx.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_dx.setValue(float(getattr(self.machine, "right_head_angle", 0.0)))
        self.spin_dx.valueChanged.connect(self._apply_angles)
        self.spin_dx.lineEdit().textEdited.connect(lambda s: self._force_decimal_point(self.spin_dx, s))
        self.btn_dx_0 = QPushButton("0°"); self.btn_dx_0.setStyleSheet("background:#2c3e50; color:#ecf0f1;")
        self.btn_dx_0.clicked.connect(lambda: self._set_angle_quick('dx', 0.0))
        self.btn_dx_45 = QPushButton("45°"); self.btn_dx_45.setStyleSheet("background:#8e44ad; color:white;")
        self.btn_dx_45.clicked.connect(lambda: self._set_angle_quick('dx', 45.0))
        dx_row.addWidget(self.spin_dx); dx_row.addWidget(self.btn_dx_0); dx_row.addWidget(self.btn_dx_45)
        dx_lay.addLayout(dx_row)

        ang.addWidget(sx_block, 0, 0); ang.addWidget(dx_block, 0, 1)
        mid.addWidget(ang_container, 1)
        left_col.addLayout(mid, 0)

        # Riga bassa: misura + pulsanti + Quota + dettagli FQ
        bottom_box = QVBoxLayout(); bottom_box.setSpacing(8)
        meas_row = QHBoxLayout()
        meas_row.addWidget(QLabel("Misura esterna (mm):"), 0, alignment=Qt.AlignLeft)
        self.ext_len = QLineEdit()
        self.ext_len.setPlaceholderText("Es. 1000.0")
        self.ext_len.setStyleSheet("font-size: 24px; font-weight: 700;")
        self.ext_len.setMinimumHeight(44)
        self.ext_len.textChanged.connect(self._recalc_displays)
        meas_row.addWidget(self.ext_len, 1)
        bottom_box.addLayout(meas_row)

        ctrl_row = QHBoxLayout()
        self.btn_brake = QPushButton("SBLOCCA")
        self.btn_brake.setMinimumHeight(52)
        self.btn_brake.clicked.connect(self._toggle_brake)
        ctrl_row.addWidget(self.btn_brake, 0, alignment=Qt.AlignLeft)

        center_col = QVBoxLayout()
        center_col.setSpacing(2)
        center_col.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.lbl_target_big = QLabel("Quota: — mm")
        self.lbl_target_big.setStyleSheet("font-size: 28px; font-weight: 800;")
        center_col.addWidget(self.lbl_target_big, 0, alignment=Qt.AlignHCenter | Qt.AlignVCenter)
        self.lbl_fq_details = QLabel("")
        self.lbl_fq_details.setVisible(False)
        self.lbl_fq_details.setStyleSheet("color:#9b59b6; font-weight:700;")
        center_col.addWidget(self.lbl_fq_details, 0, alignment=Qt.AlignHCenter | Qt.AlignVCenter)
        ctrl_row.addLayout(center_col, 1)

        self.btn_start = QPushButton("START")
        self.btn_start.setMinimumHeight(52)
        self.btn_start.clicked.connect(self._start_positioning)
        ctrl_row.addWidget(self.btn_start, 0, alignment=Qt.AlignRight)

        bottom_box.addLayout(ctrl_row)
        left_col.addLayout(bottom_box, 0)

        # Sidebar destra: Status + Fuori Quota + Intestatura (one-shot)
        right_container = QFrame()
        right_container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        right_container.setFixedWidth(180)
        right_col = QVBoxLayout(right_container)
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(6)

        self.status_panel = StatusPanel(self.machine, title="STATO")
        self.status_panel.setFixedWidth(180)
        self.status_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        right_col.addWidget(self.status_panel, 1)

        fq_box = QFrame()
        fq_box.setFixedSize(QSize(180, 200))  # spazio extra per intestatura
        fq_box.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius:6px; }")
        fq = QGridLayout(fq_box)
        fq.setHorizontalSpacing(6)
        fq.setVerticalSpacing(4)

        self.chk_fuori_quota = QCheckBox("Fuori quota")
        self.chk_fuori_quota.toggled.connect(self._on_fuori_quota_toggle)
        fq.addWidget(self.chk_fuori_quota, 0, 0, 1, 2)

        fq.addWidget(QLabel("Offset:"), 1, 0)
        self.spin_offset = QDoubleSpinBox()
        self.spin_offset.setRange(0.0, 1000.0)
        self.spin_offset.setDecimals(0)
        self.spin_offset.setValue(120.0)
        self.spin_offset.setSuffix(" mm")
        self.spin_offset.setButtonSymbols(QAbstractSpinBox.NoButtons)
        fq.addWidget(self.spin_offset, 1, 1)

        # Pulsante unico INTESATURA (rinominato) - nessuna checkbox persistente
        self.btn_intesta = QPushButton("INTESTATURA")
        self.btn_intesta.clicked.connect(self._do_intestatura)
        fq.addWidget(self.btn_intesta, 2, 0, 1, 2)

        right_col.addWidget(fq_box, 0, alignment=Qt.AlignTop)

        # Montaggio colonne
        root.addWidget(left_container, 1)
        root.addWidget(right_container, 0)

        self._start_poll()

    # ---------- Banner helpers ----------
    def _style_banner_warn(self):
        self.banner.setStyleSheet("background:#f7ca4a; color:#3c2b13; border-radius:6px; padding:8px; font-weight:700;")

    def _style_banner_info(self):
        self.banner.setStyleSheet("background:#2d98da; color:white; border-radius:6px; padding:8px; font-weight:700;")

    def _style_banner_err(self):
        self.banner.setStyleSheet("background:#e74c3c; color:white; border-radius:6px; padding:8px; font-weight:700;")

    def _show_info(self, msg: str, auto_hide_ms: int = 0):
        self._style_banner_info()
        self.banner.setText(msg)
        self.banner.setVisible(True)
        if auto_hide_ms > 0:
            QTimer.singleShot(auto_hide_ms, lambda: self.banner.setVisible(False))

    def _show_warn(self, msg: str, auto_hide_ms: int = 0):
        self._style_banner_warn()
        self.banner.setText(msg)
        self.banner.setVisible(True)
        if auto_hide_ms > 0:
            QTimer.singleShot(auto_hide_ms, lambda: self.banner.setVisible(False))

    def _show_err(self, msg: str, auto_hide_ms: int = 0):
        self._style_banner_err()
        self.banner.setText(msg)
        self.banner.setVisible(True)
        if auto_hide_ms > 0:
            QTimer.singleShot(auto_hide_ms, lambda: self.banner.setVisible(False))

    # ---------- Utils ----------
    def _force_decimal_point(self, spinbox: QDoubleSpinBox, s: str):
        # accetta ',' e la converte in '.' senza creare loop
        if ',' in s:
            new_s = s.replace(',', '.')
            if new_s != s:
                spinbox.lineEdit().setText(new_s)

    def _on_profile_changed(self, name: str):
        name = (name or "").strip()
        try:
            if name in self._profiles:
                self.thickness.setText(str(self._profiles.get(name, 0.0)))
        except Exception:
            pass
        self._recalc_displays()

    def _open_save_profile_dialog(self):
        if not ProfileEditDialog or not self.profiles_store:
            self._show_info("Modulo profili non disponibile in questa build.", auto_hide_ms=2500)
            return
        cur_name = (self.cb_profilo.currentText() or "").strip()
        try:
            cur_th = float((self.thickness.text() or "0").replace(",", "."))
        except Exception:
            cur_th = 0.0
        dlg = ProfileEditDialog(self, default_name=cur_name, default_thickness=cur_th)
        if dlg.exec():
            name, th = dlg.result_name, dlg.result_thickness
            try:
                self.profiles_store.upsert_profile(name, th)
                self._profiles[name] = th
                if self.cb_profilo.findText(name) < 0:
                    self.cb_profilo.addItem(name)
                self.cb_profilo.setCurrentText(name)
                self.thickness.setText(str(th))
                self._show_info("Profilo salvato.", auto_hide_ms=2000)
            except Exception as e:
                self._show_err(f"Errore salvataggio: {e!s}")

    def _set_angle_quick(self, side: str, val: float):
        if side == "sx":
            self.spin_sx.setValue(float(val))
        else:
            self.spin_dx.setValue(float(val))
        self._apply_angles()

    def _apply_angles(self):
        # Leggo dal testo per supportare sia '.' che ','
        sx = self._parse_float(self.spin_sx.text(), 0.0)
        dx = self._parse_float(self.spin_dx.text(), 0.0)
        sx = max(0.0, min(45.0, sx))
        dx = max(0.0, min(45.0, dx))
        ok = True
        if hasattr(self.machine, "set_head_angles"):
            ok = bool(self.machine.set_head_angles(sx, dx))
        else:
            setattr(self.machine, "left_head_angle", sx)
            setattr(self.machine, "right_head_angle", dx)
        if not ok:
            self._show_warn("Angoli non applicati (EMG?)", auto_hide_ms=2500)
        try:
            self.heads.refresh()
        except Exception:
            pass

    def _parse_float(self, s: str, default: float = 0.0) -> float:
        try:
            return float((str(s) or "").replace(",", ".").strip())
        except Exception:
            return default

    def _recalc_displays(self):
        # La quota live è aggiornata nel tick; qui potremo inserire preview se richiesto
        pass

    # ---------- Fuori Quota / Target ----------
    def _compute_target_from_inputs(self):
        # Calcola quota interna e target (mai posizionare a "min" forzatamente; usa banner/proposta FQ)
        ext = self._parse_float(self.ext_len.text(), 0.0)
        th = self._parse_float(self.thickness.text(), 0.0)
        sx = self._parse_float(self.spin_sx.text(), 0.0)
        dx = self._parse_float(self.spin_dx.text(), 0.0)
        if ext <= 0:
            raise ValueError("MISURA ESTERNA NON VALIDA")

        det_sx = th * math.tan(math.radians(sx)) if sx > 0 and th > 0 else 0.0
        det_dx = th * math.tan(math.radians(dx)) if dx > 0 and th > 0 else 0.0
        internal = ext - (det_sx + det_dx)

        min_q = float(getattr(self.machine, "min_distance", 250.0))
        max_q = float(getattr(self.machine, "max_cut_length", 4000.0))
        offset = float(self.spin_offset.value())
        min_with_offset = max(0.0, min_q - offset)

        # Messaggi e condizioni
        if internal < min_with_offset:
            self._show_warn(f"Quota troppo piccola: {internal:.1f} < {min_with_offset:.1f} mm (min {min_q:.0f} − offset {offset:.0f})")
            self._last_internal = None
            self._last_target = None
            self.lbl_fq_details.setVisible(False)
            raise ValueError("Quota troppo piccola")

        if internal < min_q and not self.chk_fuori_quota.isChecked():
            self._show_warn(f"Quota {internal:.1f} sotto minima ({min_q:.1f}). Abilita FUORI QUOTA per taglio.")
            self._last_internal = None
            self._last_target = None
            self.lbl_fq_details.setVisible(False)
            raise ValueError("Quota sotto minima: abilita Fuori Quota")

        # Nessun warning
        self.banner.setVisible(False)

        if internal < min_q and self.chk_fuori_quota.isChecked():
            target = max(min_q, internal + offset)
            # Mostra dettagli Fuori Quota
            self._last_internal = internal
            self._last_target = target
            self.lbl_fq_details.setText(f"Pezzo: {internal:.1f} mm | Pos. testa: {target:.1f} mm (quota+offset)")
            self.lbl_fq_details.setVisible(True)
        else:
            target = internal
            self._last_internal = None
            self._last_target = None
            self.lbl_fq_details.setVisible(False)

        if target > max_q:
            self.lbl_fq_details.setVisible(False)
            raise ValueError(f"QUOTA MAX {int(max_q)}MM")

        return target, sx, dx

    def _on_fuori_quota_toggle(self, on: bool):
        # In Fuori Quota inibire SEMPRE lama DX (mobile); quando FQ off, riabilitarla
        self._set_right_blade_inhibit(bool(on))
        # azzera indicatore
        self.lbl_fq_details.setVisible(False)
        self._last_internal = None
        self._last_target = None

    # ---------- Intestatura (one-shot) ----------
    def _do_intestatura(self):
        # Solo operazione di preparazione; taglio avviato dall'operatore
        if not self.chk_fuori_quota.isChecked():
            self._show_warn("Abilita prima la modalità Fuori Quota.")
            return
        if getattr(self.machine, "emergency_active", False):
            self._show_warn("EMERGENZA ATTIVA.")
            return
        if not getattr(self.machine, "machine_homed", False):
            self._show_warn("ESEGUI AZZERA (HOMING) prima.")
            return
        if self._intest_in_progress:
            return

        min_q = float(getattr(self.machine, "min_distance", 250.0))
        # Memorizza stato precedente
        self._intest_in_progress = True
        self._intest_prev_ang_dx = float(getattr(self.machine, "right_head_angle", 0.0) or 0.0)

        # Inibizioni: SX inibita, DX abilitata per il taglio
        self._set_left_blade_inhibit(True)
        self._set_right_blade_inhibit(False)

        # Imposta angolo DX a 45°, SX invariato
        sx_cur = float(getattr(self.machine, "left_head_angle", 0.0) or 0.0)
        if hasattr(self.machine, "set_head_angles"):
            self.machine.set_head_angles(sx_cur, 45.0)
        else:
            setattr(self.machine, "right_head_angle", 45.0)
        try:
            self.heads.refresh()
        except Exception:
            pass

        # Sblocca freno per muovere
        if getattr(self.machine, "brake_active", False) and hasattr(self.machine, "toggle_brake"):
            self.machine.toggle_brake()  # sblocca

        # Muovi a minima, poi blocca freno e attendi taglio (nessuna finestra modale)
        def _after_move_ui():
            # Blocca il freno (se non è già attivo)
            if hasattr(self.machine, "toggle_brake"):
                if not getattr(self.machine, "brake_active", False):
                    self.machine.toggle_brake()
            # Salva conteggio DX iniziale
            self._intest_dx_count_before = self._get_dx_piece_count()
            self._show_info("Intestatura pronta: DX @45° alla minima. SX INIBITA, DX ABILITATA. Esegui taglio da pulsantiera.")

        if hasattr(self.machine, "move_to_length_and_angles"):
            # Assicura callback UI-safe
            self.machine.move_to_length_and_angles(
                length_mm=float(min_q), ang_sx=float(sx_cur), ang_dx=45.0,
                done_cb=lambda ok, msg: QTimer.singleShot(0, _after_move_ui)
            )
        else:
            QTimer.singleShot(0, _after_move_ui)

    def _finish_intestatura(self):
        # Ripristini post-taglio
        fq = self.chk_fuori_quota.isChecked()

        # SX lama torna abilitata; DX re-inibita se FQ attivo
        self._set_left_blade_inhibit(False)
        self._set_right_blade_inhibit(True if fq else False)

        # Ripristina angolo DX precedente
        sx_cur = float(getattr(self.machine, "left_head_angle", 0.0) or 0.0)
        if hasattr(self.machine, "set_head_angles"):
            self.machine.set_head_angles(sx_cur, float(self._intest_prev_ang_dx))
        else:
            setattr(self.machine, "right_head_angle", float(self._intest_prev_ang_dx))
        try:
            self.heads.refresh()
        except Exception:
            pass

        # Se abbiamo un target FQ calcolato, riposiziona a quota+offset
        if fq and self._last_target is not None:
            # Sblocca freno per muovere
            if getattr(self.machine, "brake_active", False) and hasattr(self.machine, "toggle_brake"):
                self.machine.toggle_brake()
            if hasattr(self.machine, "move_to_length_and_angles"):
                self.machine.move_to_length_and_angles(
                    length_mm=float(self._last_target),
                    ang_sx=sx_cur,
                    ang_dx=float(self._intest_prev_ang_dx),
                    done_cb=lambda ok, msg: None
                )

        # Reset stato intestatura
        self._intest_in_progress = False
        self._intest_dx_count_before = None
        self._show_info("Intestatura completata.", auto_hide_ms=2000)

    def _get_dx_piece_count(self):
        # Prova varie denominazioni comuni dal firmware
        for name in [
            "right_head_piece_count", "dx_piece_count", "right_cut_count",
            "piece_count_right", "cut_dx_count", "semi_auto_count_done_dx"
        ]:
            if hasattr(self.machine, name):
                try:
                    return int(getattr(self.machine, name))
                except Exception:
                    try:
                        return int(float(getattr(self.machine, name) or 0))
                    except Exception:
                        return None
        return None

    def _inc_dx_piece_count(self):
        # Simulazione incremento conteggio pezzi DX (sviluppo)
        for name in [
            "right_head_piece_count", "dx_piece_count", "right_cut_count",
            "piece_count_right", "cut_dx_count", "semi_auto_count_done_dx"
        ]:
            if hasattr(self.machine, name):
                try:
                    cur = int(getattr(self.machine, name) or 0)
                except Exception:
                    cur = 0
                setattr(self.machine, name, cur + 1)
                return
        # Se non esiste alcun attributo, crea quello più “parlante”
        setattr(self.machine, "right_head_piece_count", 1)

    # ---------- Contapezzi ----------
    def _update_target_pieces(self, v: int):
        setattr(self.machine, "semi_auto_target_pieces", int(v))

    def _reset_counter(self):
        setattr(self.machine, "semi_auto_count_done", 0)

    # ---------- Azioni ----------
    def _start_positioning(self):
        if getattr(self.machine, "emergency_active", False):
            self._show_warn("EMERGENZA ATTIVA: ESEGUI AZZERA")
            return
        if not getattr(self.machine, "machine_homed", False):
            self._show_warn("ESEGUI AZZERA (HOMING)")
            return
        if getattr(self.machine, "positioning_active", False):
            self._show_info("Movimento in corso")
            return

        try:
            target, sx, dx = self._compute_target_from_inputs()
        except Exception:
            # banner già mostrato
            return

        # Sblocca freno se serve
        if getattr(self.machine, "brake_active", False) and hasattr(self.machine, "toggle_brake"):
            self.machine.toggle_brake()

        # Avvio movimento
        if hasattr(self.machine, "move_to_length_and_angles"):
            self.machine.move_to_length_and_angles(
                length_mm=float(target), ang_sx=float(sx), ang_dx=float(dx),
                done_cb=lambda ok, msg: None
            )
        self._update_buttons()

    def _toggle_brake(self):
        if hasattr(self.machine, "toggle_brake"):
            ok = self.machine.toggle_brake()
            if not ok:
                self._show_warn("Operazione non consentita")
        self._update_buttons()

    # ---------- Poll ----------
    def _start_poll(self):
        self._poll = QTimer(self)
        self._poll.setInterval(200)
        self._poll.timeout.connect(self._tick)
        self._poll.start()
        self._update_buttons()

    def _tick(self):
        # Status + Grafica
        try:
            self.status_panel.refresh()
        except Exception:
            pass
        try:
            self.heads.refresh()
        except Exception:
            pass

        # Quota live: encoder -> fallback a position_current
        pos = getattr(self.machine, "encoder_position", None)
        if pos is None:
            pos = getattr(self.machine, "position_current", None)
        try:
            self.lbl_target_big.setText(f"Quota: {float(pos):.1f} mm" if pos is not None else "Quota: — mm")
        except Exception:
            self.lbl_target_big.setText("Quota: — mm")

        # Monitor fine intestatura via contatore DX
        if self._intest_in_progress and (self._intest_dx_count_before is not None):
            cur = self._get_dx_piece_count()
            if cur is not None and cur > self._intest_dx_count_before:
                # Chiude intestatura in modo UI-safe
                QTimer.singleShot(0, self._finish_intestatura)

        # Contapezzi
        tgt = int(getattr(self.machine, "semi_auto_target_pieces", 0))
        done = int(getattr(self.machine, "semi_auto_count_done", 0))
        rem = max(0, tgt - done)
        self.lbl_remaining.setText(f"Rimanenti: {rem}")
        self.lbl_counted.setText(f"Contati: {done}")

        self._update_buttons()

    def _update_buttons(self):
        homed = bool(getattr(self.machine, "machine_homed", False))
        emg = bool(getattr(self.machine, "emergency_active", False))
        mov = bool(getattr(self.machine, "positioning_active", False))
        # START
        try:
            self.btn_start.setEnabled(homed and not emg and not mov)
        except Exception:
            pass
        # BLOCCA / SBLOCCA
        brk = bool(getattr(self.machine, "brake_active", False))
        try:
            self.btn_brake.setEnabled(homed and not emg and not mov)
            self.btn_brake.setText("SBLOCCA" if brk else "BLOCCA")
        except Exception:
            pass

    # ---------- Inibizioni Lama ----------
    def _set_left_blade_inhibit(self, on: bool):
        # setta attributo o chiama API se presente
        if hasattr(self.machine, "set_left_blade_inhibit"):
            try:
                self.machine.set_left_blade_inhibit(bool(on))
                return
            except Exception:
                pass
        setattr(self.machine, "left_blade_inhibit", bool(on))

    def _set_right_blade_inhibit(self, on: bool):
        if hasattr(self.machine, "set_right_blade_inhibit"):
            try:
                self.machine.set_right_blade_inhibit(bool(on))
                return
            except Exception:
                pass
        setattr(self.machine, "right_blade_inhibit", bool(on))

    # ---------- Simulazioni da tastiera ----------
    def keyPressEvent(self, event: QKeyEvent):
        # F6 / K = simula conteggio pezzo DX (+1) per chiudere intestatura
        if event.key() in (Qt.Key_F6, Qt.Key_K):
            self._inc_dx_piece_count()
            event.accept()
            return
        super().keyPressEvent(event)
