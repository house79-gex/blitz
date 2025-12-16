from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple
from collections import defaultdict
import time, contextlib, logging
from math import tan, radians

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QAbstractItemView, QSizePolicy,
    QDialog, QFormLayout, QLineEdit, QComboBox, QDialogButtonBox, QCheckBox,
    QToolTip
)
from PySide6.QtGui import (
    QKeySequence, QShortcut, QBrush, QColor, QFont, QKeyEvent, QCursor
)

from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel
from ui_qt.logic.sequencer import Sequencer
from ui_qt.services.orders_store import OrdersStore
from ui_qt.dialogs.orders_manager_qt import OrdersManagerDialog
from ui_qt.dialogs.optimization_run_qt import OptimizationRunDialog

from ui_qt.logic.refiner import (
    pack_bars_knapsack_ilp,
    refine_tail_ilp,
    bar_used_length,
    residuals,
    joint_consumption
)

from ui_qt.services.profiles_store import ProfilesStore

try:
    from ui_qt.utils.settings import read_settings, write_settings
except Exception:
    def read_settings() -> Dict[str, Any]: return {}
    def write_settings(_d: Dict[str, Any]) -> None: pass

try:
    from ui_qt.utils.label_templates_store import resolve_templates
except Exception:
    def resolve_templates(_p: str, _e: Optional[str] = None) -> List[Dict[str, Any]]:
        return [{
            "name": "DEFAULT",
            "paper": "DK-11201",
            "rotate": 0,
            "font_size": 32,
            "cut": True,
            "lines": [
                "{profile}",
                "{element}",
                "L={length_mm:.2f} AX={ang_sx:.1f} AD={ang_dx:.1f}",
                "SEQ:{seq_id}"
            ]
        }]

logger = logging.getLogger("automatico_page")

try:
    POL_EXP = QSizePolicy.Policy.Expanding
except AttributeError:
    POL_EXP = QSizePolicy.Expanding

PANEL_W = 420
DEBUG_LOG = False  # metti True per log transizioni

STATE_IDLE = "idle"
STATE_ARMING = "arming"
STATE_MOVING = "moving"
STATE_READY = "ready_to_cut"
STATE_WAIT_BRAKE = "await_brake_release"

# ---- Dialog configurazione ottimizzazione ----
class OptimizationConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurazione ottimizzazione")
        cfg = read_settings()
        stock        = str(cfg.get("opt_stock_mm", 6500.0))
        stock_use    = str(cfg.get("opt_stock_usable_mm", 0.0))
        kerf         = str(cfg.get("opt_kerf_mm", 3.0))
        ripasso      = str(cfg.get("opt_ripasso_mm", 0.0))
        solver       = str(cfg.get("opt_solver", "ILP_KNAP")).upper()
        tlimit       = str(cfg.get("opt_time_limit_s", 15))
        tail_b       = str(cfg.get("opt_refine_tail_bars", 6))
        tail_t       = str(cfg.get("opt_refine_time_s", 25))
        max_ang      = str(cfg.get("opt_kerf_max_angle_deg", 60.0))
        max_factor   = str(cfg.get("opt_kerf_max_factor", 2.0))
        cons_ang     = str(cfg.get("opt_knap_conservative_angle_deg", 45.0))
        reversible   = bool(cfg.get("opt_current_profile_reversible", False))
        thickness    = str(cfg.get("opt_current_profile_thickness_mm", 0.0))
        angle_tol    = str(cfg.get("opt_reversible_angle_tol_deg", 0.5))
        warn_over    = str(cfg.get("opt_warn_overflow_mm", 0.5))
        auto_cont    = bool(cfg.get("opt_auto_continue_enabled", False))
        auto_across  = bool(cfg.get("opt_auto_continue_across_bars", False))
        strict_seq   = bool(cfg.get("opt_strict_bar_sequence", True))
        tail_enabled = bool(cfg.get("opt_enable_tail_refine", True))
        allow_skip   = bool(cfg.get("opt_allow_skip_cut", False))

        form = QFormLayout(self)
        def add(lbl, w): form.addRow(lbl, w); return w
        self.ed_stock      = add("Stock nominale (mm):", QLineEdit(stock))
        self.ed_stock_use  = add("Stock max utilizzabile (mm):", QLineEdit(stock_use))
        self.ed_kerf       = add("Kerf base (mm):", QLineEdit(kerf))
        self.ed_ripasso    = add("Ripasso (mm):", QLineEdit(ripasso))
        self.cmb_solver    = QComboBox(); self.cmb_solver.addItems(["ILP_KNAP","ILP","BFD"])
        self.cmb_solver.setCurrentText("ILP_KNAP" if solver not in ("ILP","BFD") else solver); add("Solver:", self.cmb_solver)
        self.ed_time       = add("Time limit solver (s):", QLineEdit(tlimit))
        self.ed_tail_b     = add("Refine ultime barre (N):", QLineEdit(tail_b))
        self.ed_tail_t     = add("Refine time (s):", QLineEdit(tail_t))
        self.ed_max_ang    = add("Kerf max angolo (°):", QLineEdit(max_ang))
        self.ed_max_factor = add("Kerf max fattore:", QLineEdit(max_factor))
        self.ed_cons_ang   = add("Angolo conservativo knapsack (°):", QLineEdit(cons_ang))
        self.chk_reversible= QCheckBox("Profilo reversibile"); self.chk_reversible.setChecked(reversible); form.addRow(self.chk_reversible)
        self.ed_thickness  = add("Spessore profilo (mm):", QLineEdit(thickness))
        self.ed_angle_tol  = add("Toll. angolo reversibile (°):", QLineEdit(angle_tol))
        self.ed_warn_over  = add("Warn residuo soglia (mm):", QLineEdit(warn_over))
        self.chk_auto_cont = QCheckBox("Auto-continue pezzi identici"); self.chk_auto_cont.setChecked(auto_cont); form.addRow(self.chk_auto_cont)
        self.chk_auto_across=QCheckBox("Auto-continue anche tra barre"); self.chk_auto_across.setChecked(auto_across); form.addRow(self.chk_auto_across)
        self.chk_strict_seq= QCheckBox("Sequenza stretta (ordine barre)"); self.chk_strict_seq.setChecked(strict_seq); form.addRow(self.chk_strict_seq)
        self.chk_tail_refine=QCheckBox("Usa refine tail"); self.chk_tail_refine.setChecked(tail_enabled); form.addRow(self.chk_tail_refine)
        self.chk_allow_skip=QCheckBox("Consenti avanzare senza taglio (TEST)"); self.chk_allow_skip.setChecked(allow_skip); form.addRow(self.chk_allow_skip)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        btns.accepted.connect(self._save_and_close); btns.rejected.connect(self.reject)
        form.addRow(btns)
        self.resize(560,800)

    def _save_and_close(self):
        def f(t,d):
            try: return float((t or "").replace(",", "."))
            except Exception: return d
        def i(t,d):
            try: return int(float((t or "").replace(",", ".")))
            except Exception: return d
        data = {
            "opt_stock_mm": f(self.ed_stock.text(),6500.0),
            "opt_stock_usable_mm": f(self.ed_stock_use.text(),0.0),
            "opt_kerf_mm": f(self.ed_kerf.text(),3.0),
            "opt_ripasso_mm": f(self.ed_ripasso.text(),0.0),
            "opt_solver": self.cmb_solver.currentText().upper(),
            "opt_time_limit_s": i(self.ed_time.text(),15),
            "opt_refine_tail_bars": i(self.ed_tail_b.text(),6),
            "opt_refine_time_s": i(self.ed_tail_t.text(),25),
            "opt_kerf_max_angle_deg": f(self.ed_max_ang.text(),60.0),
            "opt_kerf_max_factor": f(self.ed_max_factor.text(),2.0),
            "opt_knap_conservative_angle_deg": f(self.ed_cons_ang.text(),45.0),
            "opt_current_profile_reversible": bool(self.chk_reversible.isChecked()),
            "opt_reversible_angle_tol_deg": f(self.ed_angle_tol.text(),0.5),
            "opt_warn_overflow_mm": f(self.ed_warn_over.text(),0.5),
            "opt_auto_continue_enabled": bool(self.chk_auto_cont.isChecked()),
            "opt_auto_continue_across_bars": bool(self.chk_auto_across.isChecked()),
            "opt_strict_bar_sequence": bool(self.chk_strict_seq.isChecked()),
            "opt_enable_tail_refine": bool(self.chk_tail_refine.isChecked()),
            "opt_allow_skip_cut": bool(self.chk_allow_skip.isChecked())
        }
        write_settings(data)
        self.accept()


