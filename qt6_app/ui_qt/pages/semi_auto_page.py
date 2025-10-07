from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QSpinBox, QGridLayout, QDoubleSpinBox, QLineEdit, QComboBox,
    QMessageBox, QSizePolicy, QCheckBox, QAbstractSpinBox, QToolButton
)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QIcon
from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel
from ui_qt.widgets.heads_view import HeadsView
import math

# Moduli opzionali per salvataggio profili su SQLite
try:
    from ui_qt.dialogs.profile_edit_dialog import ProfileEditDialog
    from ui_qt.services.profiles_store import ProfilesStore
except Exception:
    # Fallback semplice (dialog e store locali)
    from PySide6.QtWidgets import QDialog
    import sqlite3
    from pathlib import Path

    class ProfileEditDialog(QDialog):
        def __init__(self, parent=None, default_name="", default_thickness=0.0):
            super().__init__(parent)
            self.setWindowTitle("Salva profilo")
            self.result_name = None
            self.result_thickness = None

            lay = QVBoxLayout(self)
            row1 = QHBoxLayout()
            row1.addWidget(QLabel("Nome profilo:"))
            self.edit_name = QLineEdit()
            self.edit_name.setText(str(default_name or ""))
            row1.addWidget(self.edit_name, 1)
            lay.addLayout(row1)

            row2 = QHBoxLayout()
            row2.addWidget(QLabel("Spessore (mm):"))
            self.edit_th = QLineEdit()
            self.edit_th.setText(str(default_thickness or 0.0))
            row2.addWidget(self.edit_th, 1)
            lay.addLayout(row2)

            btns = QHBoxLayout()
            self.btn_ok = QPushButton("OK")
            self.btn_cancel = QPushButton("Annulla")
            self.btn_ok.clicked.connect(self._accept)
            self.btn_cancel.clicked.connect(self.reject)
            btns.addWidget(self.btn_cancel)
            btns.addStretch(1)
            btns.addWidget(self.btn_ok)
            lay.addLayout(btns)

            self.setMinimumWidth(320)

        def _accept(self):
            name = (self.edit_name.text() or "").strip()
            try:
                th = float((self.edit_th.text() or "0").replace(",", "."))
            except Exception:
                th = 0.0
            if not name:
                return
            self.result_name = name
            self.result_thickness = th
            self.accept()

    DB_PATH = Path(__file__).resolve().parents[3] / "data" / "profiles.db"

    class ProfilesStore:
        def __init__(self):
            self._ensure_db()

        def _connect(self):
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            return sqlite3.connect(DB_PATH)

        def _ensure_db(self):
            with self._connect() as con:
                con.execute("""
                    CREATE TABLE IF NOT EXISTS profiles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL,
                        thickness REAL NOT NULL DEFAULT 0
                    )
                """)
                con.commit()

        def upsert_profile(self, name: str, thickness: float):
            with self._connect() as con:
                con.execute("""
                    INSERT INTO profiles(name, thickness) VALUES(?, ?)
                    ON CONFLICT(name) DO UPDATE SET thickness=excluded.thickness
                """, (name, float(thickness)))
                con.commit()

        def list_profiles(self):
            with self._connect() as con:
                cur = con.execute("SELECT id, name, thickness FROM profiles ORDER BY name ASC")
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]

        def get_profile(self, name: str):
            with self._connect() as con:
                cur = con.execute("SELECT id, name, thickness FROM profiles WHERE name=?", (name,))
                row = cur.fetchone()
                if not row:
                    return None
                return {"id": row[0], "name": row[1], "thickness": row[2]}


SX_COLOR = "#2980b9"
DX_COLOR = "#9b59b6"


