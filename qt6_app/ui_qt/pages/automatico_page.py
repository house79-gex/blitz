from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple
from collections import defaultdict
import time

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QAbstractItemView, QSizePolicy,
    QDialog, QFormLayout, QLineEdit, QComboBox, QDialogButtonBox, QCheckBox,
    QToolTip
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut, QColor, QBrush, QFont, QKeyEvent, QCursor

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

try:
    from ui_qt.utils.settings import read_settings, write_settings
except Exception:
    def read_settings() -> Dict[str, Any]: return {}
    def write_settings(d: Dict[str, Any]) -> None: pass

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

        form = QFormLayout(self)
        self.ed_stock = QLineEdit(stock)
        self.ed_stock_use = QLineEdit(stock_use)
        self.ed_kerf = QLineEdit(kerf)
        self.ed_ripasso = QLineEdit(ripasso)
        self.cmb_solver = QComboBox(); self.cmb_solver.addItems(["ILP_KNAP", "ILP", "BFD"])
        self.cmb_solver.setCurrentText("ILP_KNAP" if solver not in ("ILP", "BFD") else solver)
        self.ed_time = QLineEdit(tlimit)
        self.ed_tail_b = QLineEdit(tail_b)
        self.ed_tail_t = QLineEdit(tail_t)
        self.ed_max_ang = QLineEdit(max_ang)
        self.ed_max_factor = QLineEdit(max_factor)
        self.ed_cons_ang = QLineEdit(cons_ang)
        self.chk_reversible = QCheckBox("Profilo reversibile"); self.chk_reversible.setChecked(reversible_now)
        self.ed_thickness = QLineEdit(thickness)
        self.ed_angle_tol = QLineEdit(angle_tol)
        self.ed_warn_over = QLineEdit(warn_over)
        self.chk_auto_cont = QCheckBox("Auto-continue abilitato"); self.chk_auto_cont.setChecked(auto_cont)
        self.chk_auto_across = QCheckBox("Auto-continue attraverso barre"); self.chk_auto_across.setChecked(auto_across)

        form.addRow("Stock nominale (mm):", self.ed_stock)
        form.addRow("Stock max utilizzabile (mm):", self.ed_stock_use)
        form.addRow("Kerf base (mm):", self.ed_kerf)
        form.addRow("Ripasso per giunto (mm):", self.ed_ripasso)
        form.addRow("Solver:", self.cmb_solver)
        form.addRow("Time limit solver (s):", self.ed_time)
        form.addRow("Refine ultime barre (N):", self.ed_tail_b)
        form.addRow("Refine time (s):", self.ed_tail_t)
        form.addRow("Kerf max angolo (°):", self.ed_max_ang)
        form.addRow("Kerf max fattore:", self.ed_max_factor)
        form.addRow("Angolo conservativo knapsack (°):", self.ed_cons_ang)
        form.addRow(self.chk_reversible)
        form.addRow("Spessore profilo (mm):", self.ed_thickness)
        form.addRow("Tolleranza angolo reversibile (°):", self.ed_angle_tol)
        form.addRow("Warn overflow soglia (mm):", self.ed_warn_over)
        form.addRow(self.chk_auto_cont)
        form.addRow(self.chk_auto_across)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        btns.accepted.connect(self._save_and_close)
        btns.rejected.connect(self.reject)
        form.addRow(btns)
        self.resize(540, 630)

    def _save_and_close(self):
        cfg = dict(read_settings())
        def f(txt, d):
            try: return float((txt or "").replace(",", "."))
            except Exception: return d
        def i(txt, d):
            try: return int(float((txt or "").replace(",", ".")))
            except Exception: return d
        cfg["opt_stock_mm"] = f(self.ed_stock.text(), 6500.0)
        cfg["opt_stock_usable_mm"] = f(self.ed_stock_use.text(), 0.0)
        cfg["opt_kerf_mm"] = f(self.ed_kerf.text(), 3.0)
        cfg["opt_ripasso_mm"] = f(self.ed_ripasso.text(), 0.0)
        cfg["opt_solver"] = self.cmb_solver.currentText().upper()
        cfg["opt_time_limit_s"] = i(self.ed_time.text(), 15)
        cfg["opt_refine_tail_bars"] = i(self.ed_tail_b.text(), 6)
        cfg["opt_refine_time_s"] = i(self.ed_tail_t.text(), 25)
        cfg["opt_kerf_max_angle_deg"] = f(self.ed_max_ang.text(), 60.0)
        cfg["opt_kerf_max_factor"] = f(self.ed_max_factor.text(), 2.0)
        cfg["opt_knap_conservative_angle_deg"] = f(self.ed_cons_ang.text(), 45.0)
        cfg["opt_current_profile_reversible"] = bool(self.chk_reversible.isChecked())
        cfg["opt_current_profile_thickness_mm"] = f(self.ed_thickness.text(), 0.0)
        cfg["opt_reversible_angle_tol_deg"] = f(self.ed_angle_tol.text(), 0.5)
        cfg["opt_warn_overflow_mm"] = f(self.ed_warn_over.text(), 0.5)
        cfg["opt_auto_continue_enabled"] = bool(self.chk_auto_cont.isChecked())
        cfg["opt_auto_continue_across_bars"] = bool(self.chk_auto_across.isChecked())
        write_settings(cfg)
        self.accept()