# ---- Dialog taglio manuale singolo ----
class ManualCutDialog(QDialog):
    def __init__(self, parent=None, preset: Optional[Dict[str,Any]] = None):
        super().__init__(parent)
        self.setWindowTitle("Taglio manuale singolo")
        form = QFormLayout(self)
        self.ed_profile = QLineEdit(str(preset.get("profile","")) if preset else "")
        self.ed_element = QLineEdit(str(preset.get("element","")) if preset else "")
        self.ed_len = QLineEdit(f"{preset.get('length_mm', preset.get('len',0.0)):.2f}" if preset else "0.00")
        self.ed_ax = QLineEdit(f"{preset.get('ang_sx', preset.get('ax',0.0)):.1f}" if preset else "0.0")
        self.ed_ad = QLineEdit(f"{preset.get('ang_dx', preset.get('ad',0.0)):.1f}" if preset else "0.0")
        form.addRow("Profilo:", self.ed_profile)
        form.addRow("Elemento:", self.ed_element)
        form.addRow("Lunghezza (mm):", self.ed_len)
        form.addRow("Angolo SX (°):", self.ed_ax)
        form.addRow("Angolo DX (°):", self.ed_ad)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        form.addRow(btns)
        self.resize(380, 260)

    def get_data(self) -> Dict[str,Any]:
        def f(txt, d):
            try: return float((txt or "").replace(",", "."))
            except Exception: return d
        return {
            "profile": self.ed_profile.text().strip(),
            "element": self.ed_element.text().strip(),
            "len": f(self.ed_len.text(), 0.0),
            "ax": f(self.ed_ax.text(), 0.0),
            "ad": f(self.ed_ad.text(), 0.0)
        }


# ---- Stampa etichette ----
class LabelPrinter:
    def __init__(self, settings: Dict[str, Any], toast_cb=None):
        self.toast = toast_cb
        self.enabled = bool(settings.get("label_enabled", False))
        self.model = str(settings.get("label_printer_model", "QL-800"))
        self.backend = str(settings.get("label_backend", "wspool"))
        self.printer = str(settings.get("label_printer_name", ""))
        self.paper = str(settings.get("label_paper", "DK-11201"))
        self.rotate = int(settings.get("label_rotate", 0))
        self.preview_if_no_printer = True
        self._ql = None; self._pil = None
        with contextlib.suppress(Exception):
            from brother_ql.raster import BrotherQLRaster
            from brother_ql.backends import backend_factory
            from PIL import Image, ImageDraw, ImageFont
            self._ql={"BrotherQLRaster":BrotherQLRaster,"backend_factory":backend_factory}
            self._pil={"Image":Image,"ImageDraw":ImageDraw,"ImageFont":ImageFont}

    def update_settings(self,s:Dict[str,Any]):
        self.enabled=bool(s.get("label_enabled",False))
        self.model=str(s.get("label_printer_model","QL-800"))
        self.backend=str(s.get("label_backend","wspool"))
        self.printer=str(s.get("label_printer_name",""))
        self.paper=str(s.get("label_paper","DK-11201"))
        self.rotate=int(s.get("label_rotate",0))
        self.preview_if_no_printer=True

    def print_label(self, lines: List[str], paper: Optional[str]=None,
                    rotate: Optional[int]=None, font_size: Optional[int]=None,
                    cut: Optional[bool]=None) -> bool:
        if self._pil is None:
            if self.toast: self.toast("Pillow non disponibile per etichette.","warn")
            return False
        try:
            Image=self._pil["Image"]; ImageDraw=self._pil["ImageDraw"]; ImageFont=self._pil["ImageFont"]
            use_paper=paper or self.paper; use_rotate=int(rotate if rotate is not None else self.rotate)
            paper_map={"DK-11201":(29.0,90.0),"DK-11202":(62.0,100.0),"DK-11209":(62.0,29.0),"DK-22205":(62.0,100.0)}
            w_mm,h_mm=paper_map.get(use_paper,(29.0,90.0))
            W=int(round((w_mm/25.4)*300)); H=int(round((h_mm/25.4)*300))
            img=Image.new("1",(W,H),1); draw=ImageDraw.Draw(img)
            fs=int(font_size or 32)
            with contextlib.suppress(Exception): font=ImageFont.truetype("arial.ttf",fs)
            if 'font' not in locals(): font=ImageFont.load_default()
            y=8
            for line in lines:
                draw.text((8,y),str(line),fill=0,font=font); y+=int(fs*1.2)
            if use_rotate in (90,180,270):
                with contextlib.suppress(Exception): img=img.rotate(use_rotate,expand=True)
            if (not self.enabled) or (self._ql is None) or (not self.printer):
                if self.preview_if_no_printer and self.toast:
                    self.toast("Etichetta simulata (stampante non configurata).","info")
                return True
            from brother_ql.conversion import convert
            BrotherQLRaster=self._ql["BrotherQLRaster"]; backend_factory=self._ql["backend_factory"]
            qlr=BrotherQLRaster(self.model); qlr.exception_on_warning=False
            instr=convert(qlr=qlr, images=[img], label=use_paper, threshold=70, dither=False,
                          compress=True, red=False, rotate='0', dpi_600=False, hq=True,
                          cut=bool(cut if cut is not None else True))
            backend=backend_factory(self.backend); be=backend(printer_identifier=self.printer)
            be.write(instr)
            with contextlib.suppress(Exception):
                be.dispose()
            return True
        except Exception as e:
            if self.toast: self.toast(f"Errore stampa: {e}","err")
            return False


