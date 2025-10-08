from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QComboBox, QSpinBox, QTreeWidget, QTreeWidgetItem, QTextEdit, QCheckBox, QDoubleSpinBox
)
from PySide6.QtCore import Qt, QTimer
from ui_qt.widgets.header import Header
from ui_qt.utils.settings import read_settings
from ui_qt.logic.planner import plan_ilp, plan_bfd
from ui_qt.logic.sequencer import Sequencer
from ui_qt.widgets.status_panel import StatusPanel

STATUS_PANEL_HEIGHT = 220  # uniforma dimensioni a Semi-Auto (regolabile)


class AutomaticoPage(QWidget):
    """
    Pianificatore ILP/BFD e sequencer.
    Stato a destra con:
    - StatusPanel (stessa dimensione di Semi-Auto)
    - Contapezzi (target/tagliati/rimanenti)
    - Modalità Fuori Quota (toggle)
    """
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine
        self.plan = {"solver": "", "steps": []}
        self.seq = Sequencer(appwin)
        self.seq.step_started.connect(self._on_step_started)
        self.seq.step_finished.connect(self._on_step_finished)
        self.seq.finished.connect(self._on_seq_done)

        self.status: StatusPanel | None = None
        self._poll: QTimer | None = None

        # Contapezzi UI refs
        self.spin_target: QSpinBox | None = None
        self.lbl_done: QLabel | None = None
        self.lbl_remaining: QLabel | None = None
        # Fuori quota
        self.chk_fuori_quota: QCheckBox | None = None

        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)
        root.addWidget(Header(self.appwin, "AUTOMATICO"))

        # Controls
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

        # Plan view
        body = QHBoxLayout()
        body.setSpacing(8)
        root.addLayout(body, 1)

        left = QFrame()
        body.addWidget(left, 2)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(6, 6, 6, 6)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["#", "ID", "Len (mm)", "Qty", "Stock"])
        ll.addWidget(self.tree, 1)

        right = QFrame()
        body.addWidget(right, 1)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(6, 6, 6, 6)
        rl.setSpacing(8)

        # StatusPanel in alto (uniformato)
        self.status = StatusPanel(self.machine, "STATO", right)
        self.status.setMinimumHeight(STATUS_PANEL_HEIGHT)
        self.status.setMaximumHeight(STATUS_PANEL_HEIGHT)
        rl.addWidget(self.status)

        # Contapezzi (come in Semi-Auto)
        cnt_box = QFrame()
        cnt_l = QVBoxLayout(cnt_box); cnt_l.setContentsMargins(6, 6, 6, 6)
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

        rl.addWidget(cnt_box)

        # Modalità Fuori Quota (come in Semi-Auto: toggle)
        fq_box = QFrame()
        fq_l = QHBoxLayout(fq_box); fq_l.setContentsMargins(6, 6, 6, 6)
        self.chk_fuori_quota = QCheckBox("Modalità fuori quota")
        cur_fq = bool(getattr(self.machine, "fuori_quota_mode", False) or getattr(self.machine, "out_of_quota_mode", False))
        self.chk_fuori_quota.setChecked(cur_fq)
        self.chk_fuori_quota.toggled.connect(self._toggle_fuori_quota)
        fq_l.addWidget(self.chk_fuori_quota); fq_l.addStretch(1)
        rl.addWidget(fq_box)

        # Log
        rl.addWidget(QLabel("Log"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        rl.addWidget(self.log, 1)

    def _toast(self, msg, level="info"):
        if hasattr(self.appwin, "toast"):
            self.appwin.toast.show(msg, level, 2500)

    # ----------------- Piano / Sequencer -----------------
    def _calc_plan(self):
        # TODO: sostituire con sorgenti dati reali (come in Tk)
        dummy_jobs = [
            {"id": "A", "len": 500.0, "qty": 3},
            {"id": "B", "len": 750.0, "qty": 2},
        ]
        solver = self.cb_solver.currentText()
        if solver == "ILP":
            self.plan = plan_ilp(dummy_jobs, stock=None, time_limit_s=int(self.spin_tl.value()))
        else:
            self.plan = plan_bfd(dummy_jobs, stock=None)
        self._populate_plan()
        self._toast(f"Piano calcolato ({self.plan['solver']})", "ok")

    def _populate_plan(self):
        self.tree.clear()
        for i, st in enumerate(self.plan.get("steps", []), start=1):
            it = QTreeWidgetItem([
                str(i),
                str(st.get("id", "")),
                f"{float(st.get('len', 0.0)):.1f}",
                str(int(st.get("qty", 1))),
                str(st.get("stock_id", "") or "-"),
            ])
            self.tree.addTopLevelItem(it)

    def _start_seq(self):
        steps = self.plan.get("steps") or []
        if not steps:
            self._toast("Nessun piano: calcola prima", "warn")
            return
        self.seq.load_plan(steps)
        self.seq.start()
        self._log("Sequenza avviata")

    def _pause_seq(self):
        self.seq.pause()
        self._log("Sequenza in pausa")

    def _resume_seq(self):
        self.seq.resume()
        self._log("Sequenza ripresa")

    def _stop_seq(self):
        self.seq.stop()
        self._log("Sequenza arrestata")

    def _on_step_started(self, idx: int, step: dict):
        self._log(f"Step {idx+1} start: {step.get('id')}")

    def _on_step_finished(self, idx: int, step: dict):
        self._log(f"Step {idx+1} done")

    def _on_seq_done(self):
        self._log("Sequenza completata")
        self._toast("Automatico: completato", "ok")

    def _log(self, s: str):
        self.log.append(s)

    # ----------------- Contapezzi / Fuori Quota -----------------
    def _apply_target(self):
        try:
            val = int(self.spin_target.value()) if self.spin_target else 0
            setattr(self.machine, "semi_auto_target_pieces", val)
            self._update_counters_ui()
            self._toast("Target contapezzi impostato", "ok")
        except Exception:
            pass

    def _reset_counter(self):
        try:
            # allinea alla semantica di Semi-Auto
            setattr(self.machine, "semi_auto_count_done", 0)
            self._update_counters_ui()
            self._toast("Contatore pezzi azzerato", "ok")
        except Exception:
            pass

    def _toggle_fuori_quota(self, checked: bool):
        # esponi entrambi i nomi per compat
        try:
            setattr(self.machine, "fuori_quota_mode", bool(checked))
            setattr(self.machine, "out_of_quota_mode", bool(checked))
            self._toast(("Fuori quota ON" if checked else "Fuori quota OFF"), "info")
        except Exception:
            pass

    def _update_counters_ui(self):
        done = int(getattr(self.machine, "semi_auto_count_done", 0) or 0)
        target = int(getattr(self.machine, "semi_auto_target_pieces", 0) or 0)
        remaining = max(target - done, 0)
        if self.lbl_done:
            self.lbl_done.setText(f"Tagliati: {done}")
        if self.lbl_remaining:
            self.lbl_remaining.setText(f"Rimanenti: {remaining}")
        if self.spin_target and self.spin_target.value() != target:
            self.spin_target.setValue(target)

    # ----------------- Polling Status/Counters -----------------
    def on_show(self):
        # avvia polling status quando la pagina diventa attiva
        if self._poll is None:
            self._poll = QTimer(self)
            self._poll.timeout.connect(self._tick)
            self._poll.start(200)
        # sync iniziale
        self._update_counters_ui()
        if self.status:
            self.status.refresh()

    def _tick(self):
        self._update_counters_ui()
        if self.status:
            self.status.refresh()

    def hideEvent(self, ev):
        # ferma polling quando la pagina non è visibile
        if self._poll is not None:
            try:
                self._poll.stop()
            except Exception:
                pass
            self._poll = None
        super().hideEvent(ev)
