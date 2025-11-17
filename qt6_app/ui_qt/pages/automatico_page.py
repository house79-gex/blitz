# v6.8.1 — Fix AttributeError (_set_pressers missing) + manual/plan highlight/positioning
# - Reintroduce _set_pressers() used by _move_and_arm().
# - Keeps v6.8 behavior: manual mode row highlight + positioning; plan signals to dialog; brake fallback.
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
    joint_consumption,
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


class OptimizationConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurazione ottimizzazione")
        cfg = read_settings()
        stock = str(cfg.get("opt_stock_mm", 6500.0))
        stock_use = str(cfg.get("opt_stock_usable_mm", 0.0))
        kerf = str(cfg.get("opt_kerf_mm", 3.0))
        ripasso = str(cfg.get("opt_ripasso_mm", 0.0))
        solver = str(cfg.get("opt_solver", "ILP_KNAP")).upper()
        tlimit = str(cfg.get("opt_time_limit_s", 15))
        tail_b = str(cfg.get("opt_refine_tail_bars", 6))
        tail_t = str(cfg.get("opt_refine_time_s", 25))
        max_ang = str(cfg.get("opt_kerf_max_angle_deg", 60.0))
        max_factor = str(cfg.get("opt_kerf_max_factor", 2.0))
        cons_ang = str(cfg.get("opt_knap_conservative_angle_deg", 45.0))
        reversible_now = bool(cfg.get("opt_current_profile_reversible", False))
        thickness = str(cfg.get("opt_current_profile_thickness_mm", 0.0))
        angle_tol = str(cfg.get("opt_reversible_angle_tol_deg", 0.5))
        warn_over = str(cfg.get("opt_warn_overflow_mm", 0.5))
        auto_cont = bool(cfg.get("opt_auto_continue_enabled", False))
        auto_across = bool(cfg.get("opt_auto_continue_across_bars", False))
        strict_seq = bool(cfg.get("opt_strict_bar_sequence", True))

        form = QFormLayout(self)
        def add(lbl, w): form.addRow(lbl, w); return w
        self.ed_stock = add("Stock nominale (mm):", QLineEdit(stock))
        self.ed_stock_use = add("Stock max utilizzabile (mm):", QLineEdit(stock_use))
        self.ed_kerf = add("Kerf base (mm):", QLineEdit(kerf))
        self.ed_ripasso = add("Ripasso (mm):", QLineEdit(ripasso))
        self.cmb_solver = QComboBox(); self.cmb_solver.addItems(["ILP_KNAP","ILP","BFD"])
        self.cmb_solver.setCurrentText("ILP_KNAP" if solver not in ("ILP","BFD") else solver); add("Solver:", self.cmb_solver)
        self.ed_time = add("Time limit solver (s):", QLineEdit(tlimit))
        self.ed_tail_b = add("Refine ultime barre (N):", QLineEdit(tail_b))
        self.ed_tail_t = add("Refine time (s):", QLineEdit(tail_t))
        self.ed_max_ang = add("Kerf max angolo (°):", QLineEdit(max_ang))
        self.ed_max_factor = add("Kerf max fattore:", QLineEdit(max_factor))
        self.ed_cons_ang = add("Angolo conservativo knapsack (°):", QLineEdit(cons_ang))
        self.chk_reversible = QCheckBox("Profilo reversibile"); self.chk_reversible.setChecked(reversible_now); form.addRow(self.chk_reversible)
        self.ed_thickness = add("Spessore profilo (mm):", QLineEdit(thickness))
        self.ed_angle_tol = add("Tolleranza angolo reversibile (°):", QLineEdit(angle_tol))
        self.ed_warn_over = add("Warn overflow soglia (mm):", QLineEdit(warn_over))
        self.chk_auto_cont = QCheckBox("Auto-continue pezzi identici (stessa barra)"); self.chk_auto_cont.setChecked(auto_cont); form.addRow(self.chk_auto_cont)
        self.chk_auto_across = QCheckBox("Consenti auto-continue su barra successiva"); self.chk_auto_across.setChecked(auto_across); form.addRow(self.chk_auto_across)
        self.chk_strict_seq = QCheckBox("Sequenza stretta per barra"); self.chk_strict_seq.setChecked(strict_seq); form.addRow(self.chk_strict_seq)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        btns.accepted.connect(self._save_and_close); btns.rejected.connect(self.reject)
        form.addRow(btns)
        self.resize(560,700)

    def _save_and_close(self):
        cfg = dict(read_settings())
        def f(t,d):
            try: return float((t or "").replace(",", "."))
            except Exception: return d
        def i(t,d):
            try: return int(float((t or "").replace(",", ".")))
            except Exception: return d
        cfg["opt_stock_mm"] = f(self.ed_stock.text(),6500.0)
        cfg["opt_stock_usable_mm"] = f(self.ed_stock_use.text(),0.0)
        cfg["opt_kerf_mm"] = f(self.ed_kerf.text(),3.0)
        cfg["opt_ripasso_mm"] = f(self.ed_ripasso.text(),0.0)
        cfg["opt_solver"] = self.cmb_solver.currentText().upper()
        cfg["opt_time_limit_s"] = i(self.ed_time.text(),15)
        cfg["opt_refine_tail_bars"] = i(self.ed_tail_b.text(),6)
        cfg["opt_refine_time_s"] = i(self.ed_tail_t.text(),25)
        cfg["opt_kerf_max_angle_deg"] = f(self.ed_max_ang.text(),60.0)
        cfg["opt_kerf_max_factor"] = f(self.ed_max_factor.text(),2.0)
        cfg["opt_knap_conservative_angle_deg"] = f(self.ed_cons_ang.text(),45.0)
        cfg["opt_current_profile_reversible"] = bool(self.chk_reversible.isChecked())
        cfg["opt_reversible_angle_tol_deg"] = f(self.ed_angle_tol.text(),0.5)
        cfg["opt_warn_overflow_mm"] = f(self.ed_warn_over.text(),0.5)
        cfg["opt_auto_continue_enabled"] = bool(self.chk_auto_cont.isChecked())
        cfg["opt_auto_continue_across_bars"] = bool(self._chk_auto_across.isChecked()) if hasattr(self, "_chk_auto_across") else bool(cfg.get("opt_auto_continue_across_bars", False))
        cfg["opt_strict_bar_sequence"] = bool(self.chk_strict_seq.isChecked())
        write_settings(cfg); self.accept()


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


