from typing import Optional, Dict, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QSpinBox, QGridLayout, QDoubleSpinBox, QLineEdit, QComboBox,
    QSizePolicy, QCheckBox, QAbstractSpinBox, QToolButton, QStyle, QApplication,
    QMessageBox, QListWidget, QInputDialog
)
from PySide6.QtCore import Qt, QTimer, QSize, QLocale, QRect
from PySide6.QtGui import QKeyEvent, QGuiApplication
from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel
from ui_qt.widgets.heads_view import HeadsView
from ui_qt.widgets.collapsible_section import CollapsibleSection
from ui_qt.logic.modes import (
    ModeConfig,
    ModeDetector,
    ModeInfo,
    OutOfQuotaHandler,
    UltraShortHandler,
    ExtraLongHandler
)
from ui_qt.logic.modes.out_of_quota_handler import OutOfQuotaConfig
from ui_qt.logic.modes.ultra_short_handler import UltraShortConfig
from ui_qt.logic.modes.extra_long_handler import ExtraLongConfig
from ui_qt.utils.settings import read_settings, write_settings
from ui_qt.logic.angles import normalize_cut_tilt_deg
import math
import logging
from datetime import datetime
import contextlib

# Metro Digitale integration
from ui_qt.services.metro_digitale_manager import get_metro_manager

logger = logging.getLogger("semi_auto_page")

try:
    from ui_qt.services.profiles_store import ProfilesStore
except Exception:
    ProfilesStore = None

try:
    from ui_qt.widgets.section_preview_popup import SectionPreviewPopup
except Exception:
    SectionPreviewPopup = None

SX_COLOR = "#2980b9"
DX_COLOR = "#9b59b6"

STATUS_W = 280
FQ_W = 260
FQ_H = 240
COUNTER_SIZE = 260