class AutomaticoPage(QWidget):
    activePieceChanged = Signal(dict)
    pieceCut = Signal(dict)

    def __init__(self, appwin):
        super().__init__()
        self.appwin=appwin
        self.machine=appwin.machine            # raw (per StatusPanel)
        self.mio = getattr(appwin, "machine_adapter", None)  # adapter refactor

        self.seq=Sequencer(appwin)
        self.seq.step_started.connect(self._on_step_started)
        self.seq.step_finished.connect(self._on_step_finished)
        self.seq.finished.connect(self._on_seq_done)

        def _toast_impl(msg:str, level:str="info"):
            if hasattr(self.appwin, "toast"):
                try:
                    self.appwin.toast.show(msg, level, 2500); return
                except Exception: pass
            getattr(logger, "info" if level not in ("err","warn") else ("warning" if level=="warn" else "error"))(msg)
        self._toast = _toast_impl

        # UI refs
        self.tbl_cut=None; self.lbl_target=None; self.lbl_done=None; self.lbl_remaining=None
        self.status=None; self.btn_start_row=None; self.viewer_frame=None; self.lbl_quota_card=None
        self.banner=None; self.lbl_cycle_state=None

        # Data / Piano
        self._orders=OrdersStore()
        self._profiles_store=ProfilesStore()
        self._current_profile_thickness=0.0

        self._mode="idle"
        self._plan_profile=""
        self._bars=[]
        self._seq_plan=[]
        self._seq_pos=-1
        self._opt_dialog=None
        self._sig_total_counts={}
        self._cur_sig=None
        self._active_row=None

        # Stato dinamico
        self._brake_locked=False
        self._blade_prev=False
        self._start_prev=False

        self._state=STATE_IDLE
        self._pending_active_piece=None
        self._piece_tagliato=False

        # Config
        cfg=read_settings()
        self._kerf_max_angle_deg=float(cfg.get("opt_kerf_max_angle_deg",60.0))
        self._kerf_max_factor=float(cfg.get("opt_kerf_max_factor",2.0))
        self._knap_cons_angle_deg=float(cfg.get("opt_knap_conservative_angle_deg",45.0))
        self._ripasso_mm=float(cfg.get("opt_ripasso_mm",0.0))
        self._warn_overflow_mm=float(cfg.get("opt_warn_overflow_mm",0.5))
        self._auto_continue_enabled=bool(cfg.get("opt_auto_continue_enabled",False))
        self._auto_continue_across_bars=bool(cfg.get("opt_auto_continue_across_bars",False))
        self._strict_bar_sequence=bool(cfg.get("opt_strict_bar_sequence",True))
        self._tail_refine_enabled=bool(cfg.get("opt_enable_tail_refine",True))
        self._allow_skip_cut=bool(cfg.get("opt_allow_skip_cut",False))
        self._extshort_safe_mm=float(cfg.get("auto_extshort_safe_pos_mm",400.0)) if "auto_extshort_safe_pos_mm" in cfg else 400.0
        self._kerf_base_mm=float(cfg.get("opt_kerf_mm",3.0)) if "opt_kerf_mm" in cfg else 3.0
        self._after_cut_pause_ms=int(float(cfg.get("auto_after_cut_pause_ms",300))) if "auto_after_cut_pause_ms" in cfg else 300

        self._label_enabled=bool(cfg.get("label_enabled",False))
        self._label_printer=LabelPrinter(cfg, toast_cb=self._toast)

        self._manual_current_piece=None

        self._poll=None
        self._build()

    # ---- UI build ----
    def _build(self):
        root=QVBoxLayout(self); root.setContentsMargins(8,8,8,8); root.setSpacing(6)
        root.addWidget(Header(self.appwin,"AUTOMATICO",mode="default",
                              on_home=self._nav_home,on_reset=self._reset_and_home))
        self.banner=QLabel(""); self.banner.setVisible(False); self.banner.setAlignment(Qt.AlignCenter)
        self.banner.setStyleSheet("QLabel { background:#ffe7ba; color:#1b1b1b; font-size:18px; font-weight:800; padding:8px 12px; border:1px solid #c49a28; border-radius:6px; }")
        root.addWidget(self.banner)

        top=QHBoxLayout()
        btn_import=QPushButton("Importa…"); btn_import.clicked.connect(self._import_cutlist); top.addWidget(btn_import)
        btn_manual=QPushButton("Manuale"); btn_manual.clicked.connect(self._enter_manual_mode); top.addWidget(btn_manual)
        btn_opt=QPushButton("Ottimizza"); btn_opt.clicked.connect(self._on_optimize_clicked); top.addWidget(btn_opt)
        btn_cfg=QPushButton("Config. ottimizzazione…"); btn_cfg.clicked.connect(self._open_opt_config); top.addWidget(btn_cfg)
        top.addStretch(1); root.addLayout(top)

        body=QHBoxLayout(); body.setSpacing(8); root.addLayout(body,1)

        # Sinistra
        left=QFrame(); left.setSizePolicy(POL_EXP,POL_EXP)
        ll=QVBoxLayout(left); ll.setContentsMargins(0,0,0,0); ll.setSpacing(8)
        viewer=QFrame(); viewer.setStyleSheet("QFrame { border:1px solid #3b4b5a; border-radius:6px; }")
        self.viewer_frame=viewer
        vf=QVBoxLayout(viewer); vf.setContentsMargins(6,6,6,6); vf.setSpacing(6)

        self.tbl_cut=QTableWidget(0,8)
        self.tbl_cut.setHorizontalHeaderLabels(["SeqID","Profilo","Elemento","Lunghezza (mm)","Ang SX","Ang DX","Q.tà","Note"])
        hdr=self.tbl_cut.horizontalHeader()
        for i,m in enumerate([QHeaderView.ResizeToContents,QHeaderView.Stretch,QHeaderView.Stretch,
                              QHeaderView.ResizeToContents,QHeaderView.ResizeToContents,QHeaderView.ResizeToContents,
                              QHeaderView.ResizeToContents,QHeaderView.Stretch]):
            hdr.setSectionResizeMode(i,m)
        self.tbl_cut.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_cut.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_cut.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl_cut.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.tbl_cut.cellEntered.connect(self._on_cell_entered)
        self.tbl_cut.currentCellChanged.connect(self._on_current_cell_changed)
        vf.addWidget(self.tbl_cut,1)
        ll.addWidget(viewer,1)

        start_row=QHBoxLayout(); start_row.addStretch(1)
        self.btn_start_row=QPushButton("Start"); self.btn_start_row.setMinimumHeight(56)
        self.btn_start_row.setStyleSheet(
            "QPushButton { background:#2ecc71; color:white; font-weight:900; font-size:20px; padding:12px 32px; border-radius:10px; } "
            "QPushButton:hover { background:#27ae60; } QPushButton:pressed { background:#239b56; }")
        self.btn_start_row.clicked.connect(self._handle_start_trigger)
        start_row.addWidget(self.btn_start_row); start_row.addSpacing(12)
        quota_title=QLabel("Quota"); quota_title.setAlignment(Qt.AlignCenter); quota_title.setMinimumHeight(56)
        quota_title.setStyleSheet("QLabel { background:#f0f8ff; color:#2c3e50; font-weight:900; font-size:20px; padding:12px 24px; border:2px solid #3498db; border-radius:10px; }")
        start_row.addWidget(quota_title)
        self.lbl_quota_card=QLabel("— mm"); self.lbl_quota_card.setAlignment(Qt.AlignCenter)
        self.lbl_quota_card.setMinimumHeight(56); self.lbl_quota_card.setMinimumWidth(320)
        self.lbl_quota_card.setStyleSheet(
            "QLabel { background:#e8f4ff; color:#1f2d3d; font-weight:900; font-size:28px; padding:12px 40px; border:2px solid #3498db; border-radius:10px; }")
        start_row.addWidget(self.lbl_quota_card)
        btn_cut_sim=QPushButton("Taglio (sim)"); btn_cut_sim.clicked.connect(self._simulate_cut_key)
        btn_cut_sim.setStyleSheet("QPushButton { background:#e67e22; color:#fff; font-weight:700; padding:8px 14px; border-radius:8px; } QPushButton:hover { background:#d35400; }")
        start_row.addWidget(btn_cut_sim)
        btn_brake_rel=QPushButton("Sblocca Freno"); btn_brake_rel.clicked.connect(lambda: self._unlock_brake(False))
        btn_brake_rel.setStyleSheet("QPushButton { background:#bdc3c7; color:#2c3e50; font-weight:700; padding:8px 14px; border-radius:8px; } QPushButton:hover { background:#95a5a6; }")
        start_row.addWidget(btn_brake_rel)
        start_row.addStretch(1)
        ll.addLayout(start_row)
        body.addWidget(left,1)

        # Destra
        right=QFrame(); right.setFixedWidth(PANEL_W)
        rl=QVBoxLayout(right); rl.setContentsMargins(0,0,0,0); rl.setSpacing(8)

        cnt_box=QFrame(); cnt_box.setStyleSheet("QFrame { border:1px solid #3b4b5a; border-radius:6px; }")
        cnl=QVBoxLayout(cnt_box); cnl.setContentsMargins(12,12,12,12)
        cnl.addWidget(QLabel("NUMERO PEZZI"))
        big="font-size:24px; font-weight:800;"
        r1=QHBoxLayout(); r1.addWidget(QLabel("Target:")); self.lbl_target=QLabel("0"); self.lbl_target.setStyleSheet(big); r1.addWidget(self.lbl_target); r1.addStretch(1)
        r2=QHBoxLayout(); r2.addWidget(QLabel("Tagliati:")); self.lbl_done=QLabel("0"); self.lbl_done.setStyleSheet(big+"color:#2ecc71;"); r2.addWidget(self.lbl_done); r2.addStretch(1)
        r3=QHBoxLayout(); r3.addWidget(QLabel("Rimanenti:")); self.lbl_remaining=QLabel("-"); self.lbl_remaining.setStyleSheet(big+"color:#f39c12;"); r3.addWidget(self.lbl_remaining); r3.addStretch(1)
        cnl.addLayout(r1); cnl.addLayout(r2); cnl.addLayout(r3)
        rl.addWidget(cnt_box,0)

        st_wrap=QFrame(); st_wrap.setStyleSheet("QFrame { border:1px solid #3b4b5a; border-radius:6px; }")
        swl=QVBoxLayout(st_wrap); swl.setContentsMargins(6,6,6,6)
        self.status=StatusPanel(self.machine,"STATO",st_wrap); swl.addWidget(self.status)
        rl.addWidget(st_wrap,0)

        cycle_box=QFrame(); cycle_box.setStyleSheet("QFrame { border:1px solid #3b4b5a; border-radius:6px; }")
        ccl=QVBoxLayout(cycle_box); ccl.setContentsMargins(10,10,10,10)
        self.lbl_cycle_state=QLabel("Stato ciclo: IDLE")
        self.lbl_cycle_state.setStyleSheet("QLabel { font-size:16px; font-weight:700; }")
        ccl.addWidget(self.lbl_cycle_state)
        ccl.addWidget(QLabel("F9: posiziona / avanza. F7: taglio.\nAvanza successivo solo dopo taglio + rilascio freno (o opt_allow_skip_cut)."))
        rl.addWidget(cycle_box,0)

        lab_box=QFrame(); lab_box.setStyleSheet("QFrame { border:1px solid #3b4b5a; border-radius:6px; }")
        lb=QVBoxLayout(lab_box); lb.setContentsMargins(10,10,10,10); lb.setSpacing(6)
        lb.addWidget(QLabel("Etichette"))
        self.chk_label=QCheckBox("Stampa etichetta dopo taglio"); self.chk_label.setChecked(self._label_enabled)
        self.chk_label.toggled.connect(self._on_label_toggle); lb.addWidget(self.chk_label)
        btn_label_test=QPushButton("Test etichetta"); btn_label_test.clicked.connect(self._test_label); lb.addWidget(btn_label_test)
        rl.addWidget(lab_box,0)

        rl.addStretch(1); body.addWidget(right,0)
        QShortcut(QKeySequence("Space"), self, activated=self._handle_start_trigger)
        QShortcut(QKeySequence("F9"), self, activated=self._handle_start_trigger)
        QShortcut(QKeySequence("F7"), self, activated=self._simulate_cut_key)

    # ---- Helpers stato / log ----
    def _update_cycle_state_label(self):
        if self.lbl_cycle_state:
            self.lbl_cycle_state.setText(f"Stato ciclo: {self._state.upper()}")

    def _log_state(self,msg:str):
        if DEBUG_LOG: logger.debug(f"[AUTO] {msg}")

    # ---- Modalità manuale ----
       def _enter_manual_mode(self):
        """
        Entra in modalità manuale.
        
        In manuale: 
        - Freno e frizione SBLOCCATI
        - Testa DX libera (trascinabile a mano)
        - Encoder legge posizione passivamente
        - NO movimento motore
        """
        if self._mode == "plan":
            self._bars. clear()
            self._seq_plan.clear()
            self._seq_pos = -1
            self._cur_sig = None
        
        self._mode = "manual"
        self._state = STATE_IDLE
        
        # CRITICO: Sblocca freno E frizione per trascinamento manuale
        if self.mio:
            self.mio.command_release_brake()
            self.mio.command_set_clutch(False)  # ✅ Testa DX libera! 
            
            # Notifica contesto:  modalità manuale
            if hasattr(self.mio, "set_mode_context"):
                self.mio.set_mode_context("manual")
        
        self._update_counters_ui()
        self._toast("MANUALE:  Trascina testa DX a mano.  Encoder legge posizione.", "info")
        self._update_cycle_state_label()

    # ---- Etichette ----
    def _on_label_toggle(self,on:bool):
        self._label_enabled=bool(on)
        cfg=dict(read_settings()); cfg["label_enabled"]=self._label_enabled
        write_settings(cfg); self._label_printer.update_settings(cfg)

    def _test_label(self):
        piece={"seq_id":999,"profile":"DEMO","element":"Test","len":1234.5,"ax":45.0,"ad":0.0}
        self._emit_label(piece)

    def _emit_label(self,piece:Dict[str,Any]):
        if not self._label_enabled: return
        fmt={
            "profile":piece.get("profile",""),
            "element":piece.get("element",""),
            "length_mm":piece.get("len",piece.get("length",0.0)),
            "ang_sx":piece.get("ax",piece.get("ang_sx",0.0)),
            "ang_dx":piece.get("ad",piece.get("ang_dx",0.0)),
            "seq_id":piece.get("seq_id",0),
            "timestamp":time.strftime("%H:%M:%S")
        }
        templates=resolve_templates(piece.get("profile",""),piece.get("element",""))
        for tmpl in templates:
            lines=[]
            for raw in tmpl.get("lines",[]):
                try: lines.append(str(raw).format(**fmt))
                except Exception: lines.append(str(raw))
            self._label_printer.print_label(lines,
                                            paper=tmpl.get("paper"),
                                            rotate=int(tmpl.get("rotate",0)),
                                            font_size=int(tmpl.get("font_size",32)),
                                            cut=bool(tmpl.get("cut",True)))

    # ---- Banner ----
    def _show_banner(self,msg:str,level:str="info"):
        styles={"info":"background:#ffe7ba; color:#1b1b1b; border:1px solid #c49a28;",
                "ok":"background:#d4efdf; color:#145a32; border:1px solid #27ae60;",
                "warn":"background:#fdecea; color:#7b241c; border:1px solid #c0392b;",
                "err":"background:#fceaea; color:#922b21; border:1px solid #e74c3c;"}
        st=styles.get(level,styles["info"])
        self.banner.setText(msg)
        self.banner.setStyleSheet(f"QLabel {{{st} font-size:18px; font-weight:800; padding:8px 12px; border-radius:6px;}}")
        self.banner.setVisible(True)

    def _hide_banner(self):
        self.banner.setVisible(False); self.banner.setText("")

    # ---- Config ottimizzazione ----
    def _open_opt_config(self):
        dlg = OptimizationConfigDialog(self)
        if dlg.exec():
            self._toast("Configurazione aggiornata.","ok")
            cfg=read_settings()
            self._kerf_max_angle_deg=float(cfg.get("opt_kerf_max_angle_deg",60.0))
            self._kerf_max_factor=float(cfg.get("opt_kerf_max_factor",2.0))
            self._knap_cons_angle_deg=float(cfg.get("opt_knap_conservative_angle_deg",45.0))
            self._ripasso_mm=float(cfg.get("opt_ripasso_mm",0.0))
            self._warn_overflow_mm=float(cfg.get("opt_warn_overflow_mm",0.5))
            self._auto_continue_enabled=bool(cfg.get("opt_auto_continue_enabled",False))
            self._auto_continue_across_bars=bool(cfg.get("opt_auto_continue_across_bars",False))
            self._strict_bar_sequence=bool(cfg.get("opt_strict_bar_sequence",True))
            self._tail_refine_enabled=bool(cfg.get("opt_enable_tail_refine",True))
            self._allow_skip_cut=bool(cfg.get("opt_allow_skip_cut",False))

    # ---- Import cutlist ----
    def _import_cutlist(self):
        dlg=OrdersManagerDialog(self,self._orders)
        if dlg.exec() and getattr(dlg,"selected_order_id",None):
            ord_item=self._orders.get_order(int(dlg.selected_order_id))
            if not ord_item:
                QMessageBox.critical(self,"Importa","Ordine non trovato."); return
            data=ord_item.get("data") or {}
            if data.get("type")!="cutlist":
                QMessageBox.information(self,"Importa","Ordine non di tipo cutlist."); return
            cuts=data.get("cuts") or []
            if not cuts:
                QMessageBox.information(self,"Importa","Lista vuota."); return
            self._load_cutlist(cuts)

    def _header_items(self,profile:str)->List[QTableWidgetItem]:
        font=QFont(); font.setBold(True); bg=QBrush(QColor("#ecf0f1"))
        items=[]
        def mk(txt=""):
            it=QTableWidgetItem(txt); it.setFont(font); it.setBackground(bg); it.setFlags(Qt.ItemIsEnabled); return it
        items.append(mk(""))
        items.append(mk(profile or "—"))
        for _ in range(6): items.append(mk(""))
        return items

    def _load_cutlist(self,cuts:List[Dict[str,Any]]):
        self.tbl_cut.setRowCount(0)
        groups=defaultdict(list); order=[]
        for c in cuts:
            p=str(c.get("profile","")).strip()
            if p not in groups: order.append(p)
            groups[p].append(c)
        seq_counter=1; first_piece_row=None
        for prof in order:
            r=self.tbl_cut.rowCount(); self.tbl_cut.insertRow(r)
            for col,it in enumerate(self._header_items(prof)): self.tbl_cut.setItem(r,col,it)
            for c in groups[prof]:
                r=self.tbl_cut.rowCount(); self.tbl_cut.insertRow(r)
                Lmm=float(c.get("length_mm",0.0)); ax=float(c.get("ang_sx",0.0)); ad=float(c.get("ang_dx",0.0)); qty=int(c.get("qty",0))
                cells=[
                    QTableWidgetItem(str(seq_counter)),
                    QTableWidgetItem(prof),
                    QTableWidgetItem(str(c.get("element",""))),
                    QTableWidgetItem(f"{Lmm:.2f}"),
                    QTableWidgetItem(f"{ax:.1f}"),
                    QTableWidgetItem(f"{ad:.1f}"),
                    QTableWidgetItem(str(qty)),
                    QTableWidgetItem(str(c.get("note","")))
                ]
                cells[0].setData(Qt.UserRole,dict(c)); seq_counter+=1
                for it in cells: it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                for col,it in enumerate(cells): self.tbl_cut.setItem(r,col,it)
                if first_piece_row is None: first_piece_row=r
        self._mode="idle"; self._state=STATE_IDLE
        self._sig_total_counts.clear(); self._cur_sig=None
        self._seq_plan.clear(); self._seq_pos=-1
        self._active_row=None
        if first_piece_row is not None:
            self.tbl_cut.selectRow(first_piece_row); self._apply_active_row(first_piece_row)
        self._hide_banner(); self._update_counters_ui(); self._update_cycle_state_label()

    def _find_first_header_profile(self)->Optional[str]:
        for r in range(self.tbl_cut.rowCount()):
            if self._row_is_header(r):
                it=self.tbl_cut.item(r,1)
                if it: return it.text().strip()
        return None

    def _on_optimize_clicked(self):
        prof=None; r=self.tbl_cut.currentRow()
        if r is not None and r>=0 and self._row_is_header(r):
            it=self.tbl_cut.item(r,1); prof=it.text().strip() if it else None
        if not prof: prof=self._find_first_header_profile()
        if not prof:
            QMessageBox.information(self,"Ottimizza","Seleziona un profilo."); return
        if self._opt_dialog:
            with contextlib.suppress(Exception): self.activePieceChanged.disconnect(self._opt_dialog.onActivePieceChanged)
            with contextlib.suppress(Exception): self.pieceCut.disconnect(self._opt_dialog.onPieceCut)
            with contextlib.suppress(Exception): self._opt_dialog.close()
            self._opt_dialog=None
        self._optimize_profile(prof)
        if self._mode!="plan":
            QMessageBox.information(self,"Ottimizza",f"Nessun pezzo rimanente per '{prof}'."); return
        self._open_opt_dialog(prof)

    def _open_opt_dialog(self,profile:str):
        if self._mode != "plan": return
        rows=[]
        for r in range(self.tbl_cut.rowCount()):
            if self._row_is_header(r): continue
            if self.tbl_cut.item(r,1) and self.tbl_cut.item(r,1).text().strip()==profile:
                try:
                    L=float(self.tbl_cut.item(r,3).text())
                    ax=float(self.tbl_cut.item(r,4).text())
                    ad=float(self.tbl_cut.item(r,5).text())
                    q=int(self.tbl_cut.item(r,6).text())
                except Exception: continue
                if q>0: rows.append({"length_mm":round(L,2),"ang_sx":ax,"ang_dx":ad,"qty":q})
        if not rows:
            QMessageBox.information(self,"Piano","Tutte le righe per il profilo selezionato sono a Q=0."); return
        self._opt_dialog=OptimizationRunDialog(self, profile, rows, overlay_target=self.viewer_frame)
        with contextlib.suppress(Exception): self.activePieceChanged.connect(self._opt_dialog.onActivePieceChanged)
        with contextlib.suppress(Exception): self.pieceCut.connect(self._opt_dialog.onPieceCut)
        with contextlib.suppress(Exception): self._opt_dialog.startRequested.connect(self._handle_start_trigger)
        with contextlib.suppress(Exception): self._opt_dialog.simulationRequested.connect(self.simulate_cut_from_dialog)
        self._opt_dialog.finished.connect(lambda _p: setattr(self,"_opt_dialog",None))
        self._opt_dialog.show()
        self._toast("Piano grafico aperto.","info")

    def _optimize_profile(self,profile:str):
        prof=(profile or "").strip()
        if not prof: return
        pieces=[]; sig_totals=defaultdict(int)
        for r in range(self.tbl_cut.rowCount()):
            if self._row_is_header(r): continue
            if self.tbl_cut.item(r,1) and self.tbl_cut.item(r,1).text().strip()==prof:
                try:
                    L=round(float(self.tbl_cut.item(r,3).text()),2)
                    ax=float(self.tbl_cut.item(r,4).text())
                    ad=float(self.tbl_cut.item(r,5).text())
                    q=int(self.tbl_cut.item(r,6).text())
                    element=str(self.tbl_cut.item(r,2).text() or "")
                    meta=self.tbl_cut.item(r,0).data(Qt.UserRole) or {}
                except Exception: continue
                for _ in range(max(0,q)):
                    pieces.append({"len":float(L),"ax":float(ax),"ad":float(ad),
                                   "profile":prof,"element":element,"meta":dict(meta)})
                sig_totals[(prof,L,round(ax,1),round(ad,1))]+=max(0,q)
        if not pieces: return
        cfg=read_settings()
        stock_nom=float(cfg.get("opt_stock_mm",6500.0))
        stock_use=float(cfg.get("opt_stock_usable_mm",0.0))
        stock=stock_use if stock_use>0 else stock_nom
        kerf_base=float(cfg.get("opt_kerf_mm",3.0))
        solver=str(cfg.get("opt_solver","ILP_KNAP")).upper()
        per_bar_time=int(float(cfg.get("opt_time_limit_s",15)))
        tail_n=int(float(cfg.get("opt_refine_tail_bars",6)))
        tail_t=int(float(cfg.get("opt_refine_time_s",25)))
        reversible=bool(cfg.get("opt_current_profile_reversible",False))
        thickness_mm=self._get_profile_thickness(prof)
        angle_tol=float(cfg.get("opt_reversible_angle_tol_deg",0.5))
        max_angle=self._kerf_max_angle_deg; max_factor=self._kerf_max_factor

        if solver in ("ILP_KNAP","ILP"):
            bars, rem=pack_bars_knapsack_ilp(pieces=pieces,stock=stock,kerf_base=kerf_base,
                                             ripasso_mm=self._ripasso_mm, conservative_angle_deg=self._knap_cons_angle_deg,
                                             max_angle=max_angle, max_factor=max_factor,
                                             reversible=reversible, thickness_mm=thickness_mm,
                                             angle_tol=angle_tol, per_bar_time_s=per_bar_time)
            if not bars:
                bars, rem=self._pack_bfd(pieces,stock,kerf_base,reversible,thickness_mm,angle_tol,max_angle,max_factor)
        else:
            bars, rem=self._pack_bfd(pieces,stock,kerf_base,reversible,thickness_mm,angle_tol,max_angle,max_factor)

        if self._tail_refine_enabled:
            with contextlib.suppress(Exception):
                bars_ref, rem2=refine_tail_ilp(bars,stock,kerf_base,self._ripasso_mm,reversible,thickness_mm,
                                               angle_tol,tail_bars=tail_n,time_limit_s=tail_t,
                                               max_angle=max_angle,max_factor=max_factor)
                if bars_ref and len(bars_ref)==len(bars):
                    bars=bars_ref

        if not self._strict_bar_sequence:
            for b in bars:
                with contextlib.suppress(Exception):
                    b.sort(key=lambda p:(-float(p["len"]),float(p["ax"]),float(p["ad"])))
            bars.sort(key=lambda b:max((float(p["len"]) for p in b),default=0.0),reverse=True)

        self._bars=bars; self._plan_profile=prof
        self._sig_total_counts.clear()
        for (p,L,ax,ad),qty in sig_totals.items():
            self._sig_total_counts[(p,float(L),float(ax),float(ad))]=int(qty)
        self._build_sequential_plan()
        self._mode="plan"; self._state=STATE_IDLE
        self._seq_pos=-1; self._cur_sig=None
        self._update_counters_ui(); self._update_cycle_state_label()

    def _build_sequential_plan(self):
        self._seq_plan.clear(); seq=1
        for bi,bar in enumerate(self._bars):
            for pi,p in enumerate(bar):
                self._seq_plan.append({
                    "seq_id":seq,"bar":bi,"idx":pi,
                    "len":float(p["len"]),"ax":float(p["ax"]),"ad":float(p["ad"]),
                    "profile":p.get("profile",self._plan_profile),
                    "element":p.get("element",f"B{bi+1} #{pi+1}"),
                    "meta":dict(p.get("meta") or {})
                }); seq+=1

    # ---- Sequenza / avanzamento ----
    def _next_seq_piece(self)->Optional[Dict[str,Any]]:
        nxt=self._seq_pos+1
        return self._seq_plan[nxt] if 0<=nxt<len(self._seq_plan) else None

    def _same_sig(self,a:Dict[str,Any],b:Dict[str,Any])->bool:
        if not a or not b: return False
        if a.get("profile","")!=b.get("profile",""): return False
        return (abs(a.get("len",0.0)-b.get("len",0.0))<=0.05 and
                abs(a.get("ax",0.0)-b.get("ax",0.0))<=0.05 and
                abs(a.get("ad",0.0)-b.get("ad",0.0))<=0.05)

    def _advance_to_next_piece(self, skip_move=False):
        nxt=self._seq_pos+1
        if nxt>=len(self._seq_plan):
            self._toast("Piano completato.","ok")
            if self._opt_dialog:
                with contextlib.suppress(Exception): self._opt_dialog.accept()
                self._opt_dialog=None
            self._state=STATE_IDLE
            self._update_cycle_state_label()
            return
        self._seq_pos=nxt
        piece=self._seq_plan[self._seq_pos]
        self._cur_sig=self._sig_key(piece["profile"],piece["len"],piece["ax"],piece["ad"])
        self._pending_active_piece={
            "profile":piece["profile"],"len":piece["len"],"ax":piece["ax"],"ad":piece["ad"],
            "element":piece["element"],"seq_id":piece["seq_id"],"mode":"plan",
            "bar":piece.get("bar"),"idx":piece.get("idx")
        }
        self._piece_tagliato=False
        if skip_move:
            self._state=STATE_READY
            self._emit_active_piece()
        else:
            self._state=STATE_ARMING
            self._start_move(piece)
        self._apply_active_row(self._find_row_for_piece_tol(piece["profile"],piece["len"],piece["ax"],piece["ad"]))
        self._update_counters_ui()
        self._update_cycle_state_label()
        self._log_state(f"Advance → idx={self._seq_pos} state={self._state}")

    def _emit_active_piece(self):
        if not self._pending_active_piece: return
        self.activePieceChanged.emit(self._pending_active_piece)
        self._pending_active_piece=None
        self._state=STATE_READY
        self._update_cycle_state_label()
        self._log_state(f"Emit active piece seq={self._seq_pos}")

       def _start_move(self, piece: Dict[str, Any]):
        """
        Avvia movimento per pezzo in modalità automatico.
        
        Notifica contesto modalità alla macchina per gestione pressori.
        """
        self._state = STATE_MOVING
        thickness = self._get_profile_thickness(piece["profile"])
        eff = self._effective_position_length(piece["len"], piece["ax"], piece["ad"], thickness)
        
        if self.mio:
            # Notifica contesto: modalità plan + lunghezza pezzo
            if hasattr(self.mio, "set_mode_context"):
                # TODO: Ottenere lunghezza barra corrente da config/piano
                bar_length = 6500.0  # Default, da sostituire con valore reale
                self.mio. set_mode_context("plan", piece_length_mm=piece["len"], bar_length_mm=bar_length)
            
            self.mio.command_move(eff, piece["ax"], piece["ad"], profile=piece["profile"], element=piece["element"])
            self. mio.command_set_pressers(False, False)  # Logica interna decide se attivare
        else:
            self._position_machine_exact(eff, piece["ax"], piece["ad"], piece["profile"], piece["element"])
        
        self._update_cycle_state_label()
        self._log_state(f"Start move len_eff={eff:.2f}")

        def _try_auto_continue(self):
        """
        Tenta auto-continue se abilitato e condizioni soddisfatte.
        
        Fix: Rimosso limite 400mm, corretto skip_move per stessa barra. 
        """
        if not self._auto_continue_enabled:
            return
        
        cur = self._seq_plan[self._seq_pos] if 0 <= self._seq_pos < len(self._seq_plan) else None
        nxt = self._next_seq_piece()
        
        if not cur or not nxt:
            return
        
        if not self._same_sig(cur, nxt):
            return
        
        same_bar = (cur.get("bar") == nxt.get("bar"))
        
        if self._strict_bar_sequence and not same_bar:
            return
        
        if not same_bar and not self._auto_continue_across_bars:
            return
        
        self._log_state("Auto-continue triggered")
        
        if same_bar:
            self._advance_to_next_piece(skip_move=True)
        else:
            self._advance_to_next_piece(skip_move=False)

    # ---- Taglio ----
    def _simulate_cut_once(self):
        if self._mode!="plan": return
        if self._state!=STATE_READY: return
        piece=self._seq_plan[self._seq_pos] if 0<=self._seq_pos<len(self._seq_plan) else None
        if piece:
            self._dec_row_qty_for_sig(piece["profile"],piece["len"],piece["ax"],piece["ad"])
            self._emit_label(piece)
            self.pieceCut.emit({
                "profile":piece["profile"],"len":piece["len"],"ax":piece["ax"],"ad":piece["ad"],
                "element":piece["element"],"seq_id":piece["seq_id"],
                "mode":"plan","bar":piece.get("bar"),"idx":piece.get("idx")
            })
        self._piece_tagliato=True
        self._state=STATE_WAIT_BRAKE
        self._update_cycle_state_label()
        self._log_state("Cut executed → WAIT_BRAKE")

    def _simulate_manual_cut(self):
        if self._mode!="manual": return
        if self._state!=STATE_READY: return
        piece=self._manual_current_piece
        if not piece: return
        self._dec_row_qty_for_sig(piece["profile"],piece["len"],piece["ax"],piece["ad"])
        self._emit_label(piece)
        self.pieceCut.emit({**piece,"mode":"manual"})
        self._piece_tagliato=True
        self._state=STATE_WAIT_BRAKE
        self._update_cycle_state_label()
        self._log_state("Manual cut executed → WAIT_BRAKE")

    def simulate_cut_from_dialog(self):
        if self._mode=="plan":
            self._simulate_cut_once()
        elif self._mode=="manual":
            self._simulate_manual_cut()

    def _simulate_cut_key(self):
        if self._mode=="plan":
            self._simulate_cut_once()
        elif self._mode=="manual":
            self._simulate_manual_cut()

    # ---- Start (F9 / Space) ----
    def _handle_start_trigger(self):
        self._log_state(f"Start trigger state={self._state} mode={self._mode}")
        if self._state==STATE_WAIT_BRAKE:
            # freno rilasciato? avanzamento
            if not self._brake_locked:
                self._advance_to_next_piece(skip_move=False)
            return
        if self._state in (STATE_MOVING, STATE_ARMING):
            return
        if self._state==STATE_READY:
            if self._allow_skip_cut or self._piece_tagliato:
                self._unlock_brake(False)
                self._advance_to_next_piece(skip_move=False)
            return
        if self._mode=="manual":
            self._trigger_manual_cut()
            return
        if self._mode=="plan":
            self._unlock_brake(False)
            self._advance_to_next_piece(skip_move=False)

    # ---- Brake / lock ----
    def _refresh_brake_flag(self):
        if self.mio:
            st=self.mio.get_state()
            self._brake_locked=bool(st.get("brake_active",False))
        else:
            self._brake_locked=bool(getattr(self.machine,"brake_active",False))

    def _lock_brake(self):
        if self.mio:
            self.mio.command_lock_brake()
        else:
            with contextlib.suppress(Exception): setattr(self.machine,"brake_active",True)
        self._refresh_brake_flag()
        self._log_state("Brake locked.")

    def _unlock_brake(self,silent:bool=False):
        if self.mio:
            self.mio.command_release_brake()
        else:
            with contextlib.suppress(Exception): setattr(self.machine,"brake_active",False)
        self._refresh_brake_flag()
        if self._state==STATE_WAIT_BRAKE and not self._brake_locked:
            self._try_auto_continue()
        self._log_state("Brake unlocked.")

    # ---- Manuale posizionamento ----
       def _trigger_manual_cut(self):
        """
        Avvia taglio manuale.
        
        In manuale NON muove il motore:  operatore posiziona a mano,
        sistema legge posizione da encoder e aspetta taglio (F7).
        """
        # NON sbloccare freno/frizione (già fatto in _enter_manual_mode)
        
        r = self._current_or_next_piece_row()
        piece = self._get_row_piece(r) if r is not None else None
        
        if not piece:
            dlg = ManualCutDialog(self, preset=None)
            if not dlg.exec():
                return
            data = dlg.get_data()
            piece = {
                "profile": data["profile"],
                "element": data["element"],
                "len": data["len"],
                "ax": data["ax"],
                "ad": data["ad"],
                "seq_id": 0,
                "meta": {}
            }
        
        self._manual_current_piece = piece
        if r is not None:
            self._apply_active_row(r)
        
        self._pending_active_piece = {**piece, "mode": "manual"}
        self._state = STATE_READY  # ✅ Direttamente READY (no movimento)
        
        # Emit active piece subito
        self._emit_active_piece()
        
        self._update_cycle_state_label()
        self._toast(f"MANUALE: Posiziona testa DX a {piece['len']:. 2f}mm e premi F7 per taglio", "info")

    # ---- Tabella helpers ----
    def _row_is_header(self,row:int)->bool:
        it=self.tbl_cut.item(row,1)
        return bool(it) and not bool(it.flags() & Qt.ItemIsSelectable)

    def _first_piece_row(self) -> Optional[int]:
        for r in range(self.tbl_cut.rowCount()):
            if not self._row_is_header(r): return r
        return None

    def _current_or_next_piece_row(self) -> Optional[int]:
        r=self.tbl_cut.currentRow()
        if r is None or r<0 or self._row_is_header(r): return self._first_piece_row()
        return r

    def _get_row_piece(self,row:int)->Optional[Dict[str,Any]]:
        if row is None or row<0 or self._row_is_header(row): return None
        try:
            return {
                "profile": self.tbl_cut.item(row,1).text().strip(),
                "element": self.tbl_cut.item(row,2).text().strip(),
                "len": float(self.tbl_cut.item(row,3).text()),
                "ax": float(self.tbl_cut.item(row,4).text()),
                "ad": float(self.tbl_cut.item(row,5).text()),
                "seq_id": 0, "meta": {}
            }
        except Exception:
            return None

    def _apply_active_row(self,row:Optional[int]):
        if row is None or row<0: return
        if self._active_row is not None and self._active_row!=row:
            self._style_row_normal(self._active_row)
        self._active_row=row
        self._style_row_active(row)
        self.tbl_cut.selectRow(row)

    def _style_row_active(self,row:int):
        brush=QBrush(QColor("#00bcd4"))
        for c in range(self.tbl_cut.columnCount()):
            it=self.tbl_cut.item(row,c)
            if it: it.setBackground(brush); it.setForeground(QBrush(Qt.black))

    def _style_row_normal(self,row:int):
        brush=QBrush(QColor("#ffffff"))
        for c in range(self.tbl_cut.columnCount()):
            it=self.tbl_cut.item(row,c)
            if it: it.setBackground(brush); it.setForeground(QBrush(Qt.black))

    def _find_row_for_piece_tol(self, profile: str, length: float, ax: float, ad: float) -> Optional[int]:
        prof=profile.strip()
        best=None
        for r in range(self.tbl_cut.rowCount()):
            if self._row_is_header(r): continue
            try:
                p=self.tbl_cut.item(r,1).text().strip()
                L=float(self.tbl_cut.item(r,3).text())
                A=float(self.tbl_cut.item(r,4).text())
                D=float(self.tbl_cut.item(r,5).text())
            except Exception:
                continue
            if p!=prof: continue
            if abs(L-length)<=0.21 and abs(A-ax)<=0.21 and abs(D-ad)<=0.21:
                return r
            if best is None and abs(L-length)<=0.5 and abs(A-ax)<=0.5 and abs(D-ad)<=0.5:
                best=r
        return best

    def _dec_row_qty_for_sig(self, profile: str, length: float, ax: float, ad: float):
        prof=profile.strip()
        Ls=f"{float(length):.2f}"; Axs=f"{float(ax):.1f}"; Ads=f"{float(ad):.1f}"
        for r in range(self.tbl_cut.rowCount()):
            if self._row_is_header(r): continue
            try:
                p=self.tbl_cut.item(r,1).text().strip()
                Ltxt=self.tbl_cut.item(r,3).text().strip()
                Axtxt=self.tbl_cut.item(r,4).text().strip()
                Adtxt=self.tbl_cut.item(r,5).text().strip()
                itq=self.tbl_cut.item(r,6); q=int((itq.text() or "0").strip()) if itq else 0
            except Exception:
                continue
            if p==prof and Ltxt==Ls and Axtxt==Axs and Adtxt==Ads and q>0:
                new_q=q-1
                self.tbl_cut.setItem(r,6,QTableWidgetItem(str(new_q)))
                self.tbl_cut.item(r,6).setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                break

    # ---- Quote / calcoli ----
    def _get_profile_thickness(self, profile_name: str) -> float:
        name=profile_name.strip()
        with contextlib.suppress(Exception):
            prof=self._profiles_store.get_profile(name)
            if prof and float(prof.get("thickness") or 0.0)>0:
                return float(prof["thickness"])
        with contextlib.suppress(Exception):
            return float(read_settings().get("opt_current_profile_thickness_mm",0.0))
        return 0.0

    def _effective_position_length(self, external_len_mm: float, ang_sx: float, ang_dx: float, thickness_mm: float) -> float:
        th=max(0.0, thickness_mm)
        if th<=0.0: return max(0.0, external_len_mm)
        sx=0.0; dx=0.0
        with contextlib.suppress(Exception): sx=th*tan(radians(abs(ang_sx)))
        with contextlib.suppress(Exception): dx=th*tan(radians(abs(ang_dx)))
        return max(0.0, external_len_mm - sx - dx)

    def _position_machine_exact(self,target_mm:float,ax:float,ad:float,profile:str,element:str):
        # legacy fallback
        try:
            if hasattr(self.machine,"position_for_cut"):
                self.machine.position_for_cut(float(target_mm),float(ax),float(ad),profile,element)
            elif hasattr(self.machine,"move_to_length_and_angles"):
                self.machine.move_to_length_and_angles(length_mm=float(target_mm), ang_sx=float(ax), ang_dx=float(ad))
            elif hasattr(self.machine,"move_to_length"):
                self.machine.move_to_length(float(target_mm))
            else:
                setattr(self.machine,"position_current",float(target_mm))
        except Exception as e:
            QMessageBox.critical(self,"Posizionamento",str(e)); return

    # ---- Contatori ----
    def _sig_key(self, profile:str,length:float,ax:float,ad:float)->Tuple[str,float,float,float]:
        return (str(profile),round(length,2),round(ax,1),round(ad,1))

    def _sig_remaining_from_table(self,sig:Tuple[str,float,float,float])->int:
        prof,L2,ax1,ad1=sig; rem=0
        for r in range(self.tbl_cut.rowCount()):
            if self._row_is_header(r): continue
            try:
                p=self.tbl_cut.item(r,1).text().strip()
                L=round(float(self.tbl_cut.item(r,3).text()),2)
                ax=round(float(self.tbl_cut.item(r,4).text()),1)
                ad=round(float(self.tbl_cut.item(r,5).text()),1)
                q=int((self.tbl_cut.item(r,6).text() or "0").strip())
            except Exception: continue
            if p==prof and L==L2 and ax==ax1 and ad==ad1: rem+=q
        return rem

    def _update_counters_ui(self):
        if self._mode=="plan" and self._cur_sig:
            total=int(self._sig_total_counts.get(self._cur_sig,0))
            remaining=self._sig_remaining_from_table(self._cur_sig)
            done=max(0,total-remaining)
            self.lbl_target.setText(str(total))
            self.lbl_done.setText(str(done))
            self.lbl_remaining.setText(str(remaining))
        else:
            r=self.tbl_cut.currentRow()
            if r is None or r<0 or self._row_is_header(r):
                self.lbl_target.setText("0"); self.lbl_done.setText("0"); self.lbl_remaining.setText("0")
            else:
                it=self.tbl_cut.item(r,6)
                try: q=int((it.text() or "0").strip())
                except Exception: q=0
                self.lbl_target.setText(str(q)); self.lbl_done.setText("0"); self.lbl_remaining.setText(str(q))

    # ---- Eventi tabella ----
    def _on_cell_double_clicked(self,row:int,col:int):
        if self._row_is_header(row):
            profile=self.tbl_cut.item(row,1).text().strip() if self.tbl_cut.item(row,1) else ""
            if profile:
                if self._opt_dialog:
                    with contextlib.suppress(Exception): self.activePieceChanged.disconnect(self._opt_dialog.onActivePieceChanged)
                    with contextlib.suppress(Exception): self.pieceCut.disconnect(self._opt_dialog.onPieceCut)
                    with contextlib.suppress(Exception): self._opt_dialog.close()
                    self._opt_dialog=None
                self._optimize_profile(profile)
                if self._mode=="plan": self._open_opt_dialog(profile)
                else: QMessageBox.information(self,"Piano",f"Nessun pezzo rimanente per '{profile}'.")
            return
        if self._mode!="manual":
            self._enter_manual_mode()
        self._trigger_manual_cut()

    def _on_cell_entered(self,row:int,col:int):
        if col!=6 or row<0 or self._row_is_header(row): return
        it=self.tbl_cut.item(row,6)
        if not it: return
        try: q=int((it.text() or "0").strip())
        except Exception: q=0
        if q==0: QToolTip.showText(QCursor.pos(),"Pezzo completato (Q=0).",self.tbl_cut)

    def _on_current_cell_changed(self,cur_row:int,_cur_col:int,_prev_row:int,_prev_col:int):
        try:
            if cur_row is None or cur_row<0 or self._row_is_header(cur_row):
                self._current_profile_thickness=0.0; self._update_counters_ui(); return
            prof_item=self.tbl_cut.item(cur_row,1)
            name=prof_item.text().strip() if prof_item else ""
            self._current_profile_thickness=self._get_profile_thickness(name)
        except Exception:
            self._current_profile_thickness=0.0
        self._update_counters_ui()

    # ---- Key events ----
    def keyPressEvent(self,event:QKeyEvent):
        if event.key()==Qt.Key_F7:
            if self._mode=="plan": self._simulate_cut_once()
            elif self._mode=="manual": self._simulate_manual_cut()
            event.accept(); return
        if event.key() in (Qt.Key_Space, Qt.Key_F9):
            self._handle_start_trigger(); event.accept(); return
        super().keyPressEvent(event)

    # ---- Ciclo show/hide ----
    def on_show(self):
        if self._poll is None:
            self._poll=QTimer(self); self._poll.timeout.connect(self._tick); self._poll.start(80)
        self._update_counters_ui(); self._update_quota_label(); self._update_cycle_state_label()

    def _tick(self):
        # Aggiorna stato freno e movimento
        self._refresh_brake_flag()
        moving = self.mio.is_positioning_active() if self.mio else bool(getattr(self.machine,"positioning_active",False))
        if self._state==STATE_MOVING and not moving:
            # Arrivo: lock brake se non già, poi READY
            if not self._brake_locked:
                self._lock_brake()
            if self._state==STATE_MOVING:
                self._emit_active_piece()

        # Auto-continue se in WAIT_BRAKE e freno rilasciato
        if self._state==STATE_WAIT_BRAKE and not self._brake_locked:
            self._try_auto_continue()

        # Simulazione impulsi taglio / start (adapter)
        blade = self.mio.get_input("blade_pulse") if self.mio else False
        if blade and not self._blade_prev:
            if self._mode=="plan": self._simulate_cut_once()
            elif self._mode=="manual": self._simulate_manual_cut()
        self._blade_prev=blade

        start_pressed = self.mio.get_input("start_pressed") if self.mio else False
        if start_pressed and not self._start_prev:
            self._handle_start_trigger()
        self._start_prev=start_pressed

        self._update_quota_label()
        self._update_counters_ui()
        self._update_cycle_state_label()

        if self.mio:
            self.mio.tick()
        if self.status:
            with contextlib.suppress(Exception): self.status.refresh()

    def hideEvent(self,ev):
        if self._poll:
            with contextlib.suppress(Exception): self._poll.stop()
            self._poll=None
        self._unlock_brake(True)
        self._state=STATE_IDLE
        self._update_cycle_state_label()
        super().hideEvent(ev)

    def _update_quota_label(self):
        pos=None
        if self.mio:
            pos=self.mio.get_position()
        else:
            pos=getattr(self.machine,"encoder_position",None)
            if pos is None: pos=getattr(self.machine,"position_current",None)
        try: self.lbl_quota_card.setText(f"{float(pos):.2f} mm" if pos is not None else "— mm")
        except Exception: self.lbl_quota_card.setText("— mm")

    # ---- Navigazione / reset ----
    def _nav_home(self)->bool:
        if self._opt_dialog:
            with contextlib.suppress(Exception): self.activePieceChanged.disconnect(self._opt_dialog.onActivePieceChanged)
            with contextlib.suppress(Exception): self.pieceCut.disconnect(self._opt_dialog.onPieceCut)
            with contextlib.suppress(Exception): self._opt_dialog.close()
            self._opt_dialog=None
        if hasattr(self.appwin,"show_page"):
            with contextlib.suppress(Exception): self.appwin.show_page("home"); return True
        return False

    def _reset_and_home(self):
        if self._opt_dialog:
            with contextlib.suppress(Exception): self.activePieceChanged.disconnect(self._opt_dialog.onActivePieceChanged)
            with contextlib.suppress(Exception): self.pieceCut.disconnect(self._opt_dialog.onPieceCut)
            with contextlib.suppress(Exception): self._opt_dialog.close()
            self._opt_dialog=None
        self._mode="idle"; self._state=STATE_IDLE
        self._bars.clear(); self._seq_plan.clear(); self._seq_pos=-1
        self._cur_sig=None; self._sig_total_counts.clear()
        self._pending_active_piece=None
        if self.tbl_cut: self.tbl_cut.setRowCount(0)
        self._unlock_brake(True)
        self._update_counters_ui()
        self._update_cycle_state_label()
        self._nav_home()

    # ---- Fallback pack semplice ----
    def _pack_bfd(self,pieces:List[Dict[str,Any]],stock:float,kerf_base:float,
                  reversible:bool,thickness_mm:float,angle_tol:float,
                  max_angle:float,max_factor:float)->Tuple[List[List[Dict[str,Any]]],List[float]]:
        bars=[]
        for p in pieces:
            need=p["len"]; placed=False
            for b in bars:
                used=bar_used_length(b,kerf_base,self._ripasso_mm,reversible,thickness_mm,angle_tol,max_angle,max_factor)
                extra=joint_consumption(b[-1],kerf_base,self._ripasso_mm,reversible,thickness_mm,angle_tol,max_angle,max_factor)[0] if b else 0.0
                if used+need+(extra if b else 0.0)<=stock+1e-6:
                    b.append(p); placed=True; break
            if not placed: bars.append([p])
        rem=residuals(bars,stock,kerf_base,self._ripasso_mm,reversible,thickness_mm,angle_tol,max_angle,max_factor)
        return bars,rem

    # ---- Sequencer events (non utilizzati qui) ----
    def _on_step_started(self,idx:int,step:dict): pass
    def _on_step_finished(self,idx:int,step:dict): pass
    def _on_seq_done(self): self._toast("Sequenza terminata.","ok")