class AutomaticoPage(QWidget):
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine

        self.plan: Dict[str, Any] = {"solver": "", "steps": []}
        self.seq = Sequencer(appwin)
        self.seq.step_started.connect(self._on_step_started)
        self.seq.step_finished.connect(self._on_step_finished)
        self.seq.finished.connect(self._on_seq_done)

        self.tbl_cut: Optional[QTableWidget] = None
        self.lbl_target: Optional[QLabel] = None
        self.lbl_done: Optional[QLabel] = None
        self.lbl_remaining: Optional[QLabel] = None
        self.status: Optional[StatusPanel] = None
        self.btn_start_row: Optional[QPushButton] = None
        self.viewer_frame: Optional[QFrame] = None

        self._orders = OrdersStore()

        self._mode: str = "idle"
        self._active_row: Optional[int] = None
        self._manual_job: Optional[Dict[str, Any]] = None
        self._finished_rows: set[int] = set()

        self._plan_profile: str = ""
        self._bars: List[List[Dict[str, float]]] = []
        self._bar_idx: int = -1
        self._piece_idx: int = -1

        self._opt_dialog: Optional[OptimizationRunDialog] = None

        self._brake_locked: bool = False
        self._blade_prev: bool = False
        self._start_prev: bool = False
        self._move_target_mm: float = 0.0
        self._inpos_since: float = 0.0
        self._lock_on_inpos: bool = False
        self._poll: Optional[QTimer] = None

        cfg = read_settings()
        self._same_len_tol = self._cfg_float(cfg, "auto_same_len_tol_mm", 0.10)
        self._same_ang_tol = self._cfg_float(cfg, "auto_same_ang_tol_deg", 0.10)

        self._kerf_max_angle_deg = self._cfg_float(cfg, "opt_kerf_max_angle_deg", 60.0)
        self._kerf_max_factor = self._cfg_float(cfg, "opt_kerf_max_factor", 2.0)
        self._knap_cons_angle_deg = self._cfg_float(cfg, "opt_knap_conservative_angle_deg", 45.0)
        self._ripasso_mm = self._cfg_float(cfg, "opt_ripasso_mm", 0.0)
        self._warn_overflow_mm = self._cfg_float(cfg, "opt_warn_overflow_mm", 0.5)

        self._auto_continue_enabled = bool(cfg.get("opt_auto_continue_enabled", False))
        self._auto_continue_across_bars = bool(cfg.get("opt_auto_continue_across_bars", False))

        self._sig_total_counts: Dict[Tuple[str, float, float, float], int] = {}
        self._cur_sig: Optional[Tuple[str, float, float, float]] = None

        self._in_item_change: bool = False
        self._qty_editing_row: int = -1

        self._build()

    @staticmethod
    def _cfg_float(cfg: Dict[str, Any], key: str, dflt: float) -> float:
        try: return float(cfg.get(key, dflt))
        except Exception: return dflt

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        root.addWidget(Header(self.appwin, "AUTOMATICO", mode="default",
                              on_home=self._nav_home, on_reset=self._reset_and_home))

        top = QHBoxLayout()
        btn_import = QPushButton("Importa…"); btn_import.clicked.connect(self._import_cutlist); top.addWidget(btn_import)
        btn_opt = QPushButton("Ottimizza"); btn_opt.clicked.connect(self._on_optimize_clicked); top.addWidget(btn_opt)
        btn_cfg = QPushButton("Config. ottimizzazione…"); btn_cfg.clicked.connect(self._open_opt_config); top.addWidget(btn_cfg)
        top.addStretch(1)
        root.addLayout(top)

        body = QHBoxLayout(); body.setContentsMargins(0, 0, 0, 0); body.setSpacing(8)
        root.addLayout(body, 1)

        left = QFrame(); left.setSizePolicy(POL_EXP, POL_EXP)
        ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0); ll.setSpacing(8)

        viewer_frame = QFrame()
        viewer_frame.setStyleSheet("QFrame { border:1px solid #3b4b5a; border-radius:6px; }")
        self.viewer_frame = viewer_frame
        vf = QVBoxLayout(viewer_frame); vf.setContentsMargins(6, 6, 6, 6); vf.setSpacing(6)

        self.tbl_cut = QTableWidget(0, 7)
        self.tbl_cut.setHorizontalHeaderLabels(["Profilo", "Elemento", "Lunghezza (mm)", "Ang SX", "Ang DX", "Q.tà", "Note"])
        hdr = self.tbl_cut.horizontalHeader()
        for i, mode in enumerate([QHeaderView.Stretch, QHeaderView.Stretch, QHeaderView.ResizeToContents,
                                  QHeaderView.ResizeToContents, QHeaderView.ResizeToContents,
                                  QHeaderView.ResizeToContents, QHeaderView.Stretch]):
            hdr.setSectionResizeMode(i, mode)
        self.tbl_cut.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_cut.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_cut.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl_cut.setAlternatingRowColors(True)
        self.tbl_cut.setStyleSheet("QTableWidget::item:selected { background:#1976d2; color:#ffffff; font-weight:700; }")
        self.tbl_cut.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.tbl_cut.setMouseTracking(True)
        self.tbl_cut.cellEntered.connect(self._on_cell_entered)
        self.tbl_cut.itemChanged.connect(self._on_item_changed)

        vf.addWidget(self.tbl_cut, 1)
        ll.addWidget(viewer_frame, 1)

        start_row = QHBoxLayout(); start_row.addStretch(1)
        self.btn_start_row = QPushButton("Start")
        self.btn_start_row.setMinimumHeight(48)
        self.btn_start_row.setStyleSheet(
            "QPushButton { background:#2ecc71; color:white; font-weight:800; font-size:18px; padding:12px 32px; border-radius:10px; } "
            "QPushButton:hover { background:#27ae60; } QPushButton:pressed { background:#239b56; }"
        )
        self.btn_start_row.clicked.connect(self._start_row)
        start_row.addWidget(self.btn_start_row, 0, Qt.AlignCenter)
        start_row.addStretch(1)
        ll.addLayout(start_row)

        body.addWidget(left, 1)

        right = QFrame(); right.setFixedWidth(PANEL_W)
        rl = QVBoxLayout(right); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(8)

        cnt_box = QFrame(); cnt_box.setFrameShape(QFrame.StyledPanel)
        cnt_box.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius: 6px; }")
        cnl = QVBoxLayout(cnt_box); cnl.setContentsMargins(12, 12, 12, 12)
        title_cnt = QLabel("NUMERO PEZZI"); title_cnt.setStyleSheet("font-weight:800; font-size:16px;")
        cnl.addWidget(title_cnt)
        big = "font-size:24px; font-weight:800;"
        row1 = QHBoxLayout(); row1.addWidget(QLabel("Target:")); self.lbl_target = QLabel("0"); self.lbl_target.setStyleSheet(big); row1.addWidget(self.lbl_target); row1.addStretch(1)
        row2 = QHBoxLayout(); row2.addWidget(QLabel("Tagliati:")); self.lbl_done = QLabel("0"); self.lbl_done.setStyleSheet(big + "color:#2ecc71;"); row2.addWidget(self.lbl_done); row2.addStretch(1)
        row3 = QHBoxLayout(); row3.addWidget(QLabel("Rimanenti:")); self.lbl_remaining = QLabel("-"); self.lbl_remaining.setStyleSheet(big + "color:#f39c12;"); row3.addWidget(self.lbl_remaining); row3.addStretch(1)
        cnl.addLayout(row1); cnl.addLayout(row2); cnl.addLayout(row3)
        rl.addWidget(cnt_box, 0)

        status_wrap = QFrame(); status_wrap.setFrameShape(QFrame.StyledPanel)
        status_wrap.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius: 6px; }")
        swl = QVBoxLayout(status_wrap); swl.setContentsMargins(6, 6, 6, 6)
        self.status = StatusPanel(self.machine, "STATO", status_wrap)
        swl.addWidget(self.status)
        rl.addWidget(status_wrap, 0)
        rl.addStretch(1)

        body.addWidget(right, 0)

        QShortcut(QKeySequence("Space"), self, activated=self._handle_start_trigger)

    def _row_is_header(self, row: int) -> bool:
        it = self.tbl_cut.item(row, 0)
        return bool(it) and not bool(it.flags() & Qt.ItemIsSelectable)

    def _find_first_header_profile(self) -> Optional[str]:
        for r in range(self.tbl_cut.rowCount()):
            if self._row_is_header(r):
                it = self.tbl_cut.item(r, 0)
                if it:
                    return it.text().strip()
        return None

    @staticmethod
    def _sig_key(profile: str, length: float, ax: float, ad: float) -> Tuple[str, float, float, float]:
        return (str(profile or ""), round(float(length), 2), round(float(ax), 1), round(float(ad), 1))

    def _close_opt_dialog(self):
        if self._opt_dialog:
            try: self._opt_dialog.close()
            except Exception: pass
            self._opt_dialog = None

    def _nav_home(self) -> bool:
        self._close_opt_dialog()
        if hasattr(self.appwin, "show_page"):
            try: self.appwin.show_page("home"); return True
            except Exception: pass
        return False

    def _reset_and_home(self):
        self._close_opt_dialog()
        try: self.seq.stop()
        except Exception: pass
        self.plan = {"solver": "", "steps": []}
        self._mode = "idle"; self._active_row = None; self._manual_job = None
        self._finished_rows.clear()
        self._bars.clear(); self._bar_idx = -1; self._piece_idx = -1
        self._brake_locked = False; self._blade_prev = False; self._start_prev = False
        self._move_target_mm = 0.0; self._inpos_since = 0.0; self._lock_on_inpos = False
        self._sig_total_counts.clear(); self._cur_sig = None
        if self.tbl_cut: self.tbl_cut.setRowCount(0)
        self._update_counters_ui()

    def _import_cutlist(self):
        dlg = OrdersManagerDialog(self, self._orders)
        if dlg.exec() and getattr(dlg, "selected_order_id", None):
            ord_item = self._orders.get_order(int(dlg.selected_order_id))
            if not ord_item:
                QMessageBox.critical(self, "Importa", "Ordine non trovato."); return
            data = ord_item.get("data") or {}
            if data.get("type") != "cutlist":
                QMessageBox.information(self, "Importa", "Seleziona un ordine di tipo cutlist."); return
            cuts = data.get("cuts") or []
            if not cuts:
                QMessageBox.information(self, "Importa", "Lista di taglio vuota."); return
            self._load_cutlist(cuts)

    def _header_items(self, profile: str) -> List[QTableWidgetItem]:
        font = QFont(); font.setBold(True)
        bg = QBrush(QColor("#ecf0f1"))
        items: List[QTableWidgetItem] = []
        itp = QTableWidgetItem(profile or "—"); itp.setFont(font); itp.setBackground(bg); itp.setForeground(QBrush(Qt.black)); itp.setFlags(Qt.ItemIsEnabled)
        items.append(itp)
        for _ in range(6):
            it = QTableWidgetItem(""); it.setFont(font); it.setBackground(bg); it.setFlags(Qt.ItemIsEnabled)
            items.append(it)
        return items

    def _load_cutlist(self, cuts: List[Dict[str, Any]]):
        self.tbl_cut.setRowCount(0)
        groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        order: List[str] = []
        for c in cuts:
            p = str(c.get("profile", "")).strip()
            if p not in groups: order.append(p)
            groups[p].append(c)
        for prof in order:
            r = self.tbl_cut.rowCount(); self.tbl_cut.insertRow(r)
            for col, it in enumerate(self._header_items(prof)):
                self.tbl_cut.setItem(r, col, it)
            for c in groups[prof]:
                r = self.tbl_cut.rowCount(); self.tbl_cut.insertRow(r)
                cells = [
                    QTableWidgetItem(str(c.get("profile",""))),
                    QTableWidgetItem(str(c.get("element",""))),
                    QTableWidgetItem(f"{float(c.get('length_mm',0.0)):.2f}"),
                    QTableWidgetItem(f"{float(c.get('ang_sx',0.0)):.1f}"),
                    QTableWidgetItem(f"{float(c.get('ang_dx',0.0)):.1f}"),
                    QTableWidgetItem(str(int(c.get("qty",0)))),
                    QTableWidgetItem(str(c.get("note","")))
                ]
                for it in cells:
                    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                for col, it in enumerate(cells):
                    self.tbl_cut.setItem(r, col, it)
        self._mode = "idle"; self._active_row = None; self._manual_job = None
        self._finished_rows.clear(); self._sig_total_counts.clear(); self._cur_sig = None
        self._update_counters_ui()

    def _on_optimize_clicked(self):
        prof = None
        r = self.tbl_cut.currentRow()
        if r is not None and r >= 0 and self._row_is_header(r):
            it = self.tbl_cut.item(r, 0); prof = it.text().strip() if it else None
        if not prof:
            prof = self._find_first_header_profile()
        if not prof:
            QMessageBox.information(self, "Ottimizza", "Seleziona un profilo o importa una lista."); return
        self._optimize_profile(prof)
        self._open_opt_dialog(prof)

    def _on_cell_double_clicked(self, row: int, col: int):
        if self._row_is_header(row):
            profile = self.tbl_cut.item(row, 0).text().strip()
            if profile:
                self._optimize_profile(profile)
                self._open_opt_dialog(profile)
            return
        if col == 5:
            it = self.tbl_cut.item(row, 5)
            if it:
                try:
                    q = int((it.text() or "0").strip())
                except Exception:
                    q = 0
                if q == 0:
                    it.setFlags(it.flags() | Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    self.tbl_cut.setCurrentItem(it)
                    self.tbl_cut.openPersistentEditor(it)
                    self._qty_editing_row = row
                    return

    def _open_opt_config(self):
        dlg = OptimizationConfigDialog(self)
        dlg.exec()
        self._toast("Config ottimizzazione aggiornata.", "ok")
        cfg = read_settings()
        self._kerf_max_angle_deg = self._cfg_float(cfg, "opt_kerf_max_angle_deg", 60.0)
        self._kerf_max_factor = self._cfg_float(cfg, "opt_kerf_max_factor", 2.0)
        self._knap_cons_angle_deg = self._cfg_float(cfg, "opt_knap_conservative_angle_deg", 45.0)
        self._ripasso_mm = self._cfg_float(cfg, "opt_ripasso_mm", 0.0)
        self._warn_overflow_mm = self._cfg_float(cfg, "opt_warn_overflow_mm", 0.5)
        self._auto_continue_enabled = bool(cfg.get("opt_auto_continue_enabled", False))
        self._auto_continue_across_bars = bool(cfg.get("opt_auto_continue_across_bars", False))

    def _open_opt_dialog(self, profile: str):
        prof = (profile or "").strip()
        if not prof: return
        rows: List[Dict[str, Any]] = []
        for r in range(self.tbl_cut.rowCount()):
            if self._row_is_header(r): continue
            if self.tbl_cut.item(r, 0) and self.tbl_cut.item(r, 0).text().strip() == prof:
                try:
                    L = float(self.tbl_cut.item(r, 2).text())
                    ax = float(self.tbl_cut.item(r, 3).text())
                    ad = float(self.tbl_cut.item(r, 4).text())
                    q = int(self.tbl_cut.item(r, 5).text())
                except Exception:
                    continue
                if q > 0:
                    rows.append({"length_mm": round(L, 2), "ang_sx": ax, "ang_dx": ad, "qty": q})
        if not rows: return
        if self._opt_dialog and self._opt_dialog.profile == prof:
            try: self._opt_dialog.raise_(); self._opt_dialog.activateWindow()
            except Exception: pass
            return

        self._opt_dialog = OptimizationRunDialog(self, prof, rows, overlay_target=self.viewer_frame)
        try: self._opt_dialog.simulationRequested.connect(self.simulate_cut_from_dialog)
        except Exception: pass
        try: self._opt_dialog.startRequested.connect(self._handle_start_trigger)
        except Exception: pass
        self._opt_dialog.finished.connect(lambda _p: setattr(self, "_opt_dialog", None))
        self._opt_dialog.show()
        self._toast("Ottimizzazione aperta (F9 avanzamento, F7 taglio).", "info")

    def _start_row(self):
        r = self.tbl_cut.currentRow()
        if r < 0:
            QMessageBox.information(self, "Start", "Seleziona una riga."); return
        if self._row_is_header(r):
            QMessageBox.information(self, "Start", "Seleziona un elemento (non intestazione)."); return
        try:
            prof = self.tbl_cut.item(r, 0).text().strip()
            elem = self.tbl_cut.item(r, 1).text().strip()
            L = float(self.tbl_cut.item(r, 2).text())
            ax = float(self.tbl_cut.item(r, 3).text())
            ad = float(self.tbl_cut.item(r, 4).text())
            qty = int(self.tbl_cut.item(r, 5).text())
        except Exception:
            QMessageBox.critical(self, "Start", "Riga non valida."); return
        if qty <= 0:
            QMessageBox.information(self, "Start", "Quantità esaurita."); return

        try:
            setattr(self.machine, "semi_auto_target_pieces", int(qty))
            setattr(self.machine, "semi_auto_count_done", 0)
        except Exception: pass

        self._mode = "manual"; self._active_row = r
        self._manual_job = {"profile": prof, "element": elem, "length": L, "ax": ax, "ad": ad}
        self._cur_sig = None
        self._move_and_arm(L, ax, ad, prof, elem)
        self._update_counters_ui()

    def _optimize_profile(self, profile: str):
        prof = (profile or "").strip()
        if not prof:
            QMessageBox.information(self, "Ottimizza", "Seleziona un profilo."); return

        items: Dict[Tuple[float, float, float], int] = defaultdict(int)
        for r in range(self.tbl_cut.rowCount()):
            if self._row_is_header(r): continue
            if self.tbl_cut.item(r, 0) and self.tbl_cut.item(r, 0).text().strip() == prof:
                try:
                    L = round(float(self.tbl_cut.item(r, 2).text()), 2)
                    ax = float(self.tbl_cut.item(r, 3).text())
                    ad = float(self.tbl_cut.item(r, 4).text())
                    q = int(self.tbl_cut.item(r, 5).text())
                except Exception:
                    continue
                if q > 0: items[(L, ax, ad)] += q
        if not items:
            QMessageBox.information(self, "Ottimizza", f"Nessun pezzo per '{prof}'."); return

        cfg = read_settings()
        stock_nom = self._cfg_float(cfg, "opt_stock_mm", 6500.0)
        stock_usable = self._cfg_float(cfg, "opt_stock_usable_mm", 0.0)
        stock = stock_usable if stock_usable > 0 else stock_nom
        kerf_base = self._cfg_float(cfg, "opt_kerf_mm", 3.0)
        solver = str(cfg.get("opt_solver", "ILP_KNAP")).upper()
        per_bar_time = self._cfg_float(cfg, "opt_time_limit_s", 15.0)
        tail_n = int(self._cfg_float(cfg, "opt_refine_tail_bars", 6.0))
        tail_t = int(self._cfg_float(cfg, "opt_refine_time_s", 25.0))
        reversible_now = bool(cfg.get("opt_current_profile_reversible", False))
        thickness_mm = self._cfg_float(cfg, "opt_current_profile_thickness_mm", 0.0)
        angle_tol = self._cfg_float(cfg, "opt_reversible_angle_tol_deg", 0.5)

        pieces: List[Dict[str, float]] = []
        for (L, ax, ad), q in items.items():
            for _ in range(q):
                pieces.append({"len": float(L), "ax": float(ax), "ad": float(ad)})
        pieces.sort(key=lambda x: x["len"], reverse=True)

        max_angle = self._kerf_max_angle_deg
        max_factor = self._kerf_max_factor

        if solver in ("ILP_KNAP", "ILP"):
            bars, rem = pack_bars_knapsack_ilp(
                pieces=pieces,
                stock=stock,
                kerf_base=kerf_base,
                ripasso_mm=self._ripasso_mm,
                conservative_angle_deg=self._knap_cons_angle_deg,
                max_angle=max_angle,
                max_factor=max_factor,
                reversible=reversible_now,
                thickness_mm=thickness_mm,
                angle_tol=angle_tol,
                per_bar_time_s=int(per_bar_time)
            )
            if not bars:
                bars, rem = self._pack_bfd(pieces, stock, kerf_base,
                                           reversible_now, thickness_mm,
                                           angle_tol, max_angle, max_factor)
        else:
            bars, rem = self._pack_bfd(pieces, stock, kerf_base,
                                       reversible_now, thickness_mm,
                                       angle_tol, max_angle, max_factor)

        try:
            bars, rem = refine_tail_ilp(bars, stock, kerf_base,
                                        self._ripasso_mm,
                                        reversible_now, thickness_mm,
                                        angle_tol,
                                        tail_bars=tail_n, time_limit_s=tail_t,
                                        max_angle=max_angle, max_factor=max_factor)
        except Exception:
            pass

        fixed_bars: List[List[Dict[str, float]]] = []
        overflow: List[Dict[str, float]] = []  # CORRETTO QUI
        for bar in bars:
            b = list(bar)
            while b and bar_used_length(b, kerf_base, self._ripasso_mm,
                                       reversible_now, thickness_mm,
                                       angle_tol, max_angle, max_factor) > stock + 1e-6:
                overflow.append(b.pop())
            fixed_bars.append(b)

        if overflow:
            overflow.sort(key=lambda x: x["len"], reverse=True)
            for piece in overflow:
                placed = False
                for fb in fixed_bars:
                    used = bar_used_length(fb, kerf_base, self._ripasso_mm,
                                           reversible_now, thickness_mm,
                                           angle_tol, max_angle, max_factor)
                    extra = joint_consumption(fb[-1], kerf_base, self._ripasso_mm,
                                              reversible_now, thickness_mm,
                                              angle_tol, max_angle, max_factor)[0] if fb else 0.0
                    if used + piece["len"] + extra <= stock + 1e-6:
                        fb.append(piece); placed = True; break
                if not placed:
                    fixed_bars.append([piece])

        bars = fixed_bars
        rem = residuals(bars, stock, kerf_base, self._ripasso_mm,
                        reversible_now, thickness_mm,
                        angle_tol, max_angle, max_factor)

        bars.sort(key=lambda b: max((p["len"] for p in b), default=0.0), reverse=True)

        self._plan_profile = prof; self._bars = bars; self._bar_idx = 0; self._piece_idx = -1
        self._mode = "plan"; self._cur_sig = None

        self._sig_total_counts.clear()
        for (L, ax, ad), qty in items.items():
            self._sig_total_counts[self._sig_key(prof, L, ax, ad)] = int(qty)

        self._auto_continue_across_bars = False

        self._update_counters_ui()
        self._toast(f"Piano ottimizzato per {prof}. Barre: {len(bars)}.", "info")

    def _pack_bfd(self, pieces: List[Dict[str, float]], stock: float, kerf_base: float,
                  reversible: bool, thickness_mm: float, angle_tol: float,
                  max_angle: float, max_factor: float) -> Tuple[List[List[Dict[str, float]]], List[float]]:
        bars: List[List[Dict[str, float]]] = []
        for p in pieces:
            need = p["len"]; placed = False
            for b in bars:
                used = bar_used_length(b, kerf_base, self._ripasso_mm,
                                       reversible, thickness_mm,
                                       angle_tol, max_angle, max_factor)
                extra = joint_consumption(b[-1], kerf_base, self._ripasso_mm,
                                          reversible, thickness_mm,
                                          angle_tol, max_angle, max_factor)[0] if b else 0.0
                if used + need + (extra if b else 0.0) <= stock + 1e-6:
                    b.append(p); placed = True; break
            if not placed:
                bars.append([p])
        rem = residuals(bars, stock, kerf_base, self._ripasso_mm,
                        reversible, thickness_mm,
                        angle_tol, max_angle, max_factor)
        return bars, rem

    def _move_and_arm(self, length: float, ax: float, ad: float, profile: str, element: str):
        self._unlock_brake(silent=True)
        if hasattr(self.machine, "set_active_mode"):
            try: self.machine.set_active_mode("semi")
            except Exception: pass
        try:
            if hasattr(self.machine, "position_for_cut"):
                self.machine.position_for_cut(float(length), float(ax), float(ad), profile, element)
            elif hasattr(self.machine, "move_to_length_and_angles"):
                self.machine.move_to_length_and_angles(length_mm=float(length), ang_sx=float(ax), ang_dx=float(ad))
            elif hasattr(self.machine, "move_to_length"):
                self.machine.move_to_length(float(length))
            else:
                setattr(self.machine, "position_current", float(length))
        except Exception as e:
            QMessageBox.critical(self, "Posizionamento", str(e)); return
        self._move_target_mm = float(length); self._inpos_since = 0.0; self._lock_on_inpos = True
        if self._is_dummy():
            QTimer.singleShot(150, lambda: self._ensure_test_lock(1, 1))

    def _is_dummy(self) -> bool:
        try:
            n = type(self.machine).__name__.lower()
            return ("dummy" in n) or ("mock" in n)
        except Exception:
            return (not hasattr(self.machine, "encoder_position")) and (not hasattr(self.machine, "positioning_active"))

    def _ensure_test_lock(self, tgt: int, remaining: int):
        if self._is_dummy() and (tgt > 0) and (remaining > 0) and not self._brake_locked:
            self._lock_brake(); self._lock_on_inpos = False

    def _try_lock_on_inpos(self):
        if not self._lock_on_inpos: return
        if self._is_dummy():
            self._lock_brake(); self._lock_on_inpos = False; return
        tol = float(read_settings().get("inpos_tol_mm", 0.20))
        pos = getattr(self.machine, "encoder_position", None)
        if pos is None: pos = getattr(self.machine, "position_current", None)
        try: posf = float(pos)
        except Exception: posf = None
        in_mov = bool(getattr(self.machine, "positioning_active", False))
        in_pos = (posf is not None) and (abs(posf - self._move_target_mm) <= tol)
        if in_pos and not in_mov:
            now = time.time()
            if self._inpos_since == 0.0:
                self._inpos_since = now; return
            if (now - self._inpos_since) < 0.10:
                return
            self._lock_brake(); self._lock_on_inpos = False

    def _lock_brake(self):
        try:
            if hasattr(self.machine, "set_output"): self.machine.set_output("head_brake", True)
            elif hasattr(self.machine, "head_brake_lock"): self.machine.head_brake_lock()
            else: setattr(self.machine, "brake_active", True)
            self._brake_locked = True
        except Exception: pass

    def _unlock_brake(self, silent: bool = False):
        try:
            if hasattr(self.machine, "set_output"): self.machine.set_output("head_brake", False)
            elif hasattr(self.machine, "head_brake_unlock"): self.machine.head_brake_unlock()
            else: setattr(self.machine, "brake_active", False)
            self._brake_locked = False
        except Exception: pass

    def _auto_continue_enabled_fn(self) -> bool:
        return bool(self._auto_continue_enabled)

    def _same_job(self, p1: Dict[str, float], p2: Dict[str, float]) -> bool:
        try:
            return (abs(p1["len"] - p2["len"]) <= self._same_len_tol and
                    abs(p1["ax"] - p2["ax"]) <= self._same_ang_tol and
                    abs(p1["ad"] - p2["ad"]) <= self._same_ang_tol)
        except Exception:
            return False

    def _sig_remaining_from_table(self, sig: Tuple[str, float, float, float]) -> int:
        prof, L2, ax1, ad1 = sig
        rem = 0
        for r in range(self.tbl_cut.rowCount()):
            if self._row_is_header(r): continue
            try:
                p = self.tbl_cut.item(r, 0).text().strip()
                L = round(float(self.tbl_cut.item(r, 2).text()), 2)
                ax = round(float(self.tbl_cut.item(r, 3).text()), 1)
                ad = round(float(self.tbl_cut.item(r, 4).text()), 1)
                q = int(self.tbl_cut.item(r, 5).text())
            except Exception:
                continue
            if p == prof and L == L2 and ax == ax1 and ad == ad1:
                rem += max(0, q)
        return rem

    def _sum_remaining_for_profile(self, profile: str) -> int:
        prof = (profile or "").strip()
        tot = 0
        for r in range(self.tbl_cut.rowCount()):
            if self._row_is_header(r): continue
            try:
                p = self.tbl_cut.item(r, 0).text().strip()
                q = int(self.tbl_cut.item(r, 5).text())
            except Exception:
                continue
            if p == prof:
                tot += max(0, q)
        return tot

    def _peek_next_piece_global(self) -> Optional[Dict[str, float]]:
        if not self._bars or self._bar_idx >= len(self._bars): return None
        bar = self._bars[self._bar_idx]
        idx = self._piece_idx + 1
        if idx < len(bar): return bar[idx]
        nb = self._bar_idx + 1
        if nb >= len(self._bars): return None
        next_bar = self._bars[nb]
        return next_bar[0] if next_bar else None

    def _get_next_indices(self) -> Optional[Tuple[int, int]]:
        if not self._bars or self._bar_idx >= len(self._bars): return None
        idx = self._piece_idx + 1
        if idx < len(self._bars[self._bar_idx]): return (self._bar_idx, idx)
        nb = self._bar_idx + 1
        if nb >= len(self._bars): return None
        return (nb, 0)

    def _read_input(self, key: str) -> bool:
        try:
            if hasattr(self.machine, "read_input") and callable(getattr(self.machine, "read_input")):
                return bool(self.machine.read_input(key))
            if hasattr(self.machine, key):
                return bool(getattr(self.machine, key))
        except Exception:
            return False
        return False

    def _read_blade_pulse(self) -> bool:
        for k in ("blade_cut", "blade_pulse", "cut_pulse", "lama_pulse"):
            if self._read_input(k): return True
        return False

    def _read_start_button(self) -> bool:
        for k in ("start_mobile", "mobile_start_pressed", "start_pressed"):
            if self._read_input(k): return True
        return False

    def _handle_start_trigger(self):
        if self._mode != "plan" or not self._bars: return
        tgt = int(getattr(self.machine, "semi_auto_target_pieces", 0) or 0)
        done = int(getattr(self.machine, "semi_auto_count_done", 0) or 0)
        if self._brake_locked and tgt > 0 and done < tgt:
            return

        if self._bar_idx < 0: self._bar_idx = 0
        if self._bar_idx >= len(self._bars):
            self._toast("Piano completato", "ok")
            if self._opt_dialog:
                try: self._opt_dialog.accept()
                except Exception:
                    try: self._opt_dialog.close()
                    except Exception: pass
                self._opt_dialog = None
            return

        bar = self._bars[self._bar_idx]
        self._piece_idx += 1
        if self._piece_idx >= len(bar):
            self._bar_idx += 1
            self._piece_idx = 0
            if self._bar_idx >= len(self._bars):
                self._toast("Piano completato", "ok")
                if self._opt_dialog:
                    try: self._opt_dialog.accept()
                    except Exception:
                        try: self._opt_dialog.close()
                        except Exception: pass
                    self._opt_dialog = None
                return
            bar = self._bars[self._bar_idx]

        p = bar[self._piece_idx]
        self._cur_sig = self._sig_key(self._plan_profile, p["len"], p["ax"], p["ad"])
        self._update_counters_ui()

        try:
            setattr(self.machine, "semi_auto_target_pieces", 1)
            setattr(self.machine, "semi_auto_count_done", 0)
        except Exception: pass

        self._move_and_arm(p["len"], p["ax"], p["ad"], self._plan_profile, f"BAR {self._bar_idx+1} #{self._piece_idx+1}")

    def simulate_cut_from_dialog(self):
        self._simulate_cut_once()

    def _simulate_cut_once(self):
        tgt = int(getattr(self.machine, "semi_auto_target_pieces", 0) or 0)
        done = int(getattr(self.machine, "semi_auto_count_done", 0) or 0)
        remaining = max(tgt - done, 0)

        self._ensure_test_lock(tgt, remaining)
        if not (self._brake_locked and tgt > 0 and remaining > 0):
            self._dec_selected_row_qty()
            return

        new_done = done + 1
        try: setattr(self.machine, "semi_auto_count_done", new_done)
        except Exception: pass

        cur_piece = None
        if self._mode == "plan" and self._bars and 0 <= self._bar_idx < len(self._bars):
            if 0 <= self._piece_idx < len(self._bars[self._bar_idx]):
                cur_piece = self._bars[self._bar_idx][self._piece_idx]

        if cur_piece:
            if not self._dec_row_qty_match(self._plan_profile, float(cur_piece["len"]), float(cur_piece["ax"]), float(cur_piece["ad"])):
                self._dec_row_qty_match_str(
                    self._plan_profile,
                    f"{float(cur_piece['len']):.2f}",
                    f"{float(cur_piece['ax']):.1f}",
                    f"{float(cur_piece['ad']):.1f}"
                )
        else:
            self._dec_selected_row_qty()

        if self._opt_dialog and cur_piece:
            try:
                self._opt_dialog.update_after_cut(length_mm=float(cur_piece["len"]),
                                                  ang_sx=float(cur_piece["ax"]),
                                                  ang_dx=float(cur_piece["ad"]))
            except Exception: pass

        if new_done >= tgt:
            try:
                setattr(self.machine, "semi_auto_target_pieces", 0)
                setattr(self.machine, "semi_auto_count_done", 0)
            except Exception: pass

            if self._mode == "plan":
                next_piece = self._peek_next_piece_global()
                same_next = bool(cur_piece and next_piece and self._same_job(cur_piece, next_piece))
                nxt = self._get_next_indices()
                across = bool(nxt and (nxt[0] != self._bar_idx))
                allowed = self._auto_continue_enabled_fn() and same_next and (not across or self._auto_continue_across_bars)

                if allowed and nxt is not None:
                    nb, np = nxt
                    self._bar_idx, self._piece_idx = nb, np
                    p2 = self._bars[self._bar_idx][self._piece_idx]
                    self._cur_sig = self._sig_key(self._plan_profile, p2["len"], p2["ax"], p2["ad"])
                    try:
                        setattr(self.machine, "semi_auto_target_pieces", 1)
                        setattr(self.machine, "semi_auto_count_done", 0)
                    except Exception: pass
                    self._lock_on_inpos = False
                else:
                    self._unlock_brake()

                try:
                    rem_all = self._sum_remaining_for_profile(self._plan_profile)
                except Exception:
                    rem_all = 0
                if rem_all <= 0:
                    if self._opt_dialog:
                        try: self._opt_dialog.accept()
                        except Exception:
                            try: self._opt_dialog.close()
                            except Exception: pass
                        self._opt_dialog = None
                    self._toast("Piano completato", "ok")

            elif self._mode == "manual":
                if self._active_row is not None:
                    try:
                        q_now = int(self.tbl_cut.item(self._active_row, 5).text())
                    except Exception:
                        q_now = 0
                    if q_now <= 0:
                        self._mark_row_finished(self._active_row)
                self._mode = "idle"
                self._unlock_brake()

        self._update_counters_ui()

    def _dec_selected_row_qty(self):
        try:
            r = self.tbl_cut.currentRow()
            if r is None or r < 0 or self._row_is_header(r):
                return
            itq = self.tbl_cut.item(r, 5)
            if not itq: return
            try:
                q = int((itq.text() or "0").strip())
            except Exception:
                q = 0
            if q > 0:
                q2 = q - 1
                itq.setText(str(q2))
                if q2 == 0:
                    self._mark_row_finished(r)
        except Exception:
            pass

    def _toast(self, msg: str, level: str = "info"):
        if hasattr(self.appwin, "toast"):
            try: self.appwin.toast.show(msg, level, 2500)
            except Exception: pass

    def _mark_row_finished(self, row: int):
        self._finished_rows.add(row)
        for c in range(self.tbl_cut.columnCount()):
            it = self.tbl_cut.item(row, c)
            if it:
                it.setBackground(QBrush(QColor("#2ecc71")))
                it.setForeground(QBrush(Qt.black))
        self.tbl_cut.selectRow(row)

    def _dec_row_qty_match(self, profile: str, length: float, ax: float, ad: float) -> bool:
        n = self.tbl_cut.rowCount()
        for r in range(n):
            if self._row_is_header(r): continue
            try:
                p = self.tbl_cut.item(r, 0).text().strip()
                L = float(self.tbl_cut.item(r, 2).text())
                a1 = float(self.tbl_cut.item(r, 3).text())
                a2 = float(self.tbl_cut.item(r, 4).text())
                q = int(self.tbl_cut.item(r, 5).text())
            except Exception:
                continue
            if p == profile and abs(L - length) <= 0.01 and abs(a1 - ax) <= 0.01 and abs(a2 - ad) <= 0.01:
                new_q = max(q - 1, 0)
                self.tbl_cut.setItem(r, 5, QTableWidgetItem(str(new_q)))
                if new_q == 0: self._mark_row_finished(r)
                return True
        return False

    def _dec_row_qty_match_str(self, profile: str, Ls: str, Axs: str, Ads: str) -> bool:
        n = self.tbl_cut.rowCount()
        for r in range(n):
            if self._row_is_header(r): continue
            try:
                p = self.tbl_cut.item(r, 0).text().strip()
                Ltxt = (self.tbl_cut.item(r, 2).text() or "").strip()
                Axtxt = (self.tbl_cut.item(r, 3).text() or "").strip()
                Adtxt = (self.tbl_cut.item(r, 4).text() or "").strip()
                q = int(self.tbl_cut.item(r, 5).text())
            except Exception:
                continue
            if p == profile and Ltxt == Ls and Axtxt == Axs and Adtxt == Ads:
                new_q = max(q - 1, 0)
                self.tbl_cut.setItem(r, 5, QTableWidgetItem(str(new_q)))
                if new_q == 0: self._mark_row_finished(r)
                return True
        return False

    def _update_counters_ui(self):
        if self._mode == "plan" and self._cur_sig:
            total = int(self._sig_total_counts.get(self._cur_sig, 0))
            remaining = self._sig_remaining_from_table(self._cur_sig)
            done = max(0, total - remaining)
            self.lbl_target.setText(str(total))
            self.lbl_done.setText(str(done))
            self.lbl_remaining.setText(str(remaining))
            return
        done_m = int(getattr(self.machine, "semi_auto_count_done", 0) or 0)
        target_m = int(getattr(self.machine, "semi_auto_target_pieces", 0) or 0)
        rem_m = max(target_m - done_m, 0)
        self.lbl_target.setText(str(target_m))
        self.lbl_done.setText(str(done_m))
        self.lbl_remaining.setText(str(rem_m))

    def _on_cell_entered(self, row: int, col: int):
        if row < 0 or self._row_is_header(row) or col != 5:
            return
        it = self.tbl_cut.item(row, 5)
        if not it: return
        try:
            q = int((it.text() or "0").strip())
        except Exception:
            q = 0
        if q == 0:
            QToolTip.showText(
                QCursor.pos(),
                "Quantità a zero. Doppio click sulla cella per inserire nuova quantità.",
                self.tbl_cut
            )

    def _on_item_changed(self, it: QTableWidgetItem):
        if self._in_item_change or it is None:
            return
        row = it.row(); col = it.column()
        if row < 0 or self._row_is_header(row) or col != 5:
            return
        self._in_item_change = True
        try:
            txt = (it.text() or "").strip()
            try:
                val = int(float(txt.replace(",", ".")))
            except Exception:
                val = 0
            val = max(0, val)
            if txt != str(val):
                it.setText(str(val))
            if val > 0:
                if self.tbl_cut.isPersistentEditorOpen(it):
                    self.tbl_cut.closePersistentEditor(it)
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                if self._qty_editing_row == row:
                    self._qty_editing_row = -1
            else:
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        finally:
            self._in_item_change = False

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_F7:
            self._simulate_cut_once(); event.accept(); return
        if event.key() == Qt.Key_Space and self._mode == "plan":
            self._handle_start_trigger(); event.accept(); return
        super().keyPressEvent(event)

    def on_show(self):
        if hasattr(self.machine, "set_active_mode"):
            try: self.machine.set_active_mode("semi")
            except Exception: pass
        if self._poll is None:
            self._poll = QTimer(self); self._poll.timeout.connect(self._tick); self._poll.start(70)
        if self.status: self.status.refresh()
        self._update_counters_ui()

    def _tick(self):
        try: self.status.refresh()
        except Exception: pass

        self._try_lock_on_inpos()

        pressed = self._read_start_button()
        if pressed and not self._start_prev:
            self._handle_start_trigger()
        self._start_prev = pressed

        cur_blade = self._read_blade_pulse()
        if cur_blade and not self._blade_prev:
            self._simulate_cut_once()
        self._blade_prev = cur_blade

        self._update_counters_ui()

    def hideEvent(self, ev):
        self._close_opt_dialog()
        if self._poll:
            try: self._poll.stop()
            except Exception: pass
            self._poll = None
        self._unlock_brake(silent=True)
        super().hideEvent(ev)

    def _on_step_started(self, idx: int, step: dict): pass
    def _on_step_finished(self, idx: int, step: dict): pass
    def _on_seq_done(self): self._toast("Automatico: completato", "ok")