class SemiAutoPage(QWidget):
    """
    Refactor: usa MachineAdapter (self.mio) per movimento, testa, freno.
    Intestatura e Fuori Quota mantengono la logica originale, ma le operazioni
    di movimento e angoli passano per command_move / command_set_head_angles.
    """
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine               # raw machine (StatusPanel)
        self.mio = getattr(appwin, "machine_adapter", None)

        # === NEW: Metro Digitale ===
        self.metro_manager = get_metro_manager()
        self._metro_measurements_history = []

        self.profiles_store = ProfilesStore() if ProfilesStore else None
        self._profiles = self._load_profiles_dict()

        # === NEW: Mode system initialization ===
        try:
            settings = read_settings()
            self._mode_config = ModeConfig.from_settings(settings)
            self._mode_detector = ModeDetector(self._mode_config)
            logger.info(f"Mode system initialized: threshold={self._mode_config.ultra_short_threshold:.1f}mm")
        except Exception as e:
            logger.error(f"Error initializing mode system: {e}")
            # Fallback to default config
            self._mode_config = ModeConfig(
                machine_zero_homing_mm=250.0,
                machine_offset_battuta_mm=120.0,
                machine_max_travel_mm=4000.0,
                stock_length_mm=6500.0
            )
            self._mode_detector = ModeDetector(self._mode_config)
        
        # Handlers for special modes (lazy initialization, shared with automatico!)
        self._out_of_quota_handler: Optional[OutOfQuotaHandler] = None
        self._ultra_short_handler: Optional[UltraShortHandler] = None
        self._extra_long_handler: Optional[ExtraLongHandler] = None
        self._current_mode: str = "normal"
        self._current_mode_handler = None
        
        # Movement tracking for UI state management
        self._movement_in_progress = False
        self._cut_sim_busy = False

        # Contapezzi (stato locale = source of truth)
        self._count_done = int(getattr(self.machine, "semi_auto_count_done", 0) or 0)
        try:
            last_qty = int(read_settings().get("semi_auto_last_qty", 0) or 0)
        except Exception:
            last_qty = 0
        saved_target = int(getattr(self.machine, "semi_auto_target_pieces", 0) or 0)
        self._count_target = saved_target if saved_target > 0 else max(0, last_qty)

        # Sequenza multi-step: attesa taglio / conferma operatore
        # None | "await_cut" | "await_proceed"
        self._seq_phase: Optional[str] = None
        self._start_prev = False

        # Stato intestatura / FQ (keep for backward compatibility)
        self._intest_in_progress = False
        self._intest_prev_ang_dx = 0.0
        self._last_internal = None
        self._last_target = None
        self._last_dx_blade_out = None
        self._dx_blade_out_sim = False
        self._blade_pulse_prev = False
        self._ready_to_cut = False

        self._poll = None
        self._section_popup = None
        self.graph_frame = None

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
                    profs = {"Nessuno": 0.0}
            else:
                profs = {"Nessuno": 0.0}
        except Exception:
            profs = {"Nessuno": 0.0}
        return profs

    def refresh_profiles_external(self, select: str | None = None):
        self._profiles = self._load_profiles_dict()
        cur = (self.cb_profilo.currentText() or "").strip()
        self.cb_profilo.blockSignals(True)
        self.cb_profilo.clear()
        for name in sorted(self._profiles.keys()):
            self.cb_profilo.addItem(name)
        if select and select in self._profiles:
            self.cb_profilo.setCurrentText(select)
        elif cur in self._profiles:
            self.cb_profilo.setCurrentText(cur)
        else:
            self.cb_profilo.setCurrentText(next(iter(self._profiles.keys())))
        self.cb_profilo.blockSignals(False)
        self._on_profile_changed(self.cb_profilo.currentText())

    # ---------- UI ----------
    def _build(self):
        self.setFocusPolicy(Qt.StrongFocus)

        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(8)

        left_container = QFrame()
        left_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        left_col = QVBoxLayout(left_container)
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(8)

        header = Header(self.appwin, "SEMI-AUTOMATICO", on_azzera=self._on_homing)
        left_col.addWidget(header, 0)

        self.banner = QLabel("")
        self.banner.setVisible(False)
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet("background:#f7ca4a; color:#3c2b13; border-radius:6px; padding:8px; font-weight:700;")
        left_col.addWidget(self.banner, 0)

        top_left = QHBoxLayout()
        top_left.setSpacing(8)
        top_left.setContentsMargins(0, 0, 0, 0)

        cnt_container = QFrame()
        cnt_container.setFixedSize(QSize(COUNTER_SIZE, COUNTER_SIZE))
        cnt_container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        cnt_container.setStyleSheet("QFrame { border:1px solid #3b4b5a; border-radius:6px; }")
        cnt = QGridLayout(cnt_container)
        cnt.setHorizontalSpacing(8)
        cnt.setVerticalSpacing(6)
        title_cnt = QLabel("CONTAPEZZI")
        title_cnt.setStyleSheet("font-weight:800;")
        cnt.addWidget(title_cnt, 0, 0, 1, 2, alignment=Qt.AlignLeft)
        cnt.addWidget(QLabel("Target:"), 1, 0)
        self.spin_target = QSpinBox()
        self.spin_target.setRange(0, 999999)
        self.spin_target.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_target.setValue(int(self._count_target))
        self.spin_target.valueChanged.connect(self._update_target_pieces)
        cnt.addWidget(self.spin_target, 1, 1)
        self.lbl_counted = QLabel("Contati: 0")
        cnt.addWidget(self.lbl_counted, 2, 0, 1, 2)
        self.lbl_remaining = QLabel("Rimanenti: 0")
        cnt.addWidget(self.lbl_remaining, 3, 0, 1, 2)
        self.btn_cnt_reset = QPushButton("Reset")
        self.btn_cnt_reset.clicked.connect(self._reset_counter)
        cnt.addWidget(self.btn_cnt_reset, 4, 0, 1, 2)
        self.btn_cut_sim = QPushButton("Taglio (sim F7)")
        self.btn_cut_sim.setToolTip("Simula taglio effettuato (test contapezzi / logica).")
        self.btn_cut_sim.setStyleSheet(
            "QPushButton { background:#e67e22; color:#fff; font-weight:700; }"
        )
        self.btn_cut_sim.clicked.connect(self._simulate_cut)
        cnt.addWidget(self.btn_cut_sim, 5, 0, 1, 2)
        top_left.addWidget(cnt_container, 0, alignment=Qt.AlignTop | Qt.AlignLeft)

        self.graph_frame = QFrame()
        self.graph_frame.setObjectName("GraphFrame")
        self.graph_frame.setStyleSheet("QFrame#GraphFrame { border: 1px solid #3b4b5a; border-radius: 8px; }")
        self.graph_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        graph_layout = QVBoxLayout(self.graph_frame)
        graph_layout.setContentsMargins(0, 0, 0, 0)
        graph_layout.setSpacing(0)

        self.heads = HeadsView(self.mio or self.machine, self.graph_frame)
        self.heads.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        graph_layout.addWidget(self.heads)
        top_left.addWidget(self.graph_frame, 1)

        top_left.setStretch(0, 0)
        top_left.setStretch(1, 1)
        left_col.addLayout(top_left, 1)

        mid = QHBoxLayout()
        mid.setSpacing(8)

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
        try:
            self.cb_profilo.highlighted[str].connect(self._hover_profile_highlighted)
        except Exception:
            pass
        try:
            self.cb_profilo.highlighted.connect(self._hover_profile_highlighted_index)
        except Exception:
            pass
        self.cb_profilo.currentTextChanged.connect(self._on_profile_changed)
        prof.addWidget(self.cb_profilo, 1, 1, 1, 3)

        self.btn_save_profile = QToolButton()
        std_icon = QApplication.style().standardIcon(QStyle.SP_DialogSaveButton)
        self.btn_save_profile.setIcon(std_icon)
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

        ang_container = QFrame()
        ang_container.setStyleSheet("QFrame { border:1px solid #3b4b5a; border-radius:6px; }")
        ang = QGridLayout(ang_container)
        ang.setHorizontalSpacing(8)
        ang.setVerticalSpacing(6)

        from PySide6.QtWidgets import QVBoxLayout as VB, QHBoxLayout as HB
        sx_block = QFrame()
        sx_block.setStyleSheet(f"QFrame {{ border:2px solid {SX_COLOR}; border-radius:6px; }}")
        sx_lay = VB(sx_block)
        sx_lay.setContentsMargins(8, 8, 8, 8)
        sx_lay.addWidget(QLabel("Testa SX (0–45°)"))
        sx_row = HB()
        self.btn_sx_45 = QPushButton("45°")
        self.btn_sx_45.setStyleSheet("background:#8e44ad; color:white;")
        self.btn_sx_45.clicked.connect(lambda: self._set_angle_quick('sx', 45.0))
        self.btn_sx_0 = QPushButton("0°")
        self.btn_sx_0.setStyleSheet("background:#2c3e50; color:#ecf0f1;")
        self.btn_sx_0.clicked.connect(lambda: self._set_angle_quick('sx', 0.0))
        self.spin_sx = QDoubleSpinBox()
        self.spin_sx.setRange(0.0, 45.0)
        self.spin_sx.setDecimals(1)
        self.spin_sx.setSingleStep(0.1)
        self.spin_sx.setLocale(QLocale(QLocale.C))
        self.spin_sx.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_sx.setValue(float(getattr(self.machine, "left_head_angle", 0.0)))
        self.spin_sx.valueChanged.connect(lambda *_: self._update_mode_label())
        self.spin_sx.lineEdit().textEdited.connect(lambda s: self._force_decimal_point(self.spin_sx, s))
        self.btn_sx_go = QPushButton("Vai a pos.")
        self.btn_sx_go.setToolTip("Porta la testa SX all'angolo impostato nello spin (es. 30°).")
        self.btn_sx_go.setStyleSheet("background:#2980b9; color:white; font-weight:700;")
        self.btn_sx_go.clicked.connect(self._apply_angles)
        sx_row.addWidget(self.btn_sx_45)
        sx_row.addWidget(self.btn_sx_0)
        self.btn_sx_zero_enc = QPushButton("Azzera enc.")
        self.btn_sx_zero_enc.setToolTip(
            "Azzera encoder SX a mano. In macchina lo zero teste è nell'homing (Azzera)."
        )
        self.btn_sx_zero_enc.clicked.connect(lambda: self._zero_head_encoder("sx"))
        sx_row.addWidget(self.btn_sx_zero_enc)
        sx_row.addWidget(self.spin_sx)
        sx_row.addWidget(self.btn_sx_go)
        sx_lay.addLayout(sx_row)

        dx_block = QFrame()
        dx_block.setStyleSheet(f"QFrame {{ border:2px solid {DX_COLOR}; border-radius:6px; }}")
        dx_lay = VB(dx_block)
        dx_lay.setContentsMargins(8, 8, 8, 8)
        dx_lay.addWidget(QLabel("Testa DX (0–45°)"))
        dx_row = HB()
        self.spin_dx = QDoubleSpinBox()
        self.spin_dx.setRange(0.0, 45.0)
        self.spin_dx.setDecimals(1)
        self.spin_dx.setSingleStep(0.1)
        self.spin_dx.setLocale(QLocale(QLocale.C))
        self.spin_dx.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_dx.setValue(float(getattr(self.machine, "right_head_angle", 0.0)))
        self.spin_dx.valueChanged.connect(lambda *_: self._update_mode_label())
        self.spin_dx.lineEdit().textEdited.connect(lambda s: self._force_decimal_point(self.spin_dx, s))
        self.btn_dx_0 = QPushButton("0°")
        self.btn_dx_0.setStyleSheet("background:#2c3e50; color:#ecf0f1;")
        self.btn_dx_0.clicked.connect(lambda: self._set_angle_quick('dx', 0.0))
        self.btn_dx_45 = QPushButton("45°")
        self.btn_dx_45.setStyleSheet("background:#8e44ad; color:white;")
        self.btn_dx_45.clicked.connect(lambda: self._set_angle_quick('dx', 45.0))
        self.btn_dx_go = QPushButton("Vai a pos.")
        self.btn_dx_go.setToolTip("Porta la testa DX all'angolo impostato nello spin (es. 30°).")
        self.btn_dx_go.setStyleSheet("background:#9b59b6; color:white; font-weight:700;")
        self.btn_dx_go.clicked.connect(self._apply_angles)
        dx_row.addWidget(self.spin_dx)
        dx_row.addWidget(self.btn_dx_go)
        dx_row.addWidget(self.btn_dx_0)
        dx_row.addWidget(self.btn_dx_45)
        self.btn_dx_zero_enc = QPushButton("Azzera enc.")
        self.btn_dx_zero_enc.setToolTip(
            "Azzera encoder DX a mano. In macchina lo zero teste è nell'homing (Azzera)."
        )
        self.btn_dx_zero_enc.clicked.connect(lambda: self._zero_head_encoder("dx"))
        dx_row.addWidget(self.btn_dx_zero_enc)
        dx_lay.addLayout(dx_row)

        ang.addWidget(sx_block, 0, 0)
        ang.addWidget(dx_block, 0, 1)
        mid.addWidget(ang_container, 1)
        left_col.addLayout(mid, 0)

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

        center_col = QVBoxLayout()
        center_col.setSpacing(2)
        center_col.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.lbl_target_big = QLabel("Quota: — mm")
        self.lbl_target_big.setStyleSheet("font-size: 28px; font-weight: 800;")
        center_col.addWidget(self.lbl_target_big, 0, alignment=Qt.AlignHCenter | Qt.AlignVCenter)
        self.lbl_mode = QLabel("Modalità: —")
        self.lbl_mode.setStyleSheet("font-size: 14px; font-weight: 700; color:#3498db;")
        self.lbl_mode.setAlignment(Qt.AlignHCenter)
        center_col.addWidget(self.lbl_mode, 0, alignment=Qt.AlignHCenter | Qt.AlignVCenter)
        self.lbl_fq_details = QLabel("")
        self.lbl_fq_details.setVisible(False)
        self.lbl_fq_details.setStyleSheet("color:#9b59b6; font-weight:700;")
        center_col.addWidget(self.lbl_fq_details, 0, alignment=Qt.AlignHCenter | Qt.AlignVCenter)
        ctrl_row.addLayout(center_col, 1)

        self.btn_start = QPushButton("START")
        self.btn_start.setMinimumHeight(52)
        self.btn_start.clicked.connect(self._on_cut)
        ctrl_row.addWidget(self.btn_start, 0, alignment=Qt.AlignRight)

        bottom_box.addLayout(ctrl_row)
        left_col.addLayout(bottom_box, 0)

        # === NEW: Metro Digitale Section (Collapsible) ===
        if self.metro_manager.is_available():
            metro_collapsible = CollapsibleSection("📡 Metro Digitale", start_collapsed=True)
            metro_content = self._build_metro_section_content()
            metro_collapsible.add_content(metro_content)
            left_col.addWidget(metro_collapsible, 0)

        right_container = QFrame()
        right_container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        right_container.setFixedWidth(STATUS_W)
        right_col = QVBoxLayout(right_container)
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(6)

        self.status_panel = StatusPanel(self.machine, title="STATO")
        self.status_panel.setFixedWidth(STATUS_W)
        self.status_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        right_col.addWidget(self.status_panel, 1)

        # NOTE: "Fuori Quota" section removed - mode detection is now automatic
        # Legacy UI elements preserved for backward compatibility but hidden:
        # Checkbox, offset spinbox, and intestatura button are no longer used
        # Mode is automatically detected based on piece length
        
        # Keep offset spinbox for backward compatibility (may be referenced elsewhere)
        self.spin_offset = QDoubleSpinBox()
        self.spin_offset.setRange(0.0, 1000.0)
        self.spin_offset.setDecimals(0)
        self.spin_offset.setValue(120.0)
        self.spin_offset.setSuffix(" mm")
        self.spin_offset.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_offset.setVisible(False)  # Hidden - not used in new mode system
        
        # Add stub for backward compatibility with legacy code
        class _StubCheckBox:
            def isChecked(self): return False
        self.chk_fuori_quota = _StubCheckBox()

        root.addWidget(left_container, 1)
        root.addWidget(right_container, 0)

        self._start_poll()

    # ---------- Banner helpers ----------
    def _style_banner_info(self):
        self.banner.setStyleSheet("background:#2d98da; color:white; border-radius:6px; padding:8px; font-weight:700;")

    def _style_banner_warn(self):
        self.banner.setStyleSheet("background:#f7ca4a; color:#3c2b13; border-radius:6px; padding:8px; font-weight:700;")

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

    # ---------- Metro Digitale Methods ----------
    def _build_metro_section_content(self) -> QWidget:
        """Build Metro Digitale Bluetooth section content (without outer frame)."""
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        # Connection controls
        conn_layout = QHBoxLayout()
        
        self.lbl_metro_status = QLabel("⚪ Disconnesso")
        self.lbl_metro_status.setStyleSheet("font-weight: 600; color: #2c3e50;")
        conn_layout.addWidget(self.lbl_metro_status)
        
        self.btn_metro_scan = QPushButton("🔍 Cerca")
        self.btn_metro_scan.clicked.connect(self._on_metro_scan)
        self.btn_metro_scan.setStyleSheet("""
            QPushButton {
                background: #3498db;
                color: white;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: 600;
            }
            QPushButton:hover { background: #2980b9; }
        """)
        conn_layout.addWidget(self.btn_metro_scan)
        
        self.combo_metro_devices = QComboBox()
        self.combo_metro_devices.setMinimumWidth(200)
        conn_layout.addWidget(self.combo_metro_devices)
        
        self.btn_metro_connect = QPushButton("🔌 Connetti")
        self.btn_metro_connect.clicked.connect(self._on_metro_connect)
        self.btn_metro_connect.setEnabled(False)
        self.btn_metro_connect.setStyleSheet("""
            QPushButton {
                background: #27ae60;
                color: white;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: 600;
            }
            QPushButton:hover { background: #229954; }
            QPushButton:disabled { background: #7f8c8d; }
        """)
        conn_layout.addWidget(self.btn_metro_connect)
        
        conn_layout.addStretch()
        layout.addLayout(conn_layout)
        
        # Auto-position checkbox
        self.chk_auto_position = QCheckBox("⚡ Auto-Posiziona al ricevimento misura")
        self.chk_auto_position.setStyleSheet("font-size: 11pt; color: #2c3e50;")
        self.chk_auto_position.setToolTip("Se attivo, avvia automaticamente il posizionamento quando riceve una misura")
        layout.addWidget(self.chk_auto_position)
        
        # History
        history_label = QLabel("📋 Cronologia Misure (ultime 10):")
        history_label.setStyleSheet("font-size: 10pt; color: #7f8c8d; margin-top: 8px;")
        layout.addWidget(history_label)
        
        self.list_metro_history = QListWidget()
        self.list_metro_history.setMaximumHeight(100)
        self.list_metro_history.setStyleSheet("""
            QListWidget {
                background: #ffffff;
                border: 1px solid #bdc3c7;
                border-radius: 4px;
                font-size: 10pt;
                color: #2c3e50;
            }
        """)
        layout.addWidget(self.list_metro_history)
        
        return content

    def showEvent(self, event):
        """Page becomes visible."""
        super().showEvent(event)
        
        # Set as current page in metro manager
        if self.metro_manager.is_available():
            self.metro_manager.set_current_page("semi_auto")
            try:
                self.metro_manager.measurement_received.connect(self._on_metro_measurement)
                self.metro_manager.connection_changed.connect(self._on_metro_connection_changed)
            except Exception as e:
                logger.debug(f"Signal already connected: {e}")

    def hideEvent(self, event):
        """Page hidden."""
        super().hideEvent(event)
        
        # Disconnect signals
        if self.metro_manager.is_available():
            try:
                self.metro_manager.measurement_received.disconnect(self._on_metro_measurement)
                self.metro_manager.connection_changed.disconnect(self._on_metro_connection_changed)
            except Exception:
                pass

    def _on_metro_scan(self):
        """Scan for metro devices."""
        self.btn_metro_scan.setEnabled(False)
        self.btn_metro_scan.setText("⏳ Scanning...")
        self.combo_metro_devices.clear()
        
        QTimer.singleShot(100, self._do_metro_scan)

    def _do_metro_scan(self):
        """Execute scan (blocking)."""
        try:
            devices = self.metro_manager.scan_devices()
            
            if devices:
                for d in devices:
                    self.combo_metro_devices.addItem(f"{d['name']} ({d['address']})", d['address'])
                self.btn_metro_connect.setEnabled(True)
                self._show_info(f"Trovati {len(devices)} dispositivi", auto_hide_ms=2000)
            else:
                self._show_warn("Nessun Metro Digitale trovato", auto_hide_ms=2500)
        
        except Exception as e:
            logger.error(f"Scan error: {e}")
            self._show_warn("Errore scan", auto_hide_ms=2500)
        
        finally:
            self.btn_metro_scan.setEnabled(True)
            self.btn_metro_scan.setText("🔍 Cerca")

    def _on_metro_connect(self):
        """Connect to selected metro."""
        if self.combo_metro_devices.currentIndex() < 0:
            return
        
        address = self.combo_metro_devices.currentData()
        self.btn_metro_connect.setEnabled(False)
        self.lbl_metro_status.setText("⏳ Connessione...")
        
        QTimer.singleShot(100, lambda: self._do_metro_connect(address))

    def _do_metro_connect(self, address: str):
        """Execute connection."""
        success = self.metro_manager.connect(address)
        
        if success:
            self._show_info("✅ Metro connesso", auto_hide_ms=2000)
        else:
            self._show_warn("❌ Connessione fallita", auto_hide_ms=2500)
            self.btn_metro_connect.setEnabled(True)

    def _on_metro_connection_changed(self, connected: bool):
        """Metro connection status changed."""
        if connected:
            self.lbl_metro_status.setText("🟢 Connesso")
            self.btn_metro_connect.setEnabled(False)
            self.btn_metro_scan.setEnabled(False)
            self.combo_metro_devices.setEnabled(False)
        else:
            self.lbl_metro_status.setText("⚪ Disconnesso")
            self.btn_metro_connect.setEnabled(False)
            self.btn_metro_scan.setEnabled(True)
            self.combo_metro_devices.setEnabled(True)

    def _on_metro_measurement(self, mm: float, mode: str, auto_start: bool):
        """
        Measurement received from metro.
        
        Args:
            mm: Measurement in millimeters
            mode: "semi_auto" | "automatico"
            auto_start: Auto-start flag from metro
        """
        # Only process if routed to semi_auto
        if mode != "semi_auto":
            logger.info(f"Measurement routed to {mode}, ignoring in semi_auto")
            return
        
        # Validate
        if mm <= 0 or mm > 10000:  # Reasonable range
            self._show_warn(f"Misura invalida: {mm:.1f}mm", auto_hide_ms=2500)
            return
        
        # Populate external length field
        self.ext_len.setText(str(mm))
        
        # Add to history
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._metro_measurements_history.append({
            "value": mm,
            "mode": mode,
            "timestamp": timestamp
        })
        
        # Update history list (last 10)
        self.list_metro_history.clear()
        for item in self._metro_measurements_history[-10:]:
            self.list_metro_history.addItem(
                f"✓ {item['value']:.1f}mm → {item['mode'].upper()} @ {item['timestamp']}"
            )
        self.list_metro_history.scrollToBottom()
        
        # Feedback
        self._show_info(f"📏 Misura ricevuta: {mm:.1f}mm [SEMI-AUTO]", auto_hide_ms=2000)
        
        # Auto-position if enabled
        if self.chk_auto_position.isChecked() or auto_start:
            logger.info("Auto-positioning enabled, starting movement...")
            QTimer.singleShot(500, self._on_cut)

    # ---------- Utils ----------
    def _force_decimal_point(self, spinbox: QDoubleSpinBox, s: str):
        if ',' in s:
            new_s = s.replace(',', '.')
            if new_s != s:
                spinbox.lineEdit().setText(new_s)

    def _hover_profile_highlighted(self, name: str):
        name = (name or "").strip()
        if name:
            self._show_profile_preview_ephemeral(name)

    def _hover_profile_highlighted_index(self, index: int):
        try:
            if index is not None and index >= 0:
                name = (self.cb_profilo.itemText(index) or "").strip()
                if name:
                    self._show_profile_preview_ephemeral(name)
        except Exception:
            pass

    def _on_profile_changed(self, name: str):
        name = (name or "").strip()
        try:
            if name in self._profiles:
                self.thickness.setText(str(self._profiles.get(name, 0.0)))
        except Exception:
            pass
        self._recalc_displays()

    def _ensure_popup(self):
        if self._section_popup is None and SectionPreviewPopup:
            self._section_popup = SectionPreviewPopup(self.appwin, "Sezione profilo")
        return self._section_popup

    def _show_profile_preview_ephemeral(self, profile_name: str, auto_hide_ms: int = 1200):
        if not (SectionPreviewPopup and self.profiles_store and self.graph_frame):
            return
        try:
            shape = self.profiles_store.get_profile_shape(profile_name)
            if not shape or not shape.get("dxf_path"):
                if self._section_popup:
                    self._section_popup.close()
                    self._section_popup = None
                return
            popup = self._ensure_popup()
            if not popup:
                return
            popup.load_path(shape["dxf_path"])
            bw = float(shape.get("bbox_w") or 0.0)
            bh = float(shape.get("bbox_h") or 0.0)
            if bw > 0.0 and bh > 0.0:
                screen = QGuiApplication.primaryScreen()
                scr_rect: QRect = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
                max_w = int(scr_rect.width() * 0.25)
                max_h = int(scr_rect.height() * 0.25)
                desired_w = int(min(bw, max_w))
                desired_h = int(min(bh, max_h))
                desired_w = max(160, desired_w)
                desired_h = max(120, desired_h)
                popup.resize(desired_w, desired_h)
            try:
                popup.show_top_left_of(self.graph_frame, auto_hide_ms=auto_hide_ms)
            except TypeError:
                popup.show_top_left_of(self.graph_frame)
                QTimer.singleShot(auto_hide_ms, lambda: popup.close())
        except Exception:
            try:
                if self._section_popup:
                    self._section_popup.close()
                    self._section_popup = None
            except Exception:
                pass

    def _open_save_profile_dialog(self):
        try:
            from ui_qt.dialogs.profile_edit_dialog import ProfileEditDialog
        except Exception:
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
            if not self.profiles_store:
                return
            try:
                self.profiles_store.upsert_profile(name, th)
                self.refresh_profiles_external(select=name)
                self._show_info("Profilo salvato.", auto_hide_ms=2000)
            except Exception as e:
                self._show_warn(f"Errore salvataggio: {e!s}", auto_hide_ms=2500)

    def _set_angle_quick(self, side: str, val: float):
        if side == "sx":
            self.spin_sx.setValue(float(val))
        else:
            self.spin_dx.setValue(float(val))
        self._apply_angles()

    def _apply_angles(self):
        sx = max(0.0, min(45.0, float(self.spin_sx.value())))
        dx = max(0.0, min(45.0, float(self.spin_dx.value())))
        ok = True
        if self.mio:
            ok = self.mio.command_set_head_angles(sx, dx)
        else:
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

    def _zero_head_encoder(self, side: str):
        """Azzera l'encoder di inclinazione della testa (posizione meccanica 0°)."""
        ok = False
        if self.mio and hasattr(self.mio, "command_zero_head_encoder"):
            ok = bool(self.mio.command_zero_head_encoder(side))
        elif hasattr(self.machine, "command_zero_head_encoder"):
            ok = bool(self.machine.command_zero_head_encoder(side))
        if ok:
            if side == "sx":
                self.spin_sx.setValue(0.0)
            elif side == "dx":
                self.spin_dx.setValue(0.0)
            self._apply_angles()
            self._show_info(f"Encoder testa {side.upper()} azzerato.", auto_hide_ms=2000)
        else:
            self._show_warn("Azzeramento encoder non disponibile.", auto_hide_ms=2500)
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
        self._update_mode_label()

    # ---------- Fuori Quota / Target ----------
    def _compute_target_from_inputs(self):
        ext = self._parse_float(self.ext_len.text(), 0.0)
        th = self._parse_float(self.thickness.text(), 0.0)
        sx = self._parse_float(self.spin_sx.text(), 0.0)
        dx = self._parse_float(self.spin_dx.text(), 0.0)
        if ext <= 0:
            self._show_warn("Inserisci una misura esterna valida (mm).", auto_hide_ms=2500)
            raise ValueError("MISURA ESTERNA NON VALIDA")

        det_sx = th * math.tan(math.radians(sx)) if sx > 0 and th > 0 else 0.0
        det_dx = th * math.tan(math.radians(dx)) if dx > 0 and th > 0 else 0.0
        internal = ext - (det_sx + det_dx)

        min_q = float(getattr(self.machine, "min_distance", 250.0))
        max_q = float(getattr(self.machine, "max_cut_length", 4000.0))
        offset = float(self.spin_offset.value())
        min_with_offset = max(0.0, min_q - offset)

        if internal < min_with_offset:
            self._show_warn(
                f"Quota troppo piccola: {internal:.1f} < {min_with_offset:.1f} mm (min {min_q:.0f} − offset {offset:.0f})",
                auto_hide_ms=3000
            )
            self._last_internal = None
            self._last_target = None
            self.lbl_fq_details.setVisible(False)
            raise ValueError("Quota troppo piccola")

        if internal < min_q and not self.chk_fuori_quota.isChecked():
            self._show_warn(f"Quota {internal:.1f} sotto minima ({min_q:.1f}). Abilita FUORI QUOTA.", auto_hide_ms=3000)
            self._last_internal = None
            self._last_target = None
            self.lbl_fq_details.setVisible(False)
            raise ValueError("Quota sotto minima: abilita Fuori Quota")

        self.banner.setVisible(False)

        if internal < min_q and self.chk_fuori_quota.isChecked():
            target = max(min_q, internal + offset)
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
            self._show_warn(f"Quota oltre massima: {target:.1f} > {max_q:.1f} mm")
            raise ValueError(f"QUOTA MAX {int(max_q)}MM")

        return target, sx, dx

    def _on_fuori_quota_toggle(self, on: bool):
        # In futuro: spostare in adapter un comando set_right_blade_inhibit
        if hasattr(self.machine, "set_right_blade_inhibit"):
            try:
                self.machine.set_right_blade_inhibit(bool(on))
            except Exception:
                pass
        else:
            setattr(self.machine, "right_blade_inhibit", bool(on))
        self.lbl_fq_details.setVisible(False)
        self._last_internal = None
        self._last_target = None

    # ---------- REMOVED: Old intestatura methods ----------
    # _do_intestatura and _finish_intestatura have been removed (was ~117 lines)
    # They are replaced by shared handlers from logic/modes/
    # Mode detection is now automatic, no manual "Fuori Quota" checkbox needed

    # ---------- Lettura “uscita lama DX” ----------
    def _get_dx_blade_out(self):
        if self._dx_blade_out_sim:
            return True
        if self.mio:
            return self.mio.get_input("dx_blade_out")
        for name in ("dx_blade_out", "right_blade_out", "blade_out_right"):
            if hasattr(self.machine, name):
                try:
                    return bool(getattr(self.machine, name))
                except Exception:
                    return False
        return False

    # ---------- Contapezzi ----------
    def _refresh_counter_labels(self):
        rem = max(0, int(self._count_target) - int(self._count_done))
        try:
            self.lbl_counted.setText(f"Contati: {int(self._count_done)}")
            self.lbl_remaining.setText(f"Rimanenti: {rem}")
        except Exception:
            pass

    def _update_target_pieces(self, v: int):
        self._count_target = int(v)
        with contextlib.suppress(Exception):
            setattr(self.machine, "semi_auto_target_pieces", int(v))
        if int(v) > 0:
            with contextlib.suppress(Exception):
                write_settings({"semi_auto_last_qty": int(v)})
        self._refresh_counter_labels()

    def _ask_piece_quantity(self) -> Optional[int]:
        """
        Popup «Quanti pezzi?» prima del posizionamento.
        Riepiloga il numero corrente e permette di modificarlo.
        Restituisce None se annullato; rifiuta 0.
        """
        current = max(0, int(self._count_target or 0))
        if current <= 0:
            try:
                current = int(read_settings().get("semi_auto_last_qty", 1) or 1)
            except Exception:
                current = 1
        if current <= 0:
            current = 1

        label = (
            f"Numero pezzi attualmente impostato: {int(self._count_target)}\n\n"
            f"Quanti pezzi vuoi produrre con questa misura?\n"
            f"(0 non consentito — conferma o modifica e procedi)"
        )
        qty, ok = QInputDialog.getInt(
            self,
            "Quanti pezzi?",
            label,
            int(current),
            1,
            999999,
            1,
        )
        if not ok:
            return None
        if int(qty) <= 0:
            self._show_warn("Numero pezzi deve essere ≥ 1", auto_hide_ms=2500)
            return None
        return int(qty)

    def _apply_piece_quantity(self, qty: int):
        """Applica target pezzi, azzera contati e memorizza l'ultimo valore."""
        qty = int(qty)
        self._count_target = qty
        self._count_done = 0
        with contextlib.suppress(Exception):
            setattr(self.machine, "semi_auto_target_pieces", qty)
            setattr(self.machine, "semi_auto_count_done", 0)
        with contextlib.suppress(Exception):
            self.spin_target.blockSignals(True)
            self.spin_target.setValue(qty)
            self.spin_target.blockSignals(False)
        with contextlib.suppress(Exception):
            write_settings({"semi_auto_last_qty": qty})
        self._refresh_counter_labels()

    def _reset_counter(self):
        self._count_done = 0
        with contextlib.suppress(Exception):
            setattr(self.machine, "semi_auto_count_done", 0)
        self._refresh_counter_labels()

    def _increment_counter_if_enabled(self):
        """Incrementa il contapezzi (solo taglio pezzo finale)."""
        self._count_done = int(self._count_done) + 1
        with contextlib.suppress(Exception):
            setattr(self.machine, "semi_auto_count_done", self._count_done)
        self._refresh_counter_labels()
        logger.info(
            "Contapezzi +1 → %s (target=%s, rimanenti=%s)",
            self._count_done,
            self._count_target,
            max(0, self._count_target - self._count_done),
        )

    def _is_intermediate_seq_cut(self) -> bool:
        """True se il taglio corrente è uno step intermedio (non conta pezzo)."""
        return self._seq_phase == "await_cut" and self._should_continue_multi_step()

    def _simulate_cut(self):
        """
        Simula taglio: blocco morse → taglio → sblocco morse + contapezzi (se finale).
        """
        if self._cut_sim_busy:
            return
        if self._is_movement_active() or self._movement_in_progress:
            self._show_warn("Attendi fine posizionamento prima del taglio", auto_hide_ms=2000)
            return
        if self._seq_phase == "await_proceed":
            self._show_warn("Taglio già eseguito — premi START per proseguire", auto_hide_ms=2500)
            return
        self._cut_sim_busy = True
        self._lock_morse()
        self._show_info("🔒 Morse bloccate — taglio…", auto_hide_ms=800)
        QTimer.singleShot(220, self._complete_simulated_cut)

    def _complete_simulated_cut(self):
        """Completa il taglio simulato dopo il blocco morse."""
        try:
            # Evita doppio conteggio se command_sim_cut_pulse alza blade_pulse
            self._blade_pulse_prev = True
            if self.mio and hasattr(self.mio, "command_sim_cut_pulse"):
                try:
                    self.mio.command_sim_cut_pulse()
                except Exception as e:
                    logger.debug(f"command_sim_cut_pulse: {e}")

            intermediate = self._is_intermediate_seq_cut()
            if intermediate:
                # Taglio intestatura / step intermedio: non conta pezzo
                self._ready_to_cut = False
                self._seq_phase = "await_proceed"
                step_hint = self._seq_proceed_message()
                self._show_info(
                    f"✂️ Taglio step eseguito — {step_hint}",
                    auto_hide_ms=4000,
                )
                logger.info("Taglio intermedio sequenza: in attesa START per proseguire")
            else:
                self._increment_counter_if_enabled()
                self._ready_to_cut = False
                self._seq_phase = None
                mode = self._current_mode or "normal"
                self._show_info(f"✂️ Taglio simulato ({mode})", auto_hide_ms=1200)
                # Sequenza speciale conclusa
                if self._current_mode_handler:
                    with contextlib.suppress(Exception):
                        self._current_mode_handler.reset()
                    self._current_mode_handler = None

            QTimer.singleShot(250, self._finish_cut_unlock)
        except Exception as e:
            logger.error(f"Errore taglio sim: {e}")
            self._unlock_morse()
            self._cut_sim_busy = False

    def _finish_cut_unlock(self):
        """Sblocca morse a fine taglio sim e libera il flag busy."""
        self._unlock_morse()
        if self._seq_phase == "await_proceed":
            self._show_info(self._seq_proceed_message(), auto_hide_ms=3500)
        else:
            self._show_info("🔓 Morse sbloccate", auto_hide_ms=1200)
        self._cut_sim_busy = False

    def _on_cut_done_feedback(self):
        """Compatibilità: percorso diretto (es. F6) senza sequenza morse."""
        if self._is_intermediate_seq_cut():
            self._ready_to_cut = False
            self._seq_phase = "await_proceed"
            self._unlock_morse()
            self._show_info(self._seq_proceed_message(), auto_hide_ms=3500)
            return
        self._increment_counter_if_enabled()
        self._ready_to_cut = False
        self._seq_phase = None
        self._unlock_morse()
        mode = self._current_mode or "normal"
        self._show_info(f"✂️ Taglio simulato ({mode})", auto_hide_ms=1800)

    def _seq_proceed_message(self) -> str:
        """Messaggio guida per proseguire la sequenza multi-step."""
        mode = self._current_mode or ""
        step = 0
        if mode == "out_of_quota" and self._out_of_quota_handler:
            step = self._out_of_quota_handler.get_current_step()
            return "Premi START per Step 2/2 (taglio finale)"
        if mode == "ultra_short" and self._ultra_short_handler:
            step = self._ultra_short_handler.get_current_step()
            if step == 1:
                return "Premi START per Step 2/3 (retrazione DX)"
            if step == 2:
                return "Premi START per Step 3/3 (taglio finale)"
        if mode == "extra_long" and self._extra_long_handler:
            step = self._extra_long_handler.get_current_step()
            if step == 1:
                return "Premi START per Step 2/3 (retrazione DX)"
            if step == 2:
                return "Premi START per Step 3/3 (taglio finale)"
        return "Premi START per proseguire la sequenza"

    def _seq_step_requires_cut(self) -> bool:
        """
        True se lo step appena completato richiede un taglio prima di continuare.
        Retrazione (ultra/extra step 2 dopo posa) = solo conferma START.
        """
        mode = self._current_mode or ""
        if mode == "out_of_quota" and self._out_of_quota_handler:
            return self._out_of_quota_handler.get_current_step() == 1
        if mode == "ultra_short" and self._ultra_short_handler:
            return self._ultra_short_handler.get_current_step() == 1
        if mode == "extra_long" and self._extra_long_handler:
            return self._extra_long_handler.get_current_step() == 1
        return False

    def _on_multi_step_arrival(self):
        """Gestisce l'arrivo in posizione durante una sequenza multi-step."""
        self._movement_in_progress = False
        try:
            if self.mio:
                self.mio.command_lock_brake()
            else:
                setattr(self.machine, "brake_active", True)
        except Exception as e:
            logger.error(f"Errore blocco freno multi-step: {e}")

        if self._seq_step_requires_cut():
            self._ready_to_cut = True
            self._seq_phase = "await_cut"
            self._enable_inputs_after_movement()
            mode_name = self._mode_detector.get_mode_display_name(self._current_mode or "")
            self._show_info(
                f"✅ {mode_name}: in posizione — esegui TAGLIO (F7 / pedale), "
                f"poi premi START per proseguire",
                auto_hide_ms=5000,
            )
            logger.info("Sequenza: await_cut prima dello step successivo")
        else:
            # Retrazione completata: solo conferma operatore
            self._ready_to_cut = False
            self._seq_phase = "await_proceed"
            self._enable_inputs_after_movement()
            msg = self._seq_proceed_message()
            self._show_info(f"✅ Posizionamento step ok — {msg}", auto_hide_ms=4500)
            logger.info("Sequenza: await_proceed (retrazione)")

    def _try_continue_sequence_from_start(self) -> bool:
        """
        Se siamo in await_proceed, avvia lo step successivo.
        Restituisce True se ha gestito l'evento (non avviare un nuovo ciclo).
        """
        if self._seq_phase == "await_cut":
            self._show_warn(
                "Esegui prima il TAGLIO (F7 / pedale), poi premi START",
                auto_hide_ms=3000,
            )
            return True
        if self._seq_phase != "await_proceed":
            return False
        if not self._should_continue_multi_step():
            self._seq_phase = None
            return False

        self._seq_phase = None
        self._ready_to_cut = False
        self._disable_inputs_during_movement()
        # Sblocca freno prima dello step successivo
        try:
            if self.mio:
                self.mio.command_release_brake()
            else:
                setattr(self.machine, "brake_active", False)
        except Exception as e:
            logger.error(f"Errore sblocco freno pre-step: {e}")
        self._show_info("▶️ Proseguo sequenza…", auto_hide_ms=1500)
        QTimer.singleShot(150, self._continue_multi_step_sequence)
        return True

    def _update_mode_label(self):
        """Aggiorna etichetta modalità in base alla misura inserita."""
        try:
            ext = self._parse_float(self.ext_len.text(), 0.0)
            th = self._parse_float(self.thickness.text(), 0.0)
            ax = self._parse_float(self.spin_sx.text(), 0.0)
            ad = self._parse_float(self.spin_dx.text(), 0.0)
        except Exception:
            self.lbl_mode.setText("Modalità: —")
            return
        if ext <= 0:
            self.lbl_mode.setText("Modalità: —")
            self.lbl_mode.setStyleSheet("font-size: 14px; font-weight: 700; color:#7f8c8d;")
            return
        det_sx = th * math.tan(math.radians(ax)) if ax > 0 and th > 0 else 0.0
        det_dx = th * math.tan(math.radians(ad)) if ad > 0 and th > 0 else 0.0
        length = ext - (det_sx + det_dx)
        try:
            info = self._mode_detector.detect(length)
        except Exception:
            self.lbl_mode.setText("Modalità: —")
            return
        name = self._mode_detector.get_mode_display_name(info.mode_name)
        colors = {
            "normal": "#3498db",
            "out_of_quota": "#e67e22",
            "ultra_short": "#e74c3c",
            "extra_long": "#9b59b6",
            "invalid": "#7f8c8d",
        }
        col = colors.get(info.mode_name, "#3498db")
        self.lbl_mode.setText(f"Modalità: {name} ({length:.0f} mm)")
        self.lbl_mode.setStyleSheet(f"font-size: 14px; font-weight: 700; color:{col};")
        if info.mode_name in ("out_of_quota", "ultra_short", "extra_long") and info.warning_message:
            # Mostra solo la prima riga come hint
            first = (info.warning_message or "").split("\n")[0]
            self.lbl_fq_details.setText(first)
            self.lbl_fq_details.setVisible(True)
        else:
            self.lbl_fq_details.setVisible(False)

    # ---------- Azioni ----------
    def _on_cut(self):
        """
        Handler for cut/positioning button.
        
        With automatic mode detection:
        - Normal: direct movement
        - Out of quota: 2-step cycle
        - Ultra short: 3-step cycle (inverted heads)
        - Extra long: 3-step cycle
        """
        # Continuazione sequenza multi-step (dopo taglio / retrazione)
        if self._try_continue_sequence_from_start():
            return

        # Close any open profile preview popup
        try:
            if self._section_popup:
                self._section_popup.close()
                self._section_popup = None
        except Exception:
            pass
        
        # === 1. Basic validations ===
        if getattr(self.machine, "emergency_active", False):
            self._show_warn("EMERGENZA ATTIVA", auto_hide_ms=2500)
            return
        
        if not getattr(self.machine, "machine_homed", False):
            self._show_warn("ESEGUI AZZERA (HOMING) prima", auto_hide_ms=2500)
            return
        
        # Check if already moving
        if self.mio and self.mio.is_positioning_active():
            self._show_info("Movimento in corso", auto_hide_ms=2000)
            return
        if (not self.mio) and getattr(self.machine, "positioning_active", False):
            self._show_info("Movimento in corso", auto_hide_ms=2000)
            return
        
        # === 2. Read parameters from UI ===
        try:
            ext = self._parse_float(self.ext_len.text(), 0.0)
            th = self._parse_float(self.thickness.text(), 0.0)
            angle_sx = self._parse_float(self.spin_sx.text(), 0.0)
            angle_dx = self._parse_float(self.spin_dx.text(), 0.0)
        except Exception as e:
            self._show_warn(f"Parametri invalidi: {e}", auto_hide_ms=2500)
            return
        
        if ext <= 0:
            self._show_warn("Inserisci una misura esterna valida (mm)", auto_hide_ms=2500)
            return
        
        # Calculate internal length (subtract detractions from angles)
        det_sx = th * math.tan(math.radians(angle_sx)) if angle_sx > 0 and th > 0 else 0.0
        det_dx = th * math.tan(math.radians(angle_dx)) if angle_dx > 0 and th > 0 else 0.0
        length = ext - (det_sx + det_dx)
        
        if length <= 0:
            self._show_warn("Lunghezza interna deve essere > 0", auto_hide_ms=2500)
            return

        # === 2b. Quanti pezzi? (obbligatorio, ≥ 1) ===
        qty = self._ask_piece_quantity()
        if qty is None:
            self._show_info("Operazione annullata", auto_hide_ms=1500)
            return
        self._apply_piece_quantity(qty)
        
        # === 3. Detect mode automatically ===
        try:
            mode_info = self._mode_detector.detect(length)
        except Exception as e:
            logger.error(f"Error detecting mode: {e}")
            self._show_warn(f"Errore rilevamento modalità: {e}", auto_hide_ms=3000)
            return
        
        if not mode_info.is_valid:
            self._show_warn(mode_info.error_message, auto_hide_ms=3000)
            return
        
        self._current_mode = mode_info.mode_name
        self._seq_phase = None
        logger.info(f"Mode detected: {self._current_mode} for {length:.1f}mm")
        
        # === 4. Confirm special modes ===
        if mode_info.mode_range and mode_info.mode_range.requires_confirmation:
            mode_display = self._mode_detector.get_mode_display_name(mode_info.mode_name)
            reply = QMessageBox.question(
                self,
                f"Conferma Modalità {mode_display}",
                f"{mode_info.warning_message}\n\nContinuare?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                self._show_info("Operazione annullata", auto_hide_ms=2000)
                logger.info("Special mode operation cancelled by user")
                return
        
        # === 5. Contesto macchina (frizione ON + morse SW) ===
        ctx_mode = mode_info.mode_name if mode_info.mode_name != "normal" else "semi"
        if self.mio and hasattr(self.mio, "set_mode_context"):
            try:
                self.mio.set_mode_context(
                    ctx_mode,
                    piece_length_mm=length,
                    bar_length_mm=self._mode_config.stock_length_mm
                )
            except Exception as e:
                logger.error(f"Error setting mode context: {e}")
        self._ensure_clutch_engaged()
        
        # === 6. Execute for detected mode ===
        piece = {
            "len": length,
            "ax": normalize_cut_tilt_deg(angle_sx),
            "ad": normalize_cut_tilt_deg(angle_dx),
            "profile": self.cb_profilo.currentText().strip() if hasattr(self, 'cb_profilo') else "",
            "element": ""
        }
        
        if mode_info.mode_name == "out_of_quota":
            self._execute_out_of_quota(piece)
        
        elif mode_info.mode_name == "ultra_short":
            self._execute_ultra_short(piece)
        
        elif mode_info.mode_name == "extra_long":
            self._execute_extra_long(piece)
        
        else:  # normal
            self._execute_normal_move(piece)
    
    def _execute_normal_move(self, piece: Dict[str, Any]):
        """Execute normal mode movement (250-4000mm)."""
        
        if not self.mio:
            logger.error("Machine adapter not available")
            self._show_warn("Adattatore macchina non disponibile", auto_hide_ms=2500)
            return
        
        # Configure blades
        try:
            self.mio.command_set_blade_inhibit(
                left=(piece.get("ax", 0) == 0),
                right=(piece.get("ad", 0) == 0)
            )
        except Exception as e:
            logger.error(f"Error configuring blades for piece {piece['len']:.0f}mm, ax={piece.get('ax', 0)}, ad={piece.get('ad', 0)}: {e}")
        
        # Execute movement
        try:
            success = self.mio.command_move(
                piece["len"],
                piece.get("ax", 0),
                piece.get("ad", 0),
                profile=piece.get("profile", ""),
                element=piece.get("element", "")
            )
            
            if success:
                self._movement_in_progress = True
                self._disable_inputs_during_movement()
                self._show_info(f"▶️ Posizionamento {piece['len']:.0f}mm", auto_hide_ms=2000)
                logger.info(f"Semi-auto normal movement started: {piece['len']:.0f}mm")
                self._update_buttons()  # Update button states when movement starts
            else:
                self._show_warn("❌ Movimento non avviato", auto_hide_ms=2500)
                logger.error("Normal movement failed to start")
        
        except Exception as e:
            logger.error(f"Error starting movement: {e}")
            self._show_warn(f"Errore movimento: {e}", auto_hide_ms=2500)

    def _execute_out_of_quota(self, piece: Dict[str, Any]):
        """Esegue fuori quota (2 step): avvia e lancia subito Step 1."""
        
        if not self.mio:
            logger.error("Machine adapter not available")
            return
        
        if not self._out_of_quota_handler:
            try:
                config = OutOfQuotaConfig(
                    zero_homing_mm=self._mode_config.machine_zero_homing_mm,
                    offset_battuta_mm=self._mode_config.machine_offset_battuta_mm
                )
                self._out_of_quota_handler = OutOfQuotaHandler(self.mio, config)
                logger.info("OutOfQuotaHandler initialized")
            except Exception as e:
                logger.error(f"Error creating OutOfQuotaHandler: {e}")
                self._show_warn(f"Errore inizializzazione: {e}", auto_hide_ms=2500)
                return
        
        try:
            success = self._out_of_quota_handler.start_sequence(
                target_length_mm=piece["len"],
                angle_sx=piece.get("ax", 0),
                angle_dx=piece.get("ad", 0),
            )
            
            if success and self._out_of_quota_handler.execute_step_1():
                self._current_mode_handler = self._out_of_quota_handler
                self._disable_inputs_during_movement()
                self._movement_in_progress = True
                self._ready_to_cut = False
                self._show_info("🔴 Fuori Quota: Step 1/2 - Intestatura", auto_hide_ms=3000)
                logger.info(f"Out of quota step 1 started: {piece['len']:.0f}mm")
            else:
                self._show_warn("❌ Sequenza fuori quota non avviata", auto_hide_ms=2500)
                logger.error("Out of quota sequence failed to start")
        
        except Exception as e:
            logger.error(f"Error starting out of quota: {e}")
            self._show_warn(f"Errore fuori quota: {e}", auto_hide_ms=2500)

    def _execute_ultra_short(self, piece: Dict[str, Any]):
        """Esegue ultra corta (3 step): avvia e lancia subito Step 1."""
        
        if not self.mio:
            logger.error("Machine adapter not available")
            return
        
        if not self._ultra_short_handler:
            try:
                config = UltraShortConfig(
                    zero_homing_mm=self._mode_config.machine_zero_homing_mm,
                    offset_battuta_mm=self._mode_config.machine_offset_battuta_mm
                )
                self._ultra_short_handler = UltraShortHandler(self.mio, config)
                logger.info("UltraShortHandler initialized")
            except Exception as e:
                logger.error(f"Error creating UltraShortHandler: {e}")
                self._show_warn(f"Errore inizializzazione: {e}", auto_hide_ms=2500)
                return
        
        try:
            success = self._ultra_short_handler.start_sequence(
                target_length_mm=piece["len"],
                angle_sx=piece.get("ax", 0),
                angle_dx=piece.get("ad", 0),
            )
            
            if success and self._ultra_short_handler.execute_step_1():
                self._current_mode_handler = self._ultra_short_handler
                self._disable_inputs_during_movement()
                self._movement_in_progress = True
                self._ready_to_cut = False
                self._show_info("🟡 Ultra Corta: Step 1/3 - Intestatura SX", auto_hide_ms=3000)
                logger.info(f"Ultra short step 1 started: {piece['len']:.0f}mm")
            else:
                self._show_warn("❌ Sequenza ultra corta non avviata", auto_hide_ms=2500)
                logger.error("Ultra short sequence failed to start")
        
        except Exception as e:
            logger.error(f"Error starting ultra short: {e}")
            self._show_warn(f"Errore ultra corta: {e}", auto_hide_ms=2500)

    def _execute_extra_long(self, piece: Dict[str, Any]):
        """Esegue extra lunga (3 step): avvia e lancia subito Step 1."""
        
        if not self.mio:
            logger.error("Machine adapter not available")
            return
        
        if not self._extra_long_handler:
            try:
                config = ExtraLongConfig(
                    max_travel_mm=self._mode_config.machine_max_travel_mm,
                    stock_length_mm=self._mode_config.stock_length_mm
                )
                self._extra_long_handler = ExtraLongHandler(self.mio, config)
                logger.info("ExtraLongHandler initialized")
            except Exception as e:
                logger.error(f"Error creating ExtraLongHandler: {e}")
                self._show_warn(f"Errore inizializzazione: {e}", auto_hide_ms=2500)
                return
        
        try:
            success = self._extra_long_handler.start_sequence(
                target_length_mm=piece["len"],
                angle_sx=piece.get("ax", 0),
                angle_dx=piece.get("ad", 0),
            )
            
            if success and self._extra_long_handler.execute_step_1():
                self._current_mode_handler = self._extra_long_handler
                self._disable_inputs_during_movement()
                self._movement_in_progress = True
                self._ready_to_cut = False
                self._show_info("🔵 Extra Lunga: Step 1/3 - Intestatura DX", auto_hide_ms=3000)
                logger.info(f"Extra long step 1 started: {piece['len']:.0f}mm")
            else:
                self._show_warn("❌ Sequenza extra lunga non avviata", auto_hide_ms=2500)
                logger.error("Extra long sequence failed to start")
        
        except Exception as e:
            logger.error(f"Error starting extra long: {e}")
            self._show_warn(f"Errore extra lunga: {e}", auto_hide_ms=2500)

    def _should_continue_multi_step(self) -> bool:
        """True se la sequenza speciale ha ancora step da eseguire."""
        if self._current_mode == "out_of_quota" and self._out_of_quota_handler:
            return self._out_of_quota_handler.get_current_step() == 1
        if self._current_mode == "ultra_short" and self._ultra_short_handler:
            return self._ultra_short_handler.get_current_step() in (1, 2)
        if self._current_mode == "extra_long" and self._extra_long_handler:
            return self._extra_long_handler.get_current_step() in (1, 2)
        return False

    def _continue_multi_step_sequence(self):
        """Passa allo step successivo della sequenza speciale."""
        try:
            if self._current_mode == "out_of_quota" and self._out_of_quota_handler:
                if self._out_of_quota_handler.get_current_step() == 1:
                    if self._out_of_quota_handler.execute_step_2():
                        self._movement_in_progress = True
                        self._show_info("🔴 Fuori Quota: Step 2/2 - Taglio Finale", auto_hide_ms=3000)
                    else:
                        self._show_warn("❌ Step 2 fuori quota fallito", auto_hide_ms=2500)
                        self._movement_in_progress = False

            elif self._current_mode == "ultra_short" and self._ultra_short_handler:
                step = self._ultra_short_handler.get_current_step()
                if step == 1:
                    if self._ultra_short_handler.execute_step_2():
                        self._movement_in_progress = True
                        self._show_info("🟡 Ultra Corta: Step 2/3 - Retrazione", auto_hide_ms=3000)
                    else:
                        self._show_warn("❌ Step 2 ultra corta fallito", auto_hide_ms=2500)
                        self._movement_in_progress = False
                elif step == 2:
                    if self._ultra_short_handler.execute_step_3():
                        self._movement_in_progress = True
                        self._show_info("🟡 Ultra Corta: Step 3/3 - Taglio Finale", auto_hide_ms=3000)
                    else:
                        self._show_warn("❌ Step 3 ultra corta fallito", auto_hide_ms=2500)
                        self._movement_in_progress = False

            elif self._current_mode == "extra_long" and self._extra_long_handler:
                step = self._extra_long_handler.get_current_step()
                if step == 1:
                    if self._extra_long_handler.execute_step_2():
                        self._movement_in_progress = True
                        self._show_info("🔵 Extra Lunga: Step 2/3 - Retrazione", auto_hide_ms=3000)
                    else:
                        self._show_warn("❌ Step 2 extra lunga fallito", auto_hide_ms=2500)
                        self._movement_in_progress = False
                elif step == 2:
                    if self._extra_long_handler.execute_step_3():
                        self._movement_in_progress = True
                        self._show_info("🔵 Extra Lunga: Step 3/3 - Taglio Finale", auto_hide_ms=3000)
                    else:
                        self._show_warn("❌ Step 3 extra lunga fallito", auto_hide_ms=2500)
                        self._movement_in_progress = False
        except Exception as e:
            logger.error(f"Errore continuazione multi-step: {e}")
            self._movement_in_progress = False
            self._show_warn(f"Errore sequenza: {e}", auto_hide_ms=2500)

    def _on_special_mode_step_complete(self, step_num: int, message: str = ""):
        """Callback opzionale degli handler (firma a 2 argomenti)."""
        self._show_info(f"✅ Step {step_num} completato", auto_hide_ms=2000)
        logger.info(f"Special mode step {step_num}: {message}")

    def _start_positioning(self):
        """DEPRECATED: Use _on_cut() instead. Kept for backward compatibility."""
        # Redirect to new method
        self._on_cut()

    def _ensure_clutch_engaged(self):
        """In Semi-auto la frizione resta sempre inserita."""
        if self.mio:
            with contextlib.suppress(Exception):
                self.mio.command_set_clutch(True)
        else:
            with contextlib.suppress(Exception):
                setattr(self.machine, "clutch_active", True)

    def _lock_morse(self):
        """Blocca morse a fine posa (testa in posizione)."""
        if self.mio:
            with contextlib.suppress(Exception):
                self.mio.command_set_morse(True, True)
        else:
            with contextlib.suppress(Exception):
                setattr(self.machine, "left_morse_locked", True)
                setattr(self.machine, "right_morse_locked", True)

    def _unlock_morse(self):
        """Sblocca morse a fine taglio."""
        if self.mio:
            with contextlib.suppress(Exception):
                self.mio.command_set_morse(False, False)
        else:
            with contextlib.suppress(Exception):
                setattr(self.machine, "left_morse_locked", False)
                setattr(self.machine, "right_morse_locked", False)

    def _toggle_brake(self):
        brk = bool(getattr(self.machine, "brake_active", False))
        if self.mio:
            if brk:
                self.mio.command_release_brake()
            else:
                self.mio.command_lock_brake()
        else:
            if hasattr(self.machine, "toggle_brake"):
                ok = self.machine.toggle_brake()
                if not ok:
                    self._show_warn("Operazione non consentita")
            else:
                try: setattr(self.machine, "brake_active", not brk)
                except Exception: pass
        self._update_buttons()

    def _on_homing(self):
        """Handle homing button click."""
        if not self.mio:
            self._show_warn("Adattatore macchina non disponibile", auto_hide_ms=2500)
            return
        
        try:
            # Note: do_homing() supports callback parameter (see MachineIO.do_homing signature)
            self.mio.do_homing(callback=self._on_homing_complete)
            self._show_info("⏳ Azzeramento in corso...", auto_hide_ms=3000)
            logger.info("Homing started from semi-auto page")
        except Exception as e:
            logger.error(f"Error starting homing: {e}")
            self._show_warn(f"Errore azzeramento: {e}", auto_hide_ms=2500)
    
    def _on_homing_complete(self, success: bool = True, msg: str = ""):
        """Callback a fine homing (carro + teste a 0°)."""
        if success:
            self.spin_sx.blockSignals(True)
            self.spin_dx.blockSignals(True)
            self.spin_sx.setValue(0.0)
            self.spin_dx.setValue(0.0)
            self.spin_sx.blockSignals(False)
            self.spin_dx.blockSignals(False)
            self._show_info("✅ Azzeramento completato (carro e teste)", auto_hide_ms=2000)
        else:
            self._show_warn(f"Homing non riuscito: {msg or 'errore'}", auto_hide_ms=2500)
        logger.info("Homing completed: success=%s msg=%s", success, msg)

    # ---------- Poll ----------
    def _start_poll(self):
        self._poll = QTimer(self)
        self._poll.setInterval(100)
        self._poll.timeout.connect(self._tick)
        self._poll.start()
        self._apply_angles()
        self._update_buttons()

    def _tick(self):
        if self.mio:
            self.mio.tick()
        try: self.status_panel.refresh()
        except Exception: pass
        try: self.heads.refresh()
        except Exception: pass

        pos = None
        if self.mio:
            pos = self.mio.get_position()
        else:
            pos = getattr(self.machine, "encoder_position", None)
            if pos is None:
                pos = getattr(self.machine, "position_current", None)
        try:
            self.lbl_target_big.setText(f"Quota: {float(pos):.1f} mm" if pos is not None else "Quota: — mm")
        except Exception:
            self.lbl_target_big.setText("Quota: — mm")
        
        # Check if movement completed and re-enable inputs
        if self._movement_in_progress:
            # Check movement status using helper method
            if not self._is_movement_active():
                # Sequenza multi-step: attendi taglio / conferma operatore (non auto-catena)
                if self._should_continue_multi_step():
                    self._on_multi_step_arrival()
                else:
                    # Posizionamento finale completato
                    try:
                        self._enable_inputs_after_movement()
                        self._ready_to_cut = True
                        self._seq_phase = None
                        self._movement_in_progress = False
                        hint = "F7 / pedale per taglio"
                        if self._current_mode in ("out_of_quota", "ultra_short", "extra_long"):
                            hint = "TAGLIO FINALE (F7 / pedale)"
                        self._show_info(f"✅ Posizionamento completato — {hint}", auto_hide_ms=3000)
                        logger.info("Movement completed, inputs re-enabled")
                    except Exception as e:
                        logger.error(f"Error re-enabling inputs after movement: {e}")
                        # Ensure UI is restored and flag is reset even if primary path fails
                        try:
                            self._restore_input_controls()
                        except Exception as fallback_err:
                            logger.error(f"Fallback UI restoration also failed: {fallback_err}")
                        finally:
                            # Always reset flag to prevent permanent lock
                            self._movement_in_progress = False

        # NOTE: Legacy intestatura system removed - now handled by mode handlers
        # if self._intest_in_progress:
        #     cur_out = self._get_dx_blade_out()
        #     if self._last_dx_blade_out is None:
        #         self._last_dx_blade_out = cur_out
        #     else:
        #         if self._last_dx_blade_out and not cur_out:
        #             QTimer.singleShot(0, self._finish_intestatura)
        #         self._last_dx_blade_out = cur_out

        # Rising edge blade_pulse → taglio (sim / reale via get_input)
        blade = False
        if self.mio:
            try:
                blade = bool(self.mio.get_input("blade_pulse"))
            except Exception:
                blade = False
        if blade and not self._blade_pulse_prev and not self._cut_sim_busy:
            if self._seq_phase == "await_proceed":
                pass  # Ignora impulsi dopo taglio intermedio
            elif self._is_movement_active() or self._movement_in_progress:
                pass
            else:
                self._cut_sim_busy = True
                self._lock_morse()
                QTimer.singleShot(220, self._complete_simulated_cut)
        self._blade_pulse_prev = blade

        # Rising edge start_pressed (ingresso reale / sim) → come pulsante START
        start_pressed = False
        if self.mio:
            try:
                start_pressed = bool(self.mio.get_input("start_pressed"))
            except Exception:
                start_pressed = False
        if start_pressed and not self._start_prev:
            if self._seq_phase in ("await_proceed", "await_cut") or not (
                self._is_movement_active() or self._movement_in_progress
            ):
                self._on_cut()
        self._start_prev = start_pressed

        rem = max(0, int(self._count_target) - int(self._count_done))
        self.lbl_remaining.setText(f"Rimanenti: {rem}")
        self.lbl_counted.setText(f"Contati: {int(self._count_done)}")

        self._update_buttons()
        self._update_mode_label()

    def _is_movement_active(self) -> bool:
        """
        Check if machine is currently moving.
        Uses machine_adapter if available, otherwise falls back to raw machine.
        """
        if self.mio:
            return self.mio.is_positioning_active()
        return bool(getattr(self.machine, "positioning_active", False))
    
    def _update_buttons(self):
        homed = bool(getattr(self.machine, "machine_homed", False))
        emg = bool(getattr(self.machine, "emergency_active", False))
        mov = self._is_movement_active() or self._movement_in_progress
        try:
            # In await_proceed START resta abilitato per proseguire
            can_start = homed and not emg and (not mov or self._seq_phase == "await_proceed")
            if self._seq_phase == "await_cut":
                can_start = homed and not emg and not mov  # avvisa se premuto senza taglio
            self.btn_start.setEnabled(can_start)
            if self._seq_phase == "await_proceed":
                self.btn_start.setText("PROSEGUI")
            else:
                self.btn_start.setText("START")
        except Exception:
            pass
        
        brk = bool(getattr(self.machine, "brake_active", False))
        try:
            self.btn_brake.setEnabled(homed and not emg and not mov)
            self.btn_brake.setText("SBLOCCA" if brk else "BLOCCA")
        except Exception:
            pass
    
    def _disable_inputs_during_movement(self):
        """Disable UI inputs while movement is in progress."""
        try:
            self.ext_len.setEnabled(False)
        except Exception as e:
            logger.debug(f"Could not disable ext_len: {e}")
        try:
            self.spin_sx.setEnabled(False)
        except Exception as e:
            logger.debug(f"Could not disable spin_sx: {e}")
        try:
            self.btn_sx_go.setEnabled(False)
        except Exception as e:
            logger.debug(f"Could not disable btn_sx_go: {e}")
        try:
            self.spin_dx.setEnabled(False)
        except Exception as e:
            logger.debug(f"Could not disable spin_dx: {e}")
        try:
            self.btn_dx_go.setEnabled(False)
        except Exception as e:
            logger.debug(f"Could not disable btn_dx_go: {e}")
        try:
            self.thickness.setEnabled(False)
        except Exception as e:
            logger.debug(f"Could not disable thickness: {e}")
        try:
            self.cb_profilo.setEnabled(False)
        except Exception as e:
            logger.debug(f"Could not disable cb_profilo: {e}")
        logger.debug("UI inputs disabled during movement")
    
    def _restore_input_controls(self):
        """Restore UI input controls to enabled state. Used for cleanup."""
        try:
            self.ext_len.setEnabled(True)
        except Exception as e:
            logger.debug(f"Could not enable ext_len: {e}")
        try:
            self.spin_sx.setEnabled(True)
        except Exception as e:
            logger.debug(f"Could not enable spin_sx: {e}")
        try:
            self.btn_sx_go.setEnabled(True)
        except Exception as e:
            logger.debug(f"Could not enable btn_sx_go: {e}")
        try:
            self.spin_dx.setEnabled(True)
        except Exception as e:
            logger.debug(f"Could not enable spin_dx: {e}")
        try:
            self.btn_dx_go.setEnabled(True)
        except Exception as e:
            logger.debug(f"Could not enable btn_dx_go: {e}")
        try:
            self.thickness.setEnabled(True)
        except Exception as e:
            logger.debug(f"Could not enable thickness: {e}")
        try:
            self.cb_profilo.setEnabled(True)
        except Exception as e:
            logger.debug(f"Could not enable cb_profilo: {e}")
    
    def _enable_inputs_after_movement(self):
        """Riabilita i comandi e blocca freno + morse a fine posizionamento."""
        self._restore_input_controls()
        self._movement_in_progress = False
        try:
            if self.mio:
                self.mio.command_lock_brake()
            elif hasattr(self.machine, "command_lock_brake"):
                self.machine.command_lock_brake()
            else:
                setattr(self.machine, "brake_active", True)
        except Exception as e:
            logger.error(f"Errore blocco freno a fine posa: {e}")
        self._lock_morse()
        logger.debug("UI inputs re-enabled after movement")

    # ---------- Simulazioni tastiera ----------
    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_F5:
            # Simula uscita lama DX
            self._dx_blade_out_sim = True
            if self.mio:
                self.mio.command_sim_dx_blade_out(True)
            setattr(self.machine, "dx_blade_out", True)
            self._show_info("Uscita lama DX: ATTIVA (simulazione F5)")
            event.accept(); return
        if event.key() in (Qt.Key_F6, Qt.Key_K):
            self._increment_counter_if_enabled()
            event.accept(); return
        if event.key() == Qt.Key_F7:
            self._simulate_cut()
            event.accept(); return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_F5:
            if self._dx_blade_out_sim:
                self._dx_blade_out_sim = False
                if self.mio:
                    self.mio.command_sim_dx_blade_out(False)
                setattr(self.machine, "dx_blade_out", False)
                self._show_info("Uscita lama DX: CHIUSA (simulazione F5)", auto_hide_ms=1200)
                # Legacy intestatura system removed - now handled by mode handlers
                # if self._intest_in_progress:
                #     QTimer.singleShot(0, self._finish_intestatura)
            event.accept(); return
        super().keyReleaseEvent(event)

    # --- lifecycle hook ---
    def on_show(self):
        if hasattr(self.machine, "set_active_mode"):
            try: self.machine.set_active_mode("semi")
            except Exception: pass
        self._ensure_clutch_engaged()
        if self.mio and hasattr(self.mio, "set_mode_context"):
            with contextlib.suppress(Exception):
                self.mio.set_mode_context("semi")
        # Eredita inclinazioni teste dalla macchina (es. da Automatico)
        self._inherit_head_angles_from_machine()
        # Allinea contapezzi UI ↔ stato locale
        try:
            self._count_target = int(self.spin_target.value())
        except Exception:
            pass
        self._refresh_counter_labels()
        self.refresh_profiles_external(select=self.cb_profilo.currentText().strip())

    def _inherit_head_angles_from_machine(self):
        """
        Allinea spin SX/DX allo stato reale/comandato delle teste.
        Utile passando da Automatico a Semi (es. entrambe a 45°).
        """
        sx = None
        dx = None
        # Preferisci angoli misurati se disponibili
        for src_sx, src_dx in (
            ("measured_left_head_angle", "measured_right_head_angle"),
            ("left_head_angle", "right_head_angle"),
        ):
            try:
                v_sx = getattr(self.machine, src_sx, None)
                v_dx = getattr(self.machine, src_dx, None)
                if v_sx is not None and v_dx is not None:
                    sx = float(v_sx)
                    dx = float(v_dx)
                    break
            except Exception:
                continue
        if sx is None and self.mio:
            try:
                st = self.mio.get_state() if hasattr(self.mio, "get_state") else {}
                if isinstance(st, dict):
                    if st.get("measured_left_head_angle") is not None:
                        sx = float(st["measured_left_head_angle"])
                        dx = float(st.get("measured_right_head_angle", 0.0))
                    elif st.get("left_head_angle") is not None:
                        sx = float(st["left_head_angle"])
                        dx = float(st.get("right_head_angle", 0.0))
            except Exception:
                pass
        if sx is None:
            return
        # Normalizza 90°→0° come nel resto dell'app
        sx = float(normalize_cut_tilt_deg(sx))
        dx = float(normalize_cut_tilt_deg(dx if dx is not None else 0.0))
        sx = max(0.0, min(45.0, sx))
        dx = max(0.0, min(45.0, dx))
        try:
            self.spin_sx.blockSignals(True)
            self.spin_dx.blockSignals(True)
            self.spin_sx.setValue(sx)
            self.spin_dx.setValue(dx)
        finally:
            self.spin_sx.blockSignals(False)
            self.spin_dx.blockSignals(False)
        self._update_mode_label()
        logger.info("Semi: angoli ereditati SX=%.1f° DX=%.1f°", sx, dx)

    def hideEvent(self, ev):
        try:
            if self._section_popup:
                self._section_popup.close()
                self._section_popup = None
        except Exception:
            pass
        super().hideEvent(ev)
