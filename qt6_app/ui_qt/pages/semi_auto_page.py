from typing import Optional, Dict, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QSpinBox, QGridLayout, QDoubleSpinBox, QLineEdit, QComboBox,
    QSizePolicy, QCheckBox, QAbstractSpinBox, QToolButton, QStyle, QApplication,
    QMessageBox, QListWidget
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
from ui_qt.utils.settings import read_settings
import math
import logging
from datetime import datetime

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

        # Stato intestatura / FQ (keep for backward compatibility)
        self._intest_in_progress = False
        self._intest_prev_ang_dx = 0.0
        self._last_internal = None
        self._last_target = None
        self._last_dx_blade_out = None
        self._dx_blade_out_sim = False

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

        self.graph_frame = QFrame()
        self.graph_frame.setObjectName("GraphFrame")
        self.graph_frame.setStyleSheet("QFrame#GraphFrame { border: 1px solid #3b4b5a; border-radius: 8px; }")
        self.graph_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        graph_layout = QVBoxLayout(self.graph_frame)
        graph_layout.setContentsMargins(0, 0, 0, 0)
        graph_layout.setSpacing(0)

        self.heads = HeadsView(self.machine, self.graph_frame)
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
        self.spin_sx.valueChanged.connect(self._apply_angles)
        self.spin_sx.lineEdit().textEdited.connect(lambda s: self._force_decimal_point(self.spin_sx, s))
        sx_row.addWidget(self.btn_sx_45)
        sx_row.addWidget(self.btn_sx_0)
        sx_row.addWidget(self.spin_sx)
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
        self.spin_dx.valueChanged.connect(self._apply_angles)
        self.spin_dx.lineEdit().textEdited.connect(lambda s: self._force_decimal_point(self.spin_dx, s))
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
        sx = self._parse_float(self.spin_sx.text(), 0.0)
        dx = self._parse_float(self.spin_dx.text(), 0.0)
        sx = max(0.0, min(45.0, sx))
        dx = max(0.0, min(45.0, dx))
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

    def _parse_float(self, s: str, default: float = 0.0) -> float:
        try:
            return float((str(s) or "").replace(",", ".").strip())
        except Exception:
            return default

    def _recalc_displays(self):
        pass  # eventuali calcoli preview quota

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
    def _update_target_pieces(self, v: int):
        setattr(self.machine, "semi_auto_target_pieces", int(v))

    def _reset_counter(self):
        setattr(self.machine, "semi_auto_count_done", 0)

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
        
        # === 5. Notify machine context ===
        if self.mio and hasattr(self.mio, "set_mode_context"):
            try:
                self.mio.set_mode_context(
                    "SEMI_AUTO",
                    piece_length_mm=length,
                    bar_length_mm=self._mode_config.stock_length_mm
                )
            except Exception as e:
                logger.error(f"Error setting mode context: {e}")
        
        # === 6. Execute for detected mode ===
        piece = {
            "len": length,
            "ax": angle_sx,
            "ad": angle_dx,
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
        """Execute out of quota mode (2-step sequence) - SHARED handler with automatico."""
        
        if not self.mio:
            logger.error("Machine adapter not available")
            return
        
        # Lazy initialize handler (shared with automatico!)
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
        
        # Start sequence
        try:
            success = self._out_of_quota_handler.start_sequence(
                target_length_mm=piece["len"],
                angle_sx=piece.get("ax", 0),
                angle_dx=piece.get("ad", 0),
                on_step_complete=self._on_special_mode_step_complete
            )
            
            if success:
                self._current_mode_handler = self._out_of_quota_handler
                self._show_info(f"🔴 Fuori Quota: Step 1/2 - Intestatura", auto_hide_ms=3000)
                logger.info(f"Out of quota sequence started: {piece['len']:.0f}mm")
            else:
                self._show_warn("❌ Sequenza fuori quota non avviata", auto_hide_ms=2500)
                logger.error("Out of quota sequence failed to start")
        
        except Exception as e:
            logger.error(f"Error starting out of quota: {e}")
            self._show_warn(f"Errore fuori quota: {e}", auto_hide_ms=2500)

    def _execute_ultra_short(self, piece: Dict[str, Any]):
        """Execute ultra short mode (3-step, inverted heads vs extra long) - NEW!"""
        
        if not self.mio:
            logger.error("Machine adapter not available")
            return
        
        # Lazy initialize handler
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
        
        # Start sequence
        try:
            success = self._ultra_short_handler.start_sequence(
                target_length_mm=piece["len"],
                angle_sx=piece.get("ax", 0),
                angle_dx=piece.get("ad", 0),
                on_step_complete=self._on_special_mode_step_complete
            )
            
            if success:
                self._current_mode_handler = self._ultra_short_handler
                self._show_info(f"🟡 Ultra Corta: Step 1/3 - Intestatura SX", auto_hide_ms=3000)
                logger.info(f"Ultra short sequence started: {piece['len']:.0f}mm")
            else:
                self._show_warn("❌ Sequenza ultra corta non avviata", auto_hide_ms=2500)
                logger.error("Ultra short sequence failed to start")
        
        except Exception as e:
            logger.error(f"Error starting ultra short: {e}")
            self._show_warn(f"Errore ultra corta: {e}", auto_hide_ms=2500)

    def _execute_extra_long(self, piece: Dict[str, Any]):
        """Execute extra long mode (3-step sequence) - NEW!"""
        
        if not self.mio:
            logger.error("Machine adapter not available")
            return
        
        # Lazy initialize handler
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
        
        # Start sequence
        try:
            success = self._extra_long_handler.start_sequence(
                target_length_mm=piece["len"],
                angle_sx=piece.get("ax", 0),
                angle_dx=piece.get("ad", 0),
                on_step_complete=self._on_special_mode_step_complete
            )
            
            if success:
                self._current_mode_handler = self._extra_long_handler
                self._show_info(f"🔵 Extra Lunga: Step 1/3 - Intestatura DX", auto_hide_ms=3000)
                logger.info(f"Extra long sequence started: {piece['len']:.0f}mm")
            else:
                self._show_warn("❌ Sequenza extra lunga non avviata", auto_hide_ms=2500)
                logger.error("Extra long sequence failed to start")
        
        except Exception as e:
            logger.error(f"Error starting extra long: {e}")
            self._show_warn(f"Errore extra lunga: {e}", auto_hide_ms=2500)

    def _on_special_mode_step_complete(self, step_num: int, success: bool, message: str):
        """Callback for special mode step completion."""
        
        if success:
            self._show_info(f"✅ Step {step_num} completato", auto_hide_ms=2000)
            logger.info(f"Special mode step {step_num} completed: {message}")
            
            # Check if sequence complete
            if self._current_mode_handler:
                try:
                    if hasattr(self._current_mode_handler, 'is_sequence_complete'):
                        if self._current_mode_handler.is_sequence_complete():
                            self._show_info("✅ Sequenza completata", auto_hide_ms=2500)
                            logger.info("Special mode sequence completed")
                            self._current_mode_handler = None
                            
                            # Increment counter if method exists (preserve existing functionality)
                            if hasattr(self, '_increment_counter_if_enabled'):
                                try:
                                    self._increment_counter_if_enabled()
                                except Exception as e:
                                    logger.error(f"Error incrementing counter: {e}")
                except Exception as e:
                    logger.error(f"Error checking sequence completion: {e}")
        else:
            self._show_warn(f"❌ Step {step_num} fallito", auto_hide_ms=2500)
            logger.error(f"Special mode step {step_num} failed: {message}")
            self._current_mode_handler = None

    def _start_positioning(self):
        """DEPRECATED: Use _on_cut() instead. Kept for backward compatibility."""
        # Redirect to new method
        self._on_cut()

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
            self.mio.do_homing(callback=self._on_homing_complete)
            self._show_info("⏳ Azzeramento in corso...", auto_hide_ms=3000)
            logger.info("Homing started from semi-auto page")
        except Exception as e:
            logger.error(f"Error starting homing: {e}")
            self._show_warn(f"Errore azzeramento: {e}", auto_hide_ms=2500)
    
    def _on_homing_complete(self):
        """Callback when homing completes."""
        self._show_info("✅ Azzeramento completato", auto_hide_ms=2000)
        logger.info("Homing completed")

    # ---------- Poll ----------
    def _start_poll(self):
        self._poll = QTimer(self)
        self._poll.setInterval(100)
        self._poll.timeout.connect(self._tick)
        self._poll.start()
        self._update_buttons()

    def _tick(self):
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
            # Check movement status: prefer machine_adapter if available, fallback to raw machine
            mov = self.mio.is_positioning_active() if self.mio else bool(getattr(self.machine, "positioning_active", False))
            if not mov:
                # Movement completed - re-enable inputs with error handling
                try:
                    self._enable_inputs_after_movement()
                    self._show_info("✅ Posizionamento completato", auto_hide_ms=2000)
                    logger.info("Movement completed, inputs re-enabled")
                except Exception as e:
                    logger.error(f"Error re-enabling inputs after movement: {e}")
                    # Force flag reset to prevent permanent lock
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

        tgt = int(getattr(self.machine, "semi_auto_target_pieces", 0))
        done = int(getattr(self.machine, "semi_auto_count_done", 0))
        rem = max(0, tgt - done)
        self.lbl_remaining.setText(f"Rimanenti: {rem}")
        self.lbl_counted.setText(f"Contati: {done}")

        self._update_buttons()

        if self.mio:
            self.mio.tick()

    def _update_buttons(self):
        homed = bool(getattr(self.machine, "machine_homed", False))
        emg = bool(getattr(self.machine, "emergency_active", False))
        mov = self.mio.is_positioning_active() if self.mio else bool(getattr(self.machine, "positioning_active", False))
        try:
            self.btn_start.setEnabled(homed and not emg and not mov)
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
            self.spin_sx.setEnabled(False)
            self.spin_dx.setEnabled(False)
            self.thickness.setEnabled(False)
            self.cb_profilo.setEnabled(False)
            logger.debug("UI inputs disabled during movement")
        except Exception as e:
            logger.error(f"Error disabling inputs: {e}")
    
    def _enable_inputs_after_movement(self):
        """Re-enable UI inputs after movement completes."""
        try:
            self.ext_len.setEnabled(True)
            self.spin_sx.setEnabled(True)
            self.spin_dx.setEnabled(True)
            self.thickness.setEnabled(True)
            self.cb_profilo.setEnabled(True)
            self._movement_in_progress = False
            logger.debug("UI inputs re-enabled after movement")
        except Exception as e:
            logger.error(f"Error enabling inputs: {e}")

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
            done = int(getattr(self.machine, "semi_auto_count_done", 0))
            setattr(self.machine, "semi_auto_count_done", done + 1)
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
        self.refresh_profiles_external(select=self.cb_profilo.currentText().strip())

    def hideEvent(self, ev):
        try:
            if self._section_popup:
                self._section_popup.close()
                self._section_popup = None
        except Exception:
            pass
        super().hideEvent(ev)