class SemiAutoPage(QWidget):
    """
    Colonne:
    - Sinistra (expanding): top [Contapezzi 190x190 | Grafica massimizzata], poi [Profilo/Spessore | Inclinazione],
      poi riga bassa con: [Misura esterna (input grande)] e sotto [Btn SX=BLOCCA/SBLOCCA | Quota (centro) | Btn DX=START]
    - Destra (fissa 180px): Status (riempie in altezza), sotto Fuori Quota 180x160
    - START calcola la quota target (detrazioni + fuori quota) e avvia il movimento; BLOCCA/SBLOCCA freno funzionano
    """
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine
        self._poll = None

        # Store profili/spessori (SQLite condiviso)
        self.profiles_store = ProfilesStore()

        # Cache profili in memoria: dict nome -> thickness
        self._profiles = self._load_profiles_dict()

        self._build()

    def _load_profiles_dict(self):
        profs = {}
        try:
            rows = self.profiles_store.list_profiles()
            for row in rows:
                profs[row["name"]] = float(row["thickness"] or 0.0)
            if not profs:
                # seed iniziale
                for n, t in (("Nessuno", 0.0), ("Alluminio 50", 50.0), ("PVC 60", 60.0), ("Legno 40", 40.0)):
                    self.profiles_store.upsert_profile(n, t)
                for row in self.profiles_store.list_profiles():
                    profs[row["name"]] = float(row["thickness"] or 0.0)
        except Exception:
            profs = {"Nessuno": 0.0}
        return profs

    def _build(self):
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

        # Banner per quota troppo piccola/minima
        self.banner = QLabel("")
        self.banner.setVisible(False)
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet("background:#f7ca4a; color:#3c2b13; border-radius:6px; padding:8px; font-weight:700;")
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

        # Inclinazione con input decimali e senza frecce
        ang_container = QFrame()
        ang_container.setStyleSheet("QFrame { border:1px solid #3b4b5a; border-radius:6px; }")
        ang = QGridLayout(ang_container)
        ang.setHorizontalSpacing(8)
        ang.setVerticalSpacing(6)

        # SX
        sx_block = QFrame()
        sx_block.setStyleSheet(f"QFrame {{ border:2px solid {SX_COLOR}; border-radius:6px; }}")
        sx_lay = QVBoxLayout(sx_block)
        sx_lay.setContentsMargins(8, 8, 8, 8)
        sx_lay.addWidget(QLabel("Testa SX (0–45°)"))
        sx_row = QHBoxLayout()
        self.btn_sx_45 = QPushButton("45°")
        self.btn_sx_45.setStyleSheet("background:#8e44ad; color:white;")
        self.btn_sx_45.clicked.connect(lambda: self._set_angle_quick('sx', 45.0))
        self.btn_sx_0 = QPushButton("0°")
        self.btn_sx_0.setStyleSheet("background:#2c3e50; color:#ecf0f1;")
        self.btn_sx_0.clicked.connect(lambda: self._set_angle_quick('sx', 0.0))
        self.spin_sx = QDoubleSpinBox()
        self.spin_sx.setRange(0.0, 45.0)
        self.spin_sx.setDecimals(1)
        self.spin_sx.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_sx.setValue(float(getattr(self.machine, "left_head_angle", 0.0)))
        self.spin_sx.valueChanged.connect(self._apply_angles)
        # Accetta anche virgola -> converto a punto
        self.spin_sx.lineEdit().textChanged.connect(lambda s: self._force_decimal_point(self.spin_sx, s))
        sx_row.addWidget(self.btn_sx_45)
        sx_row.addWidget(self.btn_sx_0)
        sx_row.addWidget(self.spin_sx)
        sx_lay.addLayout(sx_row)

        # DX
        dx_block = QFrame()
        dx_block.setStyleSheet(f"QFrame {{ border:2px solid {DX_COLOR}; border-radius:6px; }}")
        dx_lay = QVBoxLayout(dx_block)
        dx_lay.setContentsMargins(8, 8, 8, 8)
        dx_lay.addWidget(QLabel("Testa DX (0–45°)"))
        dx_row = QHBoxLayout()
        self.spin_dx = QDoubleSpinBox()
        self.spin_dx.setRange(0.0, 45.0)
        self.spin_dx.setDecimals(1)
        self.spin_dx.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_dx.setValue(float(getattr(self.machine, "right_head_angle", 0.0)))
        self.spin_dx.valueChanged.connect(self._apply_angles)
        self.spin_dx.lineEdit().textChanged.connect(lambda s: self._force_decimal_point(self.spin_dx, s))
        self.btn_dx_0 = QPushButton("0°")
        self.btn_dx_0.setStyleSheet("background:#2c3e50; color:#ecf0f1;")
        self.btn_dx_0.clicked.connect(lambda: self._set_angle_quick('dx', 0.0))
        self.btn_dx_45 = QPushButton("45°")
        self.btn_dx_45.setStyleSheet("background:#8e44ad; color:white;")
        self.btn_dx_45.clicked.connect(lambda: self._set_angle_quick('dx', 45.0))
        dx_row.addWidget(self.spin_dx)
        dx_row.addWidget(self.btn_dx_0)
        dx_row.addWidget(self.btn_dx_45)
        dx_lay.addLayout(dx_row)

        ang.addWidget(sx_block, 0, 0)
        ang.addWidget(dx_block, 0, 1)
        mid.addWidget(ang_container, 1)
        left_col.addLayout(mid, 0)

        # Riga bassa: misura sopra, sotto i pulsanti agli angoli e "Quota" al centro
        bottom_box = QVBoxLayout()
        bottom_box.setSpacing(8)
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

        self.lbl_target_big = QLabel("Quota: — mm")
        self.lbl_target_big.setStyleSheet("font-size: 28px; font-weight: 800;")
        ctrl_row.addWidget(self.lbl_target_big, 1, alignment=Qt.AlignHCenter | Qt.AlignVCenter)

        self.btn_start = QPushButton("START")
        self.btn_start.setMinimumHeight(52)
        self.btn_start.clicked.connect(self._start_positioning)
        ctrl_row.addWidget(self.btn_start, 0, alignment=Qt.AlignRight)

        bottom_box.addLayout(ctrl_row)
        left_col.addLayout(bottom_box, 0)

        # Sidebar destra: Status + Fuori Quota
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
        fq_box.setFixedSize(QSize(180, 160))
        fq_box.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius:6px; }")
        fq = QGridLayout(fq_box)
        fq.setHorizontalSpacing(6)
        fq.setVerticalSpacing(4)
        self.chk_fuori_quota = QCheckBox("Fuori quota")
        fq.addWidget(self.chk_fuori_quota, 0, 0, 1, 2)
        fq.addWidget(QLabel("Offset:"), 1, 0)
        self.spin_offset = QDoubleSpinBox()
        self.spin_offset.setRange(0.0, 1000.0)
        self.spin_offset.setDecimals(0)
        self.spin_offset.setValue(120.0)
        self.spin_offset.setSuffix(" mm")
        self.spin_offset.setButtonSymbols(QAbstractSpinBox.NoButtons)
        fq.addWidget(self.spin_offset, 1, 1)
        right_col.addWidget(fq_box, 0, alignment=Qt.AlignTop)

        # Montaggio colonne
        root.addWidget(left_container, 1)
        root.addWidget(right_container, 0)

        self._start_poll()

    # Forza '.' come separatore, accettando anche ','
    def _force_decimal_point(self, spinbox: QDoubleSpinBox, s: str):
        if ',' in s:
            spinbox.lineEdit().setText(s.replace(',', '.'))

    # ---- Profili ----
    def _on_profile_changed(self, name: str):
        name = (name or "").strip()
        try:
            if name in self._profiles:
                self.thickness.setText(str(self._profiles.get(name, 0.0)))
        except Exception:
            pass
        self._recalc_displays()

    def _open_save_profile_dialog(self):
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
                QMessageBox.information(self, "Profili", "Profilo salvato.")
            except Exception as e:
                QMessageBox.warning(self, "Profili", f"Errore salvataggio: {e!s}")

    # ---- Helpers ----
    def _set_angle_quick(self, side: str, val: float):
        if side == "sx":
            self.spin_sx.setValue(float(val))
        else:
            self.spin_dx.setValue(float(val))
        self._apply_angles()

    def _apply_angles(self):
        # Leggo il testo per supportare sia '.' che ','
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
            try:
                QMessageBox.warning(self, "Attenzione", "Angoli non applicati (EMG?)")
            except Exception:
                pass
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

    def _compute_target_from_inputs(self):
        # Calcola quota interna e target (senza posizionare mai a "min", solo banner/consiglio Fuori Quota)
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

        # Mostra banner e non posiziona se sotto minima
        if internal < min_with_offset:
            self.banner.setVisible(True)
            self.banner.setText(
                f"Quota troppo piccola: {internal:.1f} mm < minima {min_with_offset:.1f} mm (min {min_q:.0f} − offset {offset:.0f})"
            )
            raise ValueError("Quota troppo piccola")
        if internal < min_q and not self.chk_fuori_quota.isChecked():
            self.banner.setVisible(True)
            self.banner.setText(
                f"Quota {internal:.1f} mm sotto la minima ({min_q:.1f}). "
                "Puoi abilitare la modalità FUORI QUOTA per eseguire il taglio."
            )
            raise ValueError("Quota sotto minima: abilita Fuori Quota")
        self.banner.setVisible(False)

        if internal < min_q and self.chk_fuori_quota.isChecked():
            target = max(min_q, internal + offset)
        else:
            target = internal

        if target > max_q:
            raise ValueError(f"QUOTA MAX {int(max_q)}MM")
        return target, sx, dx

    # ---- Contapezzi ----
    def _update_target_pieces(self, v: int):
        setattr(self.machine, "semi_auto_target_pieces", int(v))

    def _reset_counter(self):
        setattr(self.machine, "semi_auto_count_done", 0)

    # ---- Azioni ----
    def _start_positioning(self):
        if getattr(self.machine, "emergency_active", False):
            QMessageBox.warning(self, "Attenzione", "EMERGENZA ATTIVA: ESEGUI AZZERA")
            return
        if not getattr(self.machine, "machine_homed", False):
            QMessageBox.warning(self, "Attenzione", "ESEGUI AZZERA (HOMING)")
            return
        if getattr(self.machine, "positioning_active", False):
            QMessageBox.information(self, "Info", "Movimento in corso")
            return

        try:
            target, sx, dx = self._compute_target_from_inputs()
        except Exception:
            # Banner già mostrato quando serve
            return

        if getattr(self.machine, "brake_active", False) and hasattr(self.machine, "toggle_brake"):
            if not self.machine.toggle_brake():
                QMessageBox.warning(self, "Attenzione", "Impossibile sbloccare il freno.")
                return

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
                try:
                    QMessageBox.warning(self, "Attenzione", "Operazione non consentita")
                except Exception:
                    pass
        self._update_buttons()

    # ---- Poll / Stato / Quota live ----
    def _start_poll(self):
        self._poll = QTimer(self)
        self._poll.setInterval(200)
        self._poll.timeout.connect(self._tick)
        self._poll.start()
        self._update_buttons()

    def _tick(self):
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

        tgt = int(getattr(self.machine, "semi_auto_target_pieces", 0))
        done = int(getattr(self.machine, "semi_auto_count_done", 0))
        rem = max(0, tgt - done)
        self.lbl_remaining.setText(f"Rimanenti: {rem}")
        self.lbl_counted.setText(f"Contati: {done}")

        self._update_buttons()

    def _update_buttons(self):
        homed = bool(getattr(self.machine, "machine_homed", False))
        emg = bool(getattr(self.machine, "emergency_active", False))
        brk = bool(getattr(self.machine, "brake_active", False))
        mov = bool(getattr(self.machine, "positioning_active", False))
        try:
            self.btn_start.setEnabled(homed and not emg and not mov)
        except Exception:
            pass
        try:
            self.btn_brake.setEnabled(homed and not emg and not mov)
            self.btn_brake.setText("SBLOCCA" if brk else "BLOCCA")
        except Exception:
            pass
