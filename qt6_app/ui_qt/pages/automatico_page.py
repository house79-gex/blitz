from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QComboBox, QSpinBox, QTreeWidget, QTreeWidgetItem, QTextEdit, QCheckBox, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer
from ui_qt.widgets.header import Header
from ui_qt.utils.settings import read_settings
from ui_qt.logic.planner import plan_ilp, plan_bfd
from ui_qt.logic.sequencer import Sequencer
from ui_qt.widgets.status_panel import StatusPanel

# Dimensioni allineate a Semi-Auto
PANEL_W = 420
PANEL_H = 220
COUNTER_W = 420
COUNTER_H = 150
FQ_H = 100

class AutomaticoPage(QWidget):
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine
        self.plan = {"solver": "", "steps": []}
        self.seq = Sequencer(appwin)
        self.seq.step_started.connect(self._on_step_started)
        self.seq.step_finished.connect(self._on_step_finished)
        self.seq.finished.connect(self._on_seq_done)

        self.status: Optional[StatusPanel] = None
        self._poll: Optional[QTimer] = None

        self.spin_target: Optional[QSpinBox] = None
        self.lbl_done: Optional[QLabel] = None
        self.lbl_remaining: Optional[QLabel] = None
        self.chk_fuori_quota: Optional[QCheckBox] = None

        self.log: Optional[QTextEdit] = None
        self.tree: Optional[QTreeWidget] = None

        self._build()

    # ---------------- Helpers nav/reset ----------------
    def _nav_home(self) -> bool:
        # Navigazione Home robusta
        if hasattr(self.appwin, "show_page") and callable(getattr(self.appwin, "show_page")):
            try:
                self.appwin.show_page("home")
                return True
            except Exception:
                pass
        for attr in ("go_home", "show_home", "navigate_home", "home"):
            if hasattr(self.appwin, attr) and callable(getattr(self.appwin, attr)):
                try:
                    getattr(self.appwin, attr)()
                    return True
                except Exception:
                    pass
        if hasattr(self.appwin, "nav") and hasattr(self.appwin.nav, "go_home") and callable(self.appwin.nav.go_home):
            try:
                self.appwin.nav.go_home()
                return True
            except Exception:
                pass
        return False

    def _reset_and_home(self):
        # Arresta sequenza e pulisce piano/viste; Header poi richiama Home
        try:
            self.seq.stop()
        except Exception:
            pass
        self.plan = {"solver": "", "steps": []}
        try:
            if self.tree:
                self.tree.clear()
        except Exception:
            pass
        if self.log:
            self.log.clear()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Header con Reset rosso e Home funzionanti (callback + fallback)
        root.addWidget(Header(self.appwin, "AUTOMATICO", mode="default", on_home=self._nav_home, on_reset=self._reset_and_home))

        # Controls top bar
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)
        root.addLayout(ctrl)
        ctrl.addWidget(QLabel("Solver:"))
        self.cb_solver = QComboBox()
        self.cb_solver.addItems(["ILP", "BFD"])
        cfg = read_settings()
        if str(cfg.get("solver", "ILP")).upper() in ("ILP", "BFD"):
            self.cb_solver.setCurrentText(str(cfg.get("solver", "ILP")).upper())
        ctrl.addWidget(self.cb_solver)

        ctrl.addWidget(QLabel("Time limit (s):"))
        self.spin_tl = QSpinBox()
        self.spin_tl.setRange(1, 600)
        self.spin_tl.setValue(int(cfg.get("ilp_time_limit_s", 15)))
        ctrl.addWidget(self.spin_tl)

        btn_calc = QPushButton("Calcola Piano"); btn_calc.clicked.connect(self._calc_plan)
        btn_start = QPushButton("Avvia Sequenza"); btn_start.clicked.connect(self._start_seq)
        btn_pause = QPushButton("Pausa"); btn_pause.clicked.connect(self._pause_seq)
        btn_resume = QPushButton("Riprendi"); btn_resume.clicked.connect(self._resume_seq)
        btn_stop = QPushButton("Stop"); btn_stop.clicked.connect(self._stop_seq)
        ctrl.addWidget(btn_calc); ctrl.addWidget(btn_start); ctrl.addWidget(btn_pause); ctrl.addWidget(btn_resume); ctrl.addWidget(btn_stop)
        ctrl.addStretch(1)

        # Corpo
        body = QHBoxLayout()
        body.setSpacing(8)
        root.addLayout(body, 1)

        # Sinistra: contapezzi, tree, log
        left = QFrame()
        body.addWidget(left, 1)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(6, 6, 6, 6)
        ll.setSpacing(8)

        cnt_box = QFrame()
        cnt_box.setFixedSize(COUNTER_W, COUNTER_H)
        cnt_box.setFrameShape(QFrame.StyledPanel)
        cnt_l = QVBoxLayout(cnt_box)
        cnt_l.setContentsMargins(8, 8, 8, 8)
        title_cnt = QLabel("CONTAPEZZI"); title_cnt.setStyleSheet("font-weight:700;")
        cnt_l.addWidget(title_cnt)
        row_t = QHBoxLayout()
        row_t.addWidget(QLabel("Target:"))
        self.spin_target = QSpinBox(); self.spin_target.setRange(0, 1_000_000)
        self.spin_target.setValue(int(getattr(self.machine, "semi_auto_target_pieces", 0)))
        btn_set_t = QPushButton("Imposta"); btn_set_t.clicked.connect(self._apply_target)
        row_t.addWidget(self.spin_target); row_t.addWidget(btn_set_t); row_t.addStretch(1)
        cnt_l.addLayout(row_t)
        row_s = QHBoxLayout()
        self.lbl_done = QLabel("Tagliati: 0"); self.lbl_done.setStyleSheet("font-weight:700; color:#2ecc71;")
        self.lbl_remaining = QLabel("Rimanenti: -"); self.lbl_remaining.setStyleSheet("font-weight:700; color:#f39c12;")
        btn_reset = QPushButton("Azzera"); btn_reset.clicked.connect(self._reset_counter)
        row_s.addWidget(self.lbl_done); row_s.addWidget(self.lbl_remaining); row_s.addStretch(1); row_s.addWidget(btn_reset)
        cnt_l.addLayout(row_s)
        ll.addWidget(cnt_box, 0, alignment=Qt.AlignLeft | Qt.AlignTop)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["#", "ID", "Len (mm)", "Qty", "Stock"])
        ll.addWidget(self.tree, 4)

        log_box = QFrame()
        log_l = QVBoxLayout(log_box); log_l.setContentsMargins(4, 4, 4, 4)
        log_l.addWidget(QLabel("Log"))
        self.log = QTextEdit(); self.log.setReadOnly(True); self.log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        log_l.addWidget(self.log, 1)
        ll.addWidget(log_box, 3)

        # Destra: status + fuori quota
        right = QFrame(); right.setFixedWidth(PANEL_W + 12); body.addWidget(right, 0)
        rl = QVBoxLayout(right); rl.setContentsMargins(6, 6, 6, 6); rl.setSpacing(8)

        status_wrap = QFrame(); status_wrap.setFixedSize(PANEL_W, PANEL_H)
        swl = QVBoxLayout(status_wrap); swl.setContentsMargins(0, 0, 0, 0)
        self.status = StatusPanel(self.machine, "STATO", status_wrap); swl.addWidget(self.status)
        rl.addWidget(status_wrap, 0, alignment=Qt.AlignLeft | Qt.AlignTop)

        fq_box = QFrame(); fq_box.setFixedSize(PANEL_W, FQ_H); fq_box.setFrameShape(QFrame.StyledPanel)
        fql = QHBoxLayout(fq_box); fql.setContentsMargins(8, 8, 8, 8)
        self.chk_fuori_quota = QCheckBox("Modalità fuori quota")
        cur_fq = bool(getattr(self.machine, "fuori_quota_mode", False) or getattr(self.machine, "out_of_quota_mode", False))
        self.chk_fuori_quota.setChecked(cur_fq)
        self.chk_fuori_quota.toggled.connect(self._toggle_fuori_quota)
        fql.addWidget(self.chk_fuori_quota); fql.addStretch(1)
        rl.addWidget(fq_box, 0, alignment=Qt.AlignLeft)
        rl.addStretch(1)

    def _toast(self, msg, level="info"):
        if hasattr(self.appwin, "toast"):
            self.appwin.toast.show(msg, level, 2500)

    # Piano/Sequencer
    def _calc_plan(self):
        dummy_jobs = [{"id": "A", "len": 500.0, "qty": 3}, {"id": "B", "len": 750.0, "qty": 2}]
        solver = self.cb_solver.currentText()
        if solver == "ILP":
            self.plan = plan_ilp(dummy_jobs, stock=None, time_limit_s=int(self.spin_tl.value()))
        else:
            self.plan = plan_bfd(dummy_jobs, stock=None)
        self._populate_plan(); self._toast(f"Piano calcolato ({self.plan['solver']})", "ok")

    def _populate_plan(self):
        self.tree.clear()
        for i, st in enumerate(self.plan.get("steps", []), start=1):
            it = QTreeWidgetItem([str(i), str(st.get("id", "")), f"{float(st.get('len', 0.0)):.1f}", str(int(st.get("qty", 1))), str(st.get("stock_id", "") or "-")])
            self.tree.addTopLevelItem(it)

    def _start_seq(self):
        steps = self.plan.get("steps") or []
        if not steps: self._toast("Nessun piano: calcola prima", "warn"); return
        self.seq.load_plan(steps); self.seq.start(); self._log("Sequenza avviata")
    def _pause_seq(self): self.seq.pause(); self._log("Sequenza in pausa")
    def _resume_seq(self): self.seq.resume(); self._log("Sequenza ripresa")
    def _stop_seq(self): self.seq.stop(); self._log("Sequenza arrestata")
    def _on_step_started(self, idx: int, step: dict): self._log(f"Step {idx+1} start: {step.get('id')}")
    def _on_step_finished(self, idx: int, step: dict): self._log(f"Step {idx+1} done")
    def _on_seq_done(self): self._log("Sequenza completata"); self._toast("Automatico: completato", "ok")
    def _log(self, s: str):
        if self.log: self.log.append(s)

    # Contapezzi / Fuori Quota
    def _apply_target(self):
        try:
            val = int(self.spin_target.value()) if self.spin_target else 0
            setattr(self.machine, "semi_auto_target_pieces", val); self._update_counters_ui(); self._toast("Target contapezzi impostato", "ok")
        except Exception: pass
    def _reset_counter(self):
        try:
            setattr(self.machine, "semi_auto_count_done", 0); self._update_counters_ui(); self._toast("Contatore pezzi azzerato", "ok")
        except Exception: pass
    def _toggle_fuori_quota(self, checked: bool):
        try:
            setattr(self.machine, "fuori_quota_mode", bool(checked)); setattr(self.machine, "out_of_quota_mode", bool(checked))
            self._toast(("Fuori quota ON" if checked else "Fuori quota OFF"), "info")
        except Exception: pass
    def _update_counters_ui(self):
        done = int(getattr(self.machine, "semi_auto_count_done", 0) or 0)
        target = int(getattr(self.machine, "semi_auto_target_pieces", 0) or 0)
        remaining = max(target - done, 0)
        if self.lbl_done: self.lbl_done.setText(f"Tagliati: {done}")
        if self.lbl_remaining: self.lbl_remaining.setText(f"Rimanenti: {remaining}")
        if self.spin_target and self.spin_target.value() != target: self.spin_target.setValue(target)

    # Polling
    def on_show(self):
        if self._poll is None:
            self._poll = QTimer(self); self._poll.timeout.connect(self._tick); self._poll.start(200)
        self._update_counters_ui()
        if self.status: self.status.refresh()
    def _tick(self):
        self._update_counters_ui()
        if self.status: self.status.refresh()
    def hideEvent(self, ev):
        if self._poll is not None:
            try: self._poll.stop()
            except Exception: pass
            self._poll = None
        super().hideEvent(ev)
