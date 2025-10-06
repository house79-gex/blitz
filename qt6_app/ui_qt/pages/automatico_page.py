from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton, QComboBox, QSpinBox, QTreeWidget, QTreeWidgetItem, QTextEdit
from PySide6.QtCore import Qt
from ui_qt.widgets.header import Header
from ui_qt.utils.settings import read_settings
from ui_qt.logic.planner import plan_ilp, plan_bfd
from ui_qt.logic.sequencer import Sequencer

class AutomaticoPage(QWidget):
    """
    Pianificatore ILP/BFD e sequencer.
    Mantiene le stesse funzioni di alto livello del Tk: calcolo piano, avvio/pausa/stop.
    """
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine
        self.plan = {"solver":"", "steps":[]}
        self.seq = Sequencer(appwin)
        self.seq.step_started.connect(self._on_step_started)
        self.seq.step_finished.connect(self._on_step_finished)
        self.seq.finished.connect(self._on_seq_done)
        self._build()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(8,8,8,8); root.setSpacing(6)
        root.addWidget(Header(self.appwin, "AUTOMATICO"))

        # Controls
        ctrl = QHBoxLayout(); ctrl.setSpacing(8)
        root.addLayout(ctrl)

        ctrl.addWidget(QLabel("Solver:"))
        self.cb_solver = QComboBox()
        self.cb_solver.addItems(["ILP", "BFD"])
        cfg = read_settings()
        if str(cfg.get("solver","ILP")).upper() in ("ILP","BFD"):
            self.cb_solver.setCurrentText(str(cfg.get("solver","ILP")).upper())
        ctrl.addWidget(self.cb_solver)

        ctrl.addWidget(QLabel("Time limit (s):"))
        self.spin_tl = QSpinBox(); self.spin_tl.setRange(1, 600); self.spin_tl.setValue(int(cfg.get("ilp_time_limit_s", 15)))
        ctrl.addWidget(self.spin_tl)

        btn_calc = QPushButton("Calcola Piano"); btn_calc.clicked.connect(self._calc_plan)
        btn_start = QPushButton("Avvia Sequenza"); btn_start.clicked.connect(self._start_seq)
        btn_pause = QPushButton("Pausa"); btn_pause.clicked.connect(self._pause_seq)
        btn_resume = QPushButton("Riprendi"); btn_resume.clicked.connect(self._resume_seq)
        btn_stop = QPushButton("Stop"); btn_stop.clicked.connect(self._stop_seq)
        ctrl.addWidget(btn_calc); ctrl.addWidget(btn_start); ctrl.addWidget(btn_pause); ctrl.addWidget(btn_resume); ctrl.addWidget(btn_stop)
        ctrl.addStretch(1)

        # Plan view
        body = QHBoxLayout(); body.setSpacing(8)
        root.addLayout(body, 1)

        left = QFrame(); body.addWidget(left, 2)
        ll = QVBoxLayout(left); ll.setContentsMargins(6,6,6,6)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["#", "ID", "Len (mm)", "Qty", "Stock"])
        ll.addWidget(self.tree, 1)

        right = QFrame(); body.addWidget(right, 1)
        rl = QVBoxLayout(right); rl.setContentsMargins(6,6,6,6)
        rl.addWidget(QLabel("Log"))
        self.log = QTextEdit(); self.log.setReadOnly(True)
        rl.addWidget(self.log, 1)

    def _toast(self, msg, level="info"):
        if hasattr(self.appwin, "toast"):
            self.appwin.toast.show(msg, level, 2500)

    def _calc_plan(self):
        # TODO: sostituire jobs/stock con sorgenti dati reali (come nel Tk)
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
                str(st.get("id","")),
                f"{float(st.get('len',0.0)):.1f}",
                str(int(st.get("qty",1))),
                str(st.get("stock_id","") or "-"),
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

    def on_show(self):
        pass
