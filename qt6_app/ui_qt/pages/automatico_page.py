from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple
from collections import defaultdict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QComboBox, QSpinBox, QTreeWidget, QTreeWidgetItem, QTextEdit, QCheckBox, QSizePolicy, QMessageBox
)
from PySide6.QtCore import Qt, QTimer

from ui_qt.widgets.header import Header
from ui_qt.utils.settings import read_settings
from ui_qt.logic.planner import plan_ilp, plan_bfd
from ui_qt.logic.sequencer import Sequencer
from ui_qt.widgets.status_panel import StatusPanel

# Nuovi import per importare liste di taglio salvate
from ui_qt.services.orders_store import OrdersStore
from ui_qt.dialogs.orders_manager_qt import OrdersManagerDialog

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
        self.plan: Dict[str, Any] = {"solver": "", "steps": []}
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

        # Nuovo: archivio ordini (usa stesso DB) e cutlist corrente
        self._orders = OrdersStore()
        self._cutlist: Optional[List[Dict[str, Any]]] = None  # lista di taglio corrente importata

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
        # Arresta sequenza e pulisce piano/viste
        try:
            self.seq.stop()
        except Exception:
            pass
        self.plan = {"solver": "", "steps": []}
        self._cutlist = None
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

        # Nuovo: import cutlist prima dei controlli solver
        btn_import_cut = QPushButton("Importa Lista di Taglio…")
        btn_import_cut.clicked.connect(self._import_cutlist)
        ctrl.addWidget(btn_import_cut)

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
        # Se è stata importata una cutlist, convertila in jobs per il planner
        if self._cutlist:
            jobs = self._jobs_from_cutlist(self._cutlist)
        else:
            # Demo fallback (come prima)
            jobs = [{"id": "A", "len": 500.0, "qty": 3}, {"id": "B", "len": 750.0, "qty": 2}]

        solver = self.cb_solver.currentText()
        if solver == "ILP":
            self.plan = plan_ilp(jobs, stock=None, time_limit_s=int(self.spin_tl.value()))
        else:
            self.plan = plan_bfd(jobs, stock=None)

        self._populate_plan()
        self._toast(f"Piano calcolato ({self.plan.get('solver','')})", "ok")

    def _jobs_from_cutlist(self, cuts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Converte la cutlist salvata (profile, length_mm, ang_sx, ang_dx, qty, note)
        in jobs per il planner: {id, len, qty}.
        Raggruppa per (profilo, lunghezza, ang_sx, ang_dx) per non mescolare varianti diverse.
        """
        grouped: Dict[Tuple[str, float, float, float], int] = defaultdict(int)
        for c in cuts:
            prof = str(c.get("profile") or "")
            length = float(c.get("length_mm", 0.0) or 0.0)
            ax = float(c.get("ang_sx", 0.0) or 0.0)
            ad = float(c.get("ang_dx", 0.0) or 0.0)
            qty = int(c.get("qty", 0) or 0)
            key = (prof, round(length, 2), round(ax, 1), round(ad, 1))
            grouped[key] += qty

        jobs: List[Dict[str, Any]] = []
        # Ordina per lunghezza decrescente (tipica ottimizzazione lineare)
        for (prof, length, ax, ad), q in sorted(grouped.items(), key=lambda kv: kv[0][1], reverse=True):
            job_id = f"{prof} {length:.2f} ({ax:.0f}/{ad:.0f})"
            jobs.append({"id": job_id, "len": float(length), "qty": int(q)})
        return jobs

    def _populate_plan(self):
        self.tree.clear()
        for i, st in enumerate(self.plan.get("steps", []), start=1):
            it = QTreeWidgetItem([
                str(i),
                str(st.get("id", "")),
                f"{float(st.get('len', 0.0)):.1f}",
                str(int(st.get("qty", 1))),
                str(st.get("stock_id", "") or "-")
            ])
            self.tree.addTopLevelItem(it)

    def _start_seq(self):
        steps = self.plan.get("steps") or []
        if not steps:
            self._toast("Nessun piano: calcola prima", "warn"); return
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
        if self.log:
            self.log.append(s)

    # Contapezzi / Fuori Quota
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
            setattr(self.machine, "semi_auto_count_done", 0)
            self._update_counters_ui()
            self._toast("Contatore pezzi azzerato", "ok")
        except Exception:
            pass

    def _toggle_fuori_quota(self, checked: bool):
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

    # Import cutlist da OrdersStore
    def _import_cutlist(self):
        dlg = OrdersManagerDialog(self, self._orders)
        if dlg.exec() and getattr(dlg, "selected_order_id", None):
            ord_item = self._orders.get_order(int(dlg.selected_order_id))
            if not ord_item:
                QMessageBox.critical(self, "Importa", "Ordine non trovato.")
                return
            data = ord_item.get("data") or {}
            if data.get("type") != "cutlist":
                QMessageBox.information(self, "Importa", "L'ordine selezionato non è una lista di taglio (type = cutlist).")
                return
            cuts = data.get("cuts") or []
            if not isinstance(cuts, list) or not cuts:
                QMessageBox.information(self, "Importa", "Lista di taglio vuota.")
                return
            self._cutlist = cuts
            self._log(f"Importata cutlist id={ord_item['id']} con {len(cuts)} righe; calcola il piano per procedere.")
            self._toast("Cutlist importata", "ok")

    # Polling
    def on_show(self):
        if self._poll is None:
            self._poll = QTimer(self)
            self._poll.timeout.connect(self._tick)
            self._poll.start(200)
        self._update_counters_ui()
        if self.status:
            self.status.refresh()

    def _tick(self):
        self._update_counters_ui()
        if self.status:
            self.status.refresh()

    def hideEvent(self, ev):
        if self._poll is not None:
            try:
                self._poll.stop()
            except Exception:
                pass
            self._poll = None
        super().hideEvent(ev)