class LabelPrinter:
    def __init__(self, settings: Dict[str, Any], toast_cb=None):
        self.toast = toast_cb
        self.enabled = bool(settings.get("label_enabled", False))
        self.model = str(settings.get("label_printer_model", "QL-800"))
        self.backend = str(settings.get("label_backend", "wspool"))
        self.printer = str(settings.get("label_printer_name", ""))
        self.paper = str(settings.get("label_paper", "DK-11201"))
        self.rotate = int(settings.get("label_rotate", 0))
        self.preview_if_no_printer = bool(settings.get("label_preview_if_no_printer", True))
        self._ql = None; self._pil = None
        with contextlib.suppress(Exception):
            from brother_ql.raster import BrotherQLRaster
            from brother_ql.backends import backend_factory
            from PIL import Image, ImageDraw, ImageFont
            self._ql={"BrotherQLRaster":BrotherQLRaster,"backend_factory":backend_factory}
            self._pil={"Image":Image,"ImageDraw":ImageDraw,"ImageFont":ImageFont}
        with contextlib.suppress(Exception):
            import qrcode

    def update_settings(self,s:Dict[str,Any]):
        self.enabled=bool(s.get("label_enabled",False))
        self.model=str(s.get("label_printer_model","QL-800"))
        self.backend=str(s.get("label_backend","wspool"))
        self.printer=str(s.get("label_printer_name",""))
        self.paper=str(s.get("label_paper","DK-11201"))
        self.rotate=int(s.get("label_rotate",0))
        self.preview_if_no_printer=bool(s.get("label_preview_if_no_printer",True))

    def print_label(self, lines: List[str], paper: Optional[str]=None,
                    rotate: Optional[int]=None, font_size: Optional[int]=None,
                    cut: Optional[bool]=None, qrcode_data: Optional[str]=None,
                    qrcode_module_size: int=4) -> bool:
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
            x_offset=8; y=8
            if qrcode_data:
                try:
                    import qrcode
                    qr=qrcode.QRCode(border=0, box_size=max(2,int(qrcode_module_size)))
                    qr.add_data(qrcode_data); qr.make(fit=True)
                    qrim=qr.make_image(fill_color="black", back_color="white").convert("1")
                    qrw,_=qrim.size; img.paste(qrim,(8,8)); x_offset=8+qrw+8
                except Exception: pass
            for line in lines:
                draw.text((x_offset,y),str(line),fill=0,font=font); y += int(fs*1.2)
            if use_rotate in (90,180,270):
                with contextlib.suppress(Exception): img=img.rotate(use_rotate,expand=True)
            if (not self.enabled) or (self._ql is None) or (not self.printer):
                if self.preview_if_no_printer and self.toast:
                    self.toast("Etichetta simulata (stampante non configurata).","info")
                return True
            BrotherQLRaster=self._ql["BrotherQLRaster"]; backend_factory=self._ql["backend_factory"]
            from brother_ql.conversion import convert
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
    activePieceChanged = Signal(dict)  # {profile,len,ax,ad,element,seq_id,mode}
    pieceCut = Signal(dict)            # idem sopra

    def __init__(self, appwin):
        super().__init__()
        self.appwin=appwin
        self.machine=appwin.machine
        self.seq=Sequencer(appwin)
        self.seq.step_started.connect(self._on_step_started)
        self.seq.step_finished.connect(self._on_step_finished)
        self.seq.finished.connect(self._on_seq_done)

        self.tbl_cut: Optional[QTableWidget]=None
        self.lbl_target: Optional[QLabel]=None
        self.lbl_done: Optional[QLabel]=None
        self.lbl_remaining: Optional[QLabel]=None
        self.status: Optional[StatusPanel]=None
        self.btn_start_row: Optional[QPushButton]=None
        self.viewer_frame: Optional[QFrame]=None
        self.lbl_quota_card: Optional[QLabel]=None
        self.banner: Optional[QLabel]=None

        self._orders=OrdersStore()
        self._profiles_store=ProfilesStore()
        self._current_profile_thickness: float=0.0

        self._mode="idle"  # idle | manual | plan
        self._plan_profile=""
        self._bars: List[List[Dict[str,Any]]]=[]
        self._seq_plan: List[Dict[str,Any]]=[]
        self._seq_pos=-1
        self._opt_dialog: Optional[OptimizationRunDialog]=None

        self._sig_total_counts: Dict[Tuple[str,float,float,float],int]={}
        self._cur_sig: Optional[Tuple[str,float,float,float]]=None

        self._active_row: Optional[int]=None

        self._brake_locked=False
        self._blade_prev=False
        self._start_prev=False
        self._move_target_mm=0.0
        self._inpos_since=0.0
        self._lock_on_inpos=False
        self._poll: Optional[QTimer]=None

        cfg=read_settings()
        self._same_len_tol=self._cfg_float(cfg,"auto_same_len_tol_mm",0.10)
        self._same_ang_tol=self._cfg_float(cfg,"auto_same_ang_tol_deg",0.10)
        self._kerf_max_angle_deg=self._cfg_float(cfg,"opt_kerf_max_angle_deg",60.0)
        self._kerf_max_factor=self._cfg_float(cfg,"opt_kerf_max_factor",2.0)
        self._knap_cons_angle_deg=self._cfg_float(cfg,"opt_knap_conservative_angle_deg",45.0)
        self._ripasso_mm=self._cfg_float(cfg,"opt_ripasso_mm",0.0)
        self._warn_overflow_mm=self._cfg_float(cfg,"opt_warn_overflow_mm",0.5)
        self._auto_continue_enabled=bool(cfg.get("opt_auto_continue_enabled",False))
        self._auto_continue_across_bars=bool(cfg.get("opt_auto_continue_across_bars",False))
        self._strict_bar_sequence=bool(cfg.get("opt_strict_bar_sequence",True))

        try: self._fq_offset_mm=float(cfg.get("semi_offset_mm",120.0))
        except Exception: self._fq_offset_mm=120.0
        try: self._extshort_safe_mm=float(cfg.get("auto_extshort_safe_pos_mm",400.0))
        except Exception: self._extshort_safe_mm=400.0
        try: self._kerf_base_mm=float(cfg.get("opt_kerf_mm",3.0))
        except Exception: self._kerf_base_mm=3.0
        try: self._after_cut_pause_ms=int(float(cfg.get("auto_after_cut_pause_ms",300)))
        except Exception: self._after_cut_pause_ms=300

        self._fq_state={"active":False,"phase":"","final_target":0.0,"ax":0.0,"ad":0.0,"profile":"","element":"","min_q":0.0}
        self._piece_fq_pending=False

        self._label_enabled=bool(cfg.get("label_enabled",False))
        self._label_printer=LabelPrinter({
            "label_enabled":self._label_enabled,
            "label_printer_model":cfg.get("label_printer_model","QL-800"),
            "label_backend":cfg.get("label_backend","wspool"),
            "label_printer_name":cfg.get("label_printer_name",""),
            "label_paper":cfg.get("label_paper","DK-11201"),
            "label_rotate":cfg.get("label_rotate",0),
            "label_preview_if_no_printer":True,
        }, toast_cb=self._toast)

        self._manual_current_piece: Optional[Dict[str,Any]] = None

        self._build()

    @staticmethod
    def _cfg_float(cfg: Dict[str,Any], key: str, dflt: float) -> float:
        try: return float(cfg.get(key,dflt))
        except Exception: return dflt

    def _open_opt_config(self):
        dlg = OptimizationConfigDialog(self)
        if dlg.exec():
            self._toast("Config ottimizzazione aggiornata.","ok")
            cfg = read_settings()
            self._kerf_max_angle_deg=self._cfg_float(cfg,"opt_kerf_max_angle_deg",60.0)
            self._kerf_max_factor=self._cfg_float(cfg,"opt_kerf_max_factor",2.0)
            self._knap_cons_angle_deg=self._cfg_float(cfg,"opt_knap_conservative_angle_deg",45.0)
            self._ripasso_mm=self._cfg_float(cfg,"opt_ripasso_mm",0.0)
            self._warn_overflow_mm=self._cfg_float(cfg,"opt_warn_overflow_mm",0.5)
            self._auto_continue_enabled=bool(cfg.get("opt_auto_continue_enabled",False))
            self._auto_continue_across_bars=bool(cfg.get("opt_auto_continue_across_bars",False))
            self._strict_bar_sequence=bool(cfg.get("opt_strict_bar_sequence",True))

    def _build(self):
        root=QVBoxLayout(self); root.setContentsMargins(8,8,8,8); root.setSpacing(6)
        root.addWidget(Header(self.appwin,"AUTOMATICO",mode="default",
                              on_home=self._nav_home,on_reset=self._reset_and_home))
        self.banner=QLabel(""); self.banner.setVisible(False); self.banner.setAlignment(Qt.AlignCenter)
        self.banner.setStyleSheet("QLabel { background:#ffe7ba; color:#1b1b1b; font-size:18px; font-weight:800; padding:8px 12px; border:1px solid #c49a28; border-radius:6px; }")
        root.addWidget(self.banner)

        top=QHBoxLayout()
        btn_import=QPushButton("Importa…"); btn_import.clicked.connect(self._import_cutlist); top.addWidget(btn_import)
        btn_manual=QPushButton("Modalità Manuale"); btn_manual.clicked.connect(self._enter_manual_mode); top.addWidget(btn_manual)
        btn_opt=QPushButton("Ottimizza"); btn_opt.clicked.connect(self._on_optimize_clicked); top.addWidget(btn_opt)
        btn_cfg=QPushButton("Config. ottimizzazione…"); btn_cfg.clicked.connect(self._open_opt_config); top.addWidget(btn_cfg)
        top.addStretch(1); root.addLayout(top)

        body=QHBoxLayout(); body.setSpacing(8); root.addLayout(body,1)

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
        self.tbl_cut.setStyleSheet("QTableWidget::item:selected { outline: none; }")
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
        start_row.addWidget(self.lbl_quota_card); start_row.addStretch(1)
        ll.addLayout(start_row); body.addWidget(left,1)

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

        lab_box=QFrame(); lab_box.setStyleSheet("QFrame { border:1px solid #3b4b5a; border-radius:6px; }")
        lb=QVBoxLayout(lab_box); lb.setContentsMargins(10,10,10,10); lb.setSpacing(6)
        lb.addWidget(QLabel("Etichette"))
        self.chk_label=QCheckBox("Stampa etichetta dopo taglio"); self.chk_label.setChecked(self._label_enabled)
        self.chk_label.toggled.connect(self._on_label_toggle); lb.addWidget(self.chk_label)
        btn_label_test=QPushButton("Test etichetta"); btn_label_test.clicked.connect(self._test_label); lb.addWidget(btn_label_test)
        rl.addWidget(lab_box,0)

        rl.addStretch(1); body.addWidget(right,0)
        QShortcut(QKeySequence("Space"), self, activated=self._handle_start_trigger)

    # ---------- Manuale ----------
    def _enter_manual_mode(self):
        if self._mode == "plan":
            self._bars.clear(); self._seq_plan.clear(); self._seq_pos=-1
            self._cur_sig=None
        self._mode="manual"
        self.lbl_target.setText("1"); self.lbl_done.setText("0"); self.lbl_remaining.setText("1")
        self._toast("Manuale: doppio click su una riga per posizionare, oppure seleziona la riga e premi Start.","info")

    # ---------- Banner / Toast ----------
    def _show_banner(self,msg:str,level:str="info"):
        styles={"info":"background:#ffe7ba; color:#1b1b1b; border:1px solid #c49a28;",
                "ok":"background:#d4efdf; color:#145a32; border:1px solid #27ae60;",
                "warn":"background:#fdecea; color:#7b241c; border:1px solid #c0392b;"}
        sty=styles.get(level,styles["info"])
        self.banner.setText(msg)
        self.banner.setStyleSheet(f"QLabel {{{sty} font-size:20px; font-weight:900; padding:10px 14px; border-radius:8px;}}")
        self.banner.setVisible(True)

    def _hide_banner(self):
        self.banner.setVisible(False); self.banner.setText("")

    def _toast(self,msg:str,level:str="info"):
        if hasattr(self.appwin,"toast"):
            with contextlib.suppress(Exception): self.appwin.toast.show(msg,level,2500)
        else:
            logger.info("%s: %s",level.upper(),msg)

    # ---------- Etichette ----------
    def _on_label_toggle(self,on:bool):
        self._label_enabled=bool(on)
        cfg=dict(read_settings()); cfg["label_enabled"]=self._label_enabled
        write_settings(cfg); self._label_printer.update_settings(cfg)

    def _test_label(self):
        piece={"seq_id":999,"profile":"DEMO","element":"Montante #1",
               "len":1234.5,"ax":45.0,"ad":0.0,
               "meta":{"commessa":"JOB-2025-001","element_id":"E-01","infisso_id":"W-42","misura_elem":1234.5}}
        self._emit_label(piece)

    def _emit_label(self,piece:Dict[str,Any]):
        if not self._label_enabled: return
        fmt={"profile":piece.get("profile",""),
             "element":piece.get("element",""),
             "length_mm":piece.get("len",piece.get("length",0.0)),
             "ang_sx":piece.get("ax",piece.get("ang_sx",0.0)),
             "ang_dx":piece.get("ad",piece.get("ang_dx",0.0)),
             "seq_id":piece.get("seq_id",0),
             "timestamp":time.strftime("%H:%M:%S"),
             "qty_remaining":0}
        meta=piece.get("meta") or {}
        if isinstance(meta,dict):
            for k,v in meta.items():
                if k not in fmt: fmt[k]=v
        templates=resolve_templates(piece.get("profile",""),piece.get("element",""))
        for tmpl in templates:
            lines=[]
            for raw in tmpl.get("lines",[]):
                try: lines.append(str(raw).format(**fmt))
                except Exception: lines.append(str(raw))
            qr_conf=tmpl.get("qrcode") or {}
            qr_data=None
            if isinstance(qr_conf,dict) and qr_conf.get("data"):
                try: qr_data=str(qr_conf["data"]).format(**fmt)
                except Exception: qr_data=str(qr_conf["data"])
            qr_mod=int(qr_conf.get("module_size",4)) if isinstance(qr_conf,dict) else 4
            self._label_printer.print_label(lines,
                                            paper=tmpl.get("paper"),
                                            rotate=int(tmpl.get("rotate",0)),
                                            font_size=int(tmpl.get("font_size",32)),
                                            cut=bool(tmpl.get("cut",True)),
                                            qrcode_data=qr_data,
                                            qrcode_module_size=qr_mod)

    # ---------- Import cutlist ----------
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
        seq_it=QTableWidgetItem(""); seq_it.setFont(font); seq_it.setBackground(bg); seq_it.setFlags(Qt.ItemIsEnabled); items.append(seq_it)
        itp=QTableWidgetItem(profile or "—"); itp.setFont(font); itp.setBackground(bg); itp.setForeground(QBrush(Qt.black)); itp.setFlags(Qt.ItemIsEnabled); items.append(itp)
        for _ in range(6):
            x=QTableWidgetItem(""); x.setFont(font); x.setBackground(bg); x.setFlags(Qt.ItemIsEnabled); items.append(x)
        return items

    def _load_cutlist(self,cuts:List[Dict[str,Any]]):
        self.tbl_cut.setRowCount(0)
        groups=defaultdict(list); order=[]
        for c in cuts:
            p=str(c.get("profile","")).strip()
            if p not in groups: order.append(p)
            groups[p].append(c)
        seq_counter=1
        for prof in order:
            r=self.tbl_cut.rowCount(); self.tbl_cut.insertRow(r)
            for col,it in enumerate(self._header_items(prof)): self.tbl_cut.setItem(r,col,it)
            for c in groups[prof]:
                r=self.tbl_cut.rowCount(); self.tbl_cut.insertRow(r)
                Lmm=float(c.get("length_mm",0.0)); ax=float(c.get("ang_sx",0.0)); ad=float(c.get("ang_dx",0.0)); qty=int(c.get("qty",0))
                cells=[
                    QTableWidgetItem(str(seq_counter)),
                    QTableWidgetItem(str(c.get("profile",""))),
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
        self._mode="idle"
        self._sig_total_counts.clear()
        self._cur_sig=None
        self._seq_plan.clear()
        self._seq_pos=-1
        self._active_row=None
        self._hide_banner()
        self._update_counters_ui()

    # ---------- Ottimizzazione / Piano ----------
    def _on_optimize_clicked(self):
        prof=None; r=self.tbl_cut.currentRow()
        if r is not None and r>=0 and self._row_is_header(r):
            it=self.tbl_cut.item(r,1); prof=it.text().strip() if it else None
        if not prof: prof=self._find_first_header_profile()
        if not prof:
            QMessageBox.information(self,"Ottimizza","Seleziona un profilo."); return
        self._optimize_profile(prof); self._open_opt_dialog(prof)

    def _open_opt_dialog(self,profile:str):
        if self._mode != "plan":
            return
        prof=(profile or "").strip()
        rows=[]
        for r in range(self.tbl_cut.rowCount()):
            if self._row_is_header(r): continue
            if self.tbl_cut.item(r,1) and self.tbl_cut.item(r,1).text().strip()==prof:
                try:
                    L=float(self.tbl_cut.item(r,3).text())
                    ax=float(self.tbl_cut.item(r,4).text())
                    ad=float(self.tbl_cut.item(r,5).text())
                    q=int(self.tbl_cut.item(r,6).text())
                except Exception: continue
                if q>0: rows.append({"length_mm":round(L,2),"ang_sx":ax,"ang_dx":ad,"qty":q})
        if not rows: return
        if self._opt_dialog and getattr(self._opt_dialog,"profile",None)==prof:
            with contextlib.suppress(Exception): self._opt_dialog.raise_(); self._opt_dialog.activateWindow(); return
        self._opt_dialog=OptimizationRunDialog(self, prof, rows, overlay_target=self.viewer_frame)
        with contextlib.suppress(Exception): self.activePieceChanged.connect(self._opt_dialog.onActivePieceChanged)
        with contextlib.suppress(Exception): self.pieceCut.connect(self._opt_dialog.onPieceCut)
        with contextlib.suppress(Exception): self._opt_dialog.startRequested.connect(self._handle_start_trigger)
        with contextlib.suppress(Exception): self._opt_dialog.simulationRequested.connect(self.simulate_cut_from_dialog)
        self._opt_dialog.finished.connect(lambda _p: setattr(self,"_opt_dialog",None))
        self._opt_dialog.show()
        self._toast("Piano grafico aperto.","info")

    def _find_first_header_profile(self)->Optional[str]:
        for r in range(self.tbl_cut.rowCount()):
            if self._row_is_header(r):
                it=self.tbl_cut.item(r,1)
                if it: return it.text().strip()
        return None

    def _optimize_profile(self,profile:str):
        prof=(profile or "").strip()
        if not prof:
            QMessageBox.information(self,"Ottimizza","Profilo mancante."); return
        pieces=[]; sig_totals=defaultdict(int)
        for r in range(self.tbl_cut.rowCount()):
            if self._row_is_header(r): continue
            if self.tbl_cut.item(r,1) and self.tbl_cut.item(r,1).text().strip()==prof:
                try:
                    L=round(float(self.tbl_cut.item(r,3).text()),2)
                    ax=float(self.tbl_cut.item(r,4).text())
                    ad=float(self.tbl_cut.item(r,5).text())
                    q=int(self.tbl_cut.item(r,6).text())
                    element_name=str(self.tbl_cut.item(r,2).text() or "")
                    meta=self.tbl_cut.item(r,0).data(Qt.UserRole) or {}
                except Exception: continue
                for _ in range(max(0,q)):
                    pieces.append({"len":float(L),"ax":float(ax),"ad":float(ad),"profile":prof,"element":element_name,"meta":dict(meta)})
                sig_totals[(prof,L,round(ax,1),round(ad,1))]+=max(0,q)
        if not pieces:
            QMessageBox.information(self,"Ottimizza",f"Nessun pezzo per '{prof}'."); return
        cfg=read_settings()
        stock_nom=self._cfg_float(cfg,"opt_stock_mm",6500.0)
        stock_usable=self._cfg_float(cfg,"opt_stock_usable_mm",0.0)
        stock=stock_usable if stock_usable>0 else stock_nom
        kerf_base=self._cfg_float(cfg,"opt_kerf_mm",3.0)
        solver=str(cfg.get("opt_solver","ILP_KNAP")).upper()
        per_bar_time=self._cfg_float(cfg,"opt_time_limit_s",15.0)
        tail_n=int(self._cfg_float(cfg,"opt_refine_tail_bars",6.0))
        tail_t=int(self._cfg_float(cfg,"opt_refine_time_s",25.0))
        reversible_now=bool(cfg.get("opt_current_profile_reversible",False))
        thickness_mm=self._get_profile_thickness(prof)
        angle_tol=self._cfg_float(cfg,"opt_reversible_angle_tol_deg",0.5)
        max_angle=self._kerf_max_angle_deg
        max_factor=self._kerf_max_factor

        pieces.sort(key=lambda x:(-x["len"],x["ax"],x["ad"]))
        if solver in ("ILP_KNAP","ILP"):
            bars, rem=pack_bars_knapsack_ilp(pieces=pieces,stock=stock,kerf_base=kerf_base,
                                             ripasso_mm=self._ripasso_mm, conservative_angle_deg=self._knap_cons_angle_deg,
                                             max_angle=max_angle, max_factor=max_factor,
                                             reversible=reversible_now, thickness_mm=thickness_mm,
                                             angle_tol=angle_tol, per_bar_time_s=int(per_bar_time))
            if not bars:
                bars, rem=self._pack_bfd(pieces,stock,kerf_base,reversible_now,thickness_mm,angle_tol,max_angle,max_factor)
        else:
            bars, rem=self._pack_bfd(pieces,stock,kerf_base,reversible_now,thickness_mm,angle_tol,max_angle,max_factor)
        with contextlib.suppress(Exception):
            bars, rem=refine_tail_ilp(bars,stock,kerf_base,self._ripasso_mm,reversible_now,thickness_mm,
                                      angle_tol,tail_bars=tail_n,time_limit_s=tail_t,
                                      max_angle=max_angle,max_factor=max_factor)
        for b in bars:
            with contextlib.suppress(Exception):
                b.sort(key=lambda p:(-float(p["len"]),float(p["ax"]),float(p["ad"])))
        self._bars=bars; self._plan_profile=prof
        self._sig_total_counts.clear()
        for (p,L,ax,ad),qty in sig_totals.items():
            self._sig_total_counts[(p,float(L),float(ax),float(ad))]=int(qty)
        self._build_sequential_plan()
        issues=self._verify_sequence_order()
        if issues:
            self._toast(f"Avviso sequenza ({len(issues)} problemi).","warn")
            for line in issues[:10]: logger.warning("SEQ ISSUE: %s",line)
        else:
            self._toast("Sequenza OK (decrescente per barra).","ok")
        self._debug_dump_sequence()
        self._mode="plan"
        self._seq_pos=-1
        self._cur_sig=None
        self._update_counters_ui()

    def _build_sequential_plan(self):
        self._seq_plan.clear(); seq_id=1
        for bi,bar in enumerate(self._bars):
            for pi,p in enumerate(bar):
                self._seq_plan.append({
                    "seq_id":seq_id,"bar":bi,"idx":pi,
                    "len":float(p["len"]),"ax":float(p["ax"]),"ad":float(p["ad"]),
                    "profile":p.get("profile",self._plan_profile),
                    "element":p.get("element",f"BAR {bi+1} #{pi+1}"),
                    "meta":dict(p.get("meta") or {})
                }); seq_id+=1

    def _verify_sequence_order(self)->List[str]:
        issues=[]
        for bi,bar in enumerate(self._bars):
            prev=None
            for p in bar:
                L=float(p["len"])
                if prev is not None and L>prev+1e-6:
                    issues.append(f"Barra {bi+1}: {L} > {prev}")
                prev=L
        last=-1
        for it in self._seq_plan:
            if it["bar"]<last:
                issues.append(f"Retrocesso da barra {last+1} a {it['bar']+1}")
            last=it["bar"]
        return issues

    def _debug_dump_sequence(self):
        logger.info("=== SEQUENZA TAGLIO (profilo=%s) ===",self._plan_profile)
        for it in self._seq_plan:
            logger.info("SEQ %4d | BAR %2d | LEN %.2f | AX %.1f | AD %.1f | %s",
                        it["seq_id"], it["bar"]+1, it["len"], it["ax"], it["ad"], it["element"])

    def _next_seq_piece(self)->Optional[Dict[str,Any]]:
        nxt=self._seq_pos+1
        if 0<=nxt<len(self._seq_plan): return self._seq_plan[nxt]
        return None

    # ---------- Avanzamento piano ----------
    def _advance_to_next_piece(self):
        nxt=self._seq_pos+1
        if nxt>=len(self._seq_plan):
            self._toast("Piano completato","ok")
            if self._opt_dialog:
                with contextlib.suppress(Exception): self._opt_dialog.accept()
                self._opt_dialog=None
            return
        self._seq_pos=nxt
        p=self._seq_plan[self._seq_pos]
        self._cur_sig=self._sig_key(p["profile"],p["len"],p["ax"],p["ad"])
        with contextlib.suppress(Exception):
            setattr(self.machine,"semi_auto_target_pieces",1)
            setattr(self.machine,"semi_auto_count_done",0)
        self._move_and_arm(p["len"],p["ax"],p["ad"],p["profile"],p["element"])
        self._apply_active_row(self._find_row_for_piece_tol(p["profile"],p["len"],p["ax"],p["ad"]))
        self.activePieceChanged.emit({
            "profile":p["profile"],"len":p["len"],"ax":p["ax"],"ad":p["ad"],
            "element":p["element"],"seq_id":p["seq_id"],"mode":"plan"
        })
        self._update_counters_ui()

    # ---------- Start trigger ----------
    def _handle_start_trigger(self):
        if self._mode=="manual":
            self._trigger_manual_cut()
            return
        if self._mode!="plan" or not self._seq_plan: return
        if self._fq_state.get("active",False): return
        tgt=int(getattr(self.machine,"semi_auto_target_pieces",0) or 0)
        done=int(getattr(self.machine,"semi_auto_count_done",0) or 0)
        if self._brake_locked and tgt>0 and done<tgt: return
        self._advance_to_next_piece()

    def _trigger_manual_cut(self):
        r=self.tbl_cut.currentRow()
        if r is not None and r>=0 and not self._row_is_header(r):
            try:
                piece={
                    "profile": (self.tbl_cut.item(r,1).text() or "").strip(),
                    "element": (self.tbl_cut.item(r,2).text() or "").strip(),
                    "len": float(self.tbl_cut.item(r,3).text()),
                    "ax": float(self.tbl_cut.item(r,4).text()),
                    "ad": float(self.tbl_cut.item(r,5).text()),
                    "seq_id":0,"meta":{}
                }
            except Exception:
                piece=None
            if piece:
                self._move_and_arm(piece["len"],piece["ax"],piece["ad"],piece["profile"],piece["element"])
                self.lbl_target.setText("1"); self.lbl_done.setText("0"); self.lbl_remaining.setText("1")
                self._apply_active_row(r)
                self.activePieceChanged.emit({**piece,"mode":"manual"})
                with contextlib.suppress(Exception):
                    setattr(self.machine,"semi_auto_target_pieces",1); setattr(self.machine,"semi_auto_count_done",0)
                self._manual_current_piece=piece
                return
        dlg=ManualCutDialog(self,preset=None)
        if not dlg.exec(): return
        data=dlg.get_data()
        piece={"profile":data["profile"],"element":data["element"],
               "len":data["len"],"ax":data["ax"],"ad":data["ad"],"seq_id":0,"meta":{}}
        self._move_and_arm(piece["len"],piece["ax"],piece["ad"],piece["profile"],piece["element"])
        self.lbl_target.setText("1"); self.lbl_done.setText("0"); self.lbl_remaining.setText("1")
        self.activePieceChanged.emit({**piece,"mode":"manual"})
        with contextlib.suppress(Exception):
            setattr(self.machine,"semi_auto_target_pieces",1); setattr(self.machine,"semi_auto_count_done",0)
        self._manual_current_piece=piece

    # ---------- Simulazione taglio ----------
    def simulate_cut_from_dialog(self):
        self._simulate_cut_once()

    def _simulate_cut_once(self):
        if self._mode=="manual":
            self._simulate_manual_cut()
            return
        tgt=int(getattr(self.machine,"semi_auto_target_pieces",0) or 0)
        done=int(getattr(self.machine,"semi_auto_count_done",0) or 0)
        remaining=max(tgt-done,0)
        if not (self._brake_locked and tgt>0 and remaining>0):
            return
        if self._fq_state.get("active",False):
            phase=self._fq_state.get("phase","")
            if phase=="intest":
                self._show_banner("Offset Fuori quota","warn")
                ax=float(self._fq_state.get("ax",0.0)); ad=float(self._fq_state.get("ad",0.0))
                prof=str(self._fq_state.get("profile","")); elem=str(self._fq_state.get("element",""))
                target2=float(self._fq_state.get("final_target",0.0))
                self._unlock_brake()
                QTimer.singleShot(int(self._after_cut_pause_ms),
                                  lambda: self._position_machine_exact(target2,ax,ad,prof,elem))
                self._fq_state["phase"]="offset"
                with contextlib.suppress(Exception):
                    setattr(self.machine,"semi_auto_target_pieces",1); setattr(self.machine,"semi_auto_count_done",0)
                return
            elif phase=="offset":
                self._hide_banner()
                self._fq_state={"active":False,"phase":"","final_target":0.0,"ax":0.0,"ad":0.0,"profile":"","element":"","min_q":0.0}
        new_done=done+1
        with contextlib.suppress(Exception): setattr(self.machine,"semi_auto_count_done",new_done)
        current_piece=self._seq_plan[self._seq_pos] if 0<=self._seq_pos<len(self._seq_plan) else None
        if current_piece:
            self._emit_label(current_piece)
            self.pieceCut.emit({
                "profile":current_piece["profile"],"len":current_piece["len"],
                "ax":current_piece["ax"],"ad":current_piece["ad"],
                "element":current_piece["element"],"seq_id":current_piece["seq_id"],
                "mode":"plan"
            })
        if new_done>=tgt:
            with contextlib.suppress(Exception):
                setattr(self.machine,"semi_auto_target_pieces",0); setattr(self.machine,"semi_auto_count_done",0)
            self._unlock_brake()
            QTimer.singleShot(int(self._after_cut_pause_ms), self._advance_to_next_piece)
        self._update_counters_ui()

    def _simulate_manual_cut(self):
        piece=self._manual_current_piece
        if not piece: return
        self._emit_label(piece)
        self.pieceCut.emit({**piece,"mode":"manual"})
        self._unlock_brake()
        self.lbl_done.setText("1"); self.lbl_remaining.setText("0")
        with contextlib.suppress(Exception):
            setattr(self.machine,"semi_auto_target_pieces",0)
            setattr(self.machine,"semi_auto_count_done",0)

    # ---------- Row highlight ----------
    def _style_row_active(self,row:int):
        if row is None or row<0: return
        brush=QBrush(QColor("#00bcd4"))
        for c in range(self.tbl_cut.columnCount()):
            it=self.tbl_cut.item(row,c)
            if it: it.setData(Qt.BackgroundRole,brush); it.setForeground(QBrush(Qt.black))

    def _style_row_normal(self,row:int):
        if row is None or row<0: return
        brush=QBrush(QColor("#ffffff"))
        for c in range(self.tbl_cut.columnCount()):
            it=self.tbl_cut.item(row,c)
            if it: it.setData(Qt.BackgroundRole,brush); it.setForeground(QBrush(Qt.black))

    def _apply_active_row(self,row:Optional[int]):
        if row is None: return
        if self._active_row is not None and self._active_row!=row:
            self._style_row_normal(self._active_row)
        self._active_row=row
        self._style_row_active(row)
        self.tbl_cut.selectRow(row)

    def _find_row_for_piece_tol(self, profile: str, length: float, ax: float, ad: float) -> Optional[int]:
        prof=profile.strip()
        best=None
        for r in range(self.tbl_cut.rowCount()):
            if self._row_is_header(r): continue
            try:
                p=(self.tbl_cut.item(r,1).text() or "").strip()
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

    # ---------- Fuori quota / posizionamento ----------
    def _get_profile_thickness(self, profile_name: str) -> float:
        name=(profile_name or "").strip()
        with contextlib.suppress(Exception):
            if name:
                prof=self._profiles_store.get_profile(name)
                if prof and float(prof.get("thickness") or 0.0)>0.0: return float(prof["thickness"])
        with contextlib.suppress(Exception):
            return float(read_settings().get("opt_current_profile_thickness_mm",0.0))
        return 0.0

    def _effective_position_length(self, external_len_mm: float, ang_sx: float, ang_dx: float, thickness_mm: float) -> float:
        L=float(external_len_mm); th=max(0.0,float(thickness_mm))
        if th<=0.0: return max(0.0,L)
        with contextlib.suppress(Exception): c_sx=th*tan(radians(abs(float(ang_sx))))
        if 'c_sx' not in locals(): c_sx=0.0
        with contextlib.suppress(Exception): c_dx=th*tan(radians(abs(float(ang_dx))))
        if 'c_dx' not in locals(): c_dx=0.0
        return max(0.0,L-max(0.0,c_sx)-max(0.0,c_dx))

    def _enforce_length_limits(self,length_mm:float)->tuple[float,bool,float,float]:
        min_q=float(getattr(self.machine,"min_distance",250.0))
        max_q=float(getattr(self.machine,"max_cut_length",read_settings().get("semi_max_length_mm",6500.0)))
        if length_mm<min_q-1e-6: return length_mm,False,min_q,max_q
        if length_mm>max_q+1e-6: return max_q,True,min_q,max_q
        return length_mm,True,min_q,max_q

    def _position_machine_exact(self,target_mm:float,ax:float,ad:float,profile:str,element:str,allow_pressers_locked:bool=False):
        if bool(getattr(self.machine,"brake_active",False)): return
        if not allow_pressers_locked:
            lp=bool(getattr(self.machine,"left_presser_locked",False))
            rp=bool(getattr(self.machine,"right_presser_locked",False))
            if lp or rp: return
        with contextlib.suppress(Exception):
            if hasattr(self.machine,"set_active_mode"): self.machine.set_active_mode("semi")
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
        self._move_target_mm=float(target_mm); self._inpos_since=0.0; self._lock_on_inpos=True
        QTimer.singleShot(300, self._maybe_force_lock)

    def _set_pressers(self,left_locked:Optional[bool]=None,right_locked:Optional[bool]=None):
        with contextlib.suppress(Exception):
            if left_locked is not None:
                if hasattr(self.machine,"set_left_presser_locked"):
                    self.machine.set_left_presser_locked(bool(left_locked))
                else:
                    setattr(self.machine,"left_presser_locked",bool(left_locked))
            if right_locked is not None:
                if hasattr(self.machine,"set_right_presser_locked"):
                    self.machine.set_right_presser_locked(bool(right_locked))
                else:
                    setattr(self.machine,"right_presser_locked",bool(right_locked))

    def _move_and_arm(self,length:float,ax:float,ad:float,profile:str,element:str):
        thickness_mm=self._get_profile_thickness(profile)
        if thickness_mm<=0 and self._current_profile_thickness>0: thickness_mm=float(self._current_profile_thickness)
        eff_len=self._effective_position_length(length,ax,ad,thickness_mm)
        target_len,ok,min_q,_=self._enforce_length_limits(eff_len)
        both_zero=(abs(ax)<=0.2 and abs(ad)<=0.2)
        min_with_offset=max(min_q,eff_len+self._fq_offset_mm)
        if not ok and eff_len < min_q - 1e-6:
            if both_zero and eff_len + self._fq_offset_mm >= min_q - 1e-6:
                self._fq_state={"active":True,"phase":"offset","final_target":float(min_with_offset),
                                "ax":float(ax),"ad":float(ad),"profile":profile,"element":element,"min_q":float(min_q)}
                self._show_banner("Offset Fuori quota","warn")
                self._set_pressers(False,False)
                self._position_machine_exact(min_with_offset,ax,ad,profile,element)
                with contextlib.suppress(Exception):
                    setattr(self.machine,"semi_auto_target_pieces",1); setattr(self.machine,"semi_auto_count_done",0)
                return
            self._fq_state={"active":True,"phase":"intest","final_target":float(min_with_offset),
                            "ax":float(ax),"ad":float(ad),"profile":profile,"element":element,"min_q":float(min_q)}
            self._show_banner("Intestatura Fuori quota (DX)","warn")
            self._set_pressers(False,False)
            self._position_machine_exact(min_q,ax,ad,profile,element)
            with contextlib.suppress(Exception):
                setattr(self.machine,"semi_auto_target_pieces",1); setattr(self.machine,"semi_auto_count_done",0)
            return
        self._hide_banner()
        self._set_pressers(False,False)
        self._position_machine_exact(target_len,ax,ad,profile,element)
        with contextlib.suppress(Exception):
            setattr(self.machine,"semi_auto_target_pieces",1); setattr(self.machine,"semi_auto_count_done",0)

    def _maybe_force_lock(self):
        if not self._brake_locked:
            in_mov = bool(getattr(self.machine,"positioning_active",False))
            if not in_mov:
                self._lock_brake()

    # ---------- Inpos / brake ----------
    def _try_lock_on_inpos(self):
        if not self._lock_on_inpos: return
        tol=float(read_settings().get("inpos_tol_mm",0.20))
        pos=getattr(self.machine,"encoder_position",None)
        if pos is None: pos=getattr(self.machine,"position_current",None)
        try: posf=float(pos)
        except Exception: posf=None
        in_mov=bool(getattr(self.machine,"positioning_active",False))
        in_pos=(posf is not None) and (abs(posf-self._move_target_mm)<=tol)
        if in_pos and not in_mov:
            now=time.time()
            if self._inpos_since==0.0:
                self._inpos_since=now; return
            if (now-self._inpos_since)<0.10: return
            self._lock_brake(); self._lock_on_inpos=False

    def _lock_brake(self):
        with contextlib.suppress(Exception):
            if hasattr(self.machine,"set_output"): self.machine.set_output("head_brake",True)
            else: setattr(self.machine,"brake_active",True)
            self._brake_locked=True

    def _unlock_brake(self,silent:bool=False):
        with contextlib.suppress(Exception):
            if hasattr(self.machine,"set_output"): self.machine.set_output("head_brake",False)
            else: setattr(self.machine,"brake_active",False)
            self._brake_locked=False

    # ---------- Contatori ----------
    def _sig_remaining_from_table(self,sig:Tuple[str,float,float,float])->int:
        prof,L2,ax1,ad1=sig
        rem=0
        for r in range(self.tbl_cut.rowCount()):
            if self._row_is_header(r): continue
            try:
                p=(self.tbl_cut.item(r,1).text() or "").strip()
                L=round(float(self.tbl_cut.item(r,3).text()),2)
                ax=round(float(self.tbl_cut.item(r,4).text()),1)
                ad=round(float(self.tbl_cut.item(r,5).text()),1)
                q=int((self.tbl_cut.item(r,6).text() or "0").strip())
            except Exception: continue
            if p==prof and L==L2 and ax==ax1 and ad==ad1: rem+=max(0,q)
        return rem

    def _update_counters_ui(self):
        if self._mode=="plan" and self._cur_sig:
            total=int(self._sig_total_counts.get(self._cur_sig,0))
            remaining=self._sig_remaining_from_table(self._cur_sig)
            done=max(0,total-remaining)
            self.lbl_target.setText(str(total))
            self.lbl_done.setText(str(done))
            self.lbl_remaining.setText(str(remaining))
        elif self._mode=="manual":
            done=int(getattr(self.machine,"semi_auto_count_done",0) or 0)
            rem=max(1-done,0)
            self.lbl_target.setText("1")
            self.lbl_done.setText(str(done))
            self.lbl_remaining.setText(str(rem))
        else:
            done_m=int(getattr(self.machine,"semi_auto_count_done",0) or 0)
            target_m=int(getattr(self.machine,"semi_auto_target_pieces",0) or 0)
            rem_m=max(target_m-done_m,0)
            self.lbl_target.setText(str(target_m))
            self.lbl_done.setText(str(done_m))
            self.lbl_remaining.setText(str(rem_m))

    # ---------- Tabella eventi ----------
    def _row_is_header(self,row:int)->bool:
        it=self.tbl_cut.item(row,1)
        return bool(it) and not bool(it.flags() & Qt.ItemIsSelectable)

    def _on_cell_double_clicked(self,row:int,col:int):
        if self._mode=="manual" and not self._row_is_header(row):
            try:
                piece={
                    "profile": (self.tbl_cut.item(row,1).text() or "").strip(),
                    "element": (self.tbl_cut.item(row,2).text() or "").strip(),
                    "len": float(self.tbl_cut.item(row,3).text()),
                    "ax": float(self.tbl_cut.item(row,4).text()),
                    "ad": float(self.tbl_cut.item(row,5).text()),
                    "seq_id":0,"meta":{}
                }
            except Exception:
                return
            self._move_and_arm(piece["len"],piece["ax"],piece["ad"],piece["profile"],piece["element"])
            self._apply_active_row(row)
            self.activePieceChanged.emit({**piece,"mode":"manual"})
            with contextlib.suppress(Exception):
                setattr(self.machine,"semi_auto_target_pieces",1); setattr(self.machine,"semi_auto_count_done",0)
            self._manual_current_piece=piece
            self._mode="manual"
            self._update_counters_ui()
            return
        if self._row_is_header(row) and self._mode!="manual":
            profile=self.tbl_cut.item(row,1).text().strip()
            if profile:
                self._optimize_profile(profile); self._open_opt_dialog(profile)

    def _on_cell_entered(self,row:int,col:int):
        if row<0 or self._row_is_header(row) or col!=6: return
        it=self.tbl_cut.item(row,6)
        if not it: return
        try: q=int((it.text() or "0").strip())
        except Exception: q=0
        if q==0:
            QToolTip.showText(QCursor.pos(),"Riga completata (Q=0).",self.tbl_cut)

    def _on_current_cell_changed(self,cur_row:int,_cur_col:int,_prev_row:int,_prev_col:int):
        try:
            if cur_row is None or cur_row<0 or self._row_is_header(cur_row): return
            prof_item=self.tbl_cut.item(cur_row,1)
            if not prof_item: return
            name=(prof_item.text() or "").strip()
            self._current_profile_thickness=self._get_profile_thickness(name)
        except Exception:
            self._current_profile_thickness=0.0

    def keyPressEvent(self,event:QKeyEvent):
        if event.key()==Qt.Key_F7:
            self._simulate_cut_once(); event.accept(); return
        if event.key()==Qt.Key_Space:
            self._handle_start_trigger(); event.accept(); return
        super().keyPressEvent(event)

    # ---------- Ciclo show/hide ----------
    def on_show(self):
        with contextlib.suppress(Exception):
            if hasattr(self.machine,"set_active_mode"): self.machine.set_active_mode("semi")
        if self._poll is None:
            self._poll=QTimer(self); self._poll.timeout.connect(self._tick); self._poll.start(70)
        if self.status:
            with contextlib.suppress(Exception): self.status.refresh()
        self._update_counters_ui(); self._update_quota_label()

    def _tick(self):
        with contextlib.suppress(Exception): self.status.refresh()
        self._try_lock_on_inpos()
        pressed=self._read_start_button()
        if pressed and not self._start_prev: self._handle_start_trigger()
        self._start_prev=pressed
        blade=self._read_blade_pulse()
        if blade and not self._blade_prev: self._simulate_cut_once()
        self._blade_prev=blade
        self._update_quota_label()
        self._update_counters_ui()

    def hideEvent(self,ev):
        if self._poll:
            with contextlib.suppress(Exception): self._poll.stop()
            self._poll=None
        self._unlock_brake(silent=True)
        self._set_pressers(True,True)
        self._hide_banner()
        super().hideEvent(ev)

    def _update_quota_label(self):
        if not self.lbl_quota_card: return
        enc=getattr(self.machine,"encoder_position",None)
        if enc is None: enc=getattr(self.machine,"position_current",None)
        try: val=float(enc); self.lbl_quota_card.setText(f"{val:.2f} mm")
        except Exception:
            self.lbl_quota_card.setText("— mm")

    # ---------- IO helpers ----------
    def _read_input(self,key:str)->bool:
        try:
            if hasattr(self.machine,"read_input") and callable(getattr(self.machine,"read_input")):
                return bool(self.machine.read_input(key))
            if hasattr(self.machine,key):
                return bool(getattr(self.machine,key))
        except Exception: return False
        return False

    def _read_blade_pulse(self)->bool:
        for k in ("blade_cut","blade_pulse","cut_pulse","lama_pulse","blade_out_pulse","blade_counter"):
            if self._read_input(k): return True
        return False

    def _read_start_button(self)->bool:
        for k in ("start_mobile","mobile_start_pressed","start_pressed"):
            if self._read_input(k): return True
        return False

    # ---------- Navigazione / reset ----------
    def _nav_home(self)->bool:
        if self._opt_dialog:
            with contextlib.suppress(Exception): self._opt_dialog.close()
            self._opt_dialog=None
        if hasattr(self.appwin,"show_page"):
            with contextlib.suppress(Exception): self.appwin.show_page("home"); return True
        return False

    def _reset_and_home(self):
        if self._opt_dialog:
            with contextlib.suppress(Exception): self._opt_dialog.close()
            self._opt_dialog=None
        with contextlib.suppress(Exception): self.seq.stop()
        self._mode="idle"
        self._bars.clear()
        self._seq_plan.clear()
        self._seq_pos=-1
        self._brake_locked=False
        self._move_target_mm=0.0
        self._inpos_since=0.0
        self._lock_on_inpos=False
        self._sig_total_counts.clear()
        self._cur_sig=None
        self._fq_state={"active":False,"phase":"","final_target":0.0,"ax":0.0,"ad":0.0,"profile":"","element":"","min_q":0.0}
        self._active_row=None
        if self.tbl_cut: self.tbl_cut.setRowCount(0)
        self._hide_banner()
        self._update_counters_ui()
        self._nav_home()

    # ---------- Packing fallback ----------
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

    # ---------- Helpers static ----------
    @staticmethod
    def _sig_key(profile:str,length:float,ax:float,ad:float)->Tuple[str,float,float,float]:
        return (str(profile or ""),round(float(length),2),round(float(ax),1),round(float(ad),1))

    def _on_step_started(self,idx:int,step:dict): pass
    def _on_step_finished(self,idx:int,step:dict): pass
    def _on_seq_done(self): self._toast("Automatico: completato","ok")
