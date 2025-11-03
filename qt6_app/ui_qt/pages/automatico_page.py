from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple
from collections import defaultdict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QComboBox, QSpinBox, QTreeWidget, QTreeWidgetItem, QTextEdit, QCheckBox,
    QSizePolicy, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView, QDoubleSpinBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut

from ui_qt.widgets.header import Header
from ui_qt.utils.settings import read_settings
from ui_qt.logic.planner import plan_ilp, plan_bfd  # opzionale: usato solo a scopo informativo
from ui_qt.logic.sequencer import Sequencer         # lasciato per segnali/log
from ui_qt.widgets.status_panel import StatusPanel

from ui_qt.services.orders_store import OrdersStore
from ui_qt.dialogs.orders_manager_qt import OrdersManagerDialog

PANEL_W = 420
PANEL_H = 220
COUNTER_W = 420
COUNTER_H = 150
FQ_H = 100


class AutomaticoPage(QWidget):
    """
    Automatico con logica Semi-Auto replicata:
    - Manuale per riga: Start → posiziona, BLOCCA freno, conteggio con input lama fino a target, quindi SBLOCCA.
    - Ottimizzazione per profilo e per barra (first-fit decreasing con kerf):
        • costruisce sequenze miste di pezzi per massimizzare l'uso della barra
        • l'operatore avanza con pulsante fisico: ogni pressione arma un pezzo (target=1), posiziona+blocca, conta il taglio, sblocca, segnala e attende.
    """

    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine

        # Sequencer per compatibilità/log
        self.plan: Dict[str, Any] = {"solver": "", "steps": []}
        self.seq = Sequencer(appwin)
        self.seq.step_started.connect(self._on_step_started)
        self.seq.step_finished.connect(self._on_step_finished)
        self.seq.finished.connect(self._on_seq_done)

        self.status: Optional[StatusPanel] = None
        self._poll: Optional[QTimer] = None

        # UI refs
        self.spin_target: Optional[QSpinBox] = None
        self.lbl_done: Optional[QLabel] = None
        self.lbl_remaining: Optional[QLabel] = None
        self.chk_fuori_quota: Optional[QCheckBox] = None
        self.chk_start_phys: Optional[QCheckBox] = None
        self.tbl_cut: Optional[QTableWidget] = None
        self.cb_solver: Optional[QComboBox] = None
        self.spin_tl: Optional[QSpinBox] = None
        self.cmb_profile: Optional[QComboBox] = None
        self.sp_stock: Optional[QDoubleSpinBox] = None
        self.sp_kerf: Optional[QDoubleSpinBox] = None
        self.log: Optional[QTextEdit] = None

        # Cutlist importata
        self._orders = OrdersStore()
        self._cutlist: List[Dict[str, Any]] = []  # {profile, element, length_mm, ang_sx, ang_dx, qty, note}
        self._profiles: List[str] = []

        # Stato operativo
        self._mode: str = "idle"  # idle | manual | plan
        self._active_row: Optional[int] = None
        self._manual_job: Optional[Dict[str, Any]] = None  # prof, elem, L, ax, ad
        self._active_initial_target: int = 0

        # I/O runtime
        self._brake_locked: bool = False
        self._blade_prev: bool = False
        self._start_prev: bool = False

        # Piano per barre
        self._plan_profile: str = ""
        self._bars: List[List[Dict[str, float]]] = []  # ogni bar: lista di pezzi {"len","ax","ad"}
        self._bar_idx: int = -1
        self._piece_idx: int = -1
        self._step_armed: bool = False  # target impostato e freno pronto a contare

        self._build()

    # ---------------- Helpers nav/reset ----------------
    def _nav_home(self) -> bool:
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
        try:
            self.seq.stop()
        except Exception:
            pass
        self.plan = {"solver": "", "steps": []}
        self._cutlist.clear()
        self._profiles.clear()

        self._mode = "idle"
        self._active_row = None
        self._manual_job = None
        self._active_initial_target = 0

        self._brake_locked = False
        self._blade_prev = False
        self._start_prev = False

        self._plan_profile = ""
        self._bars.clear()
        self._bar_idx = -1
        self._piece_idx = -1
        self._step_armed = False

        try:
            if self.tbl_cut:
                self.tbl_cut.clearContents()
                self.tbl_cut.setRowCount(0)
        except Exception:
            pass
        if self.log:
            self.log.clear()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        root.addWidget(Header(self.appwin, "AUTOMATICO", mode="default", on_home=self._nav_home, on_reset=self._reset_and_home))

        # Controls top bar
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)
        root.addLayout(ctrl)

        # Import cutlist
        btn_import = QPushButton("Importa Cutlist…")
        btn_import.clicked.connect(self._import_cutlist)
        ctrl.addWidget(btn_import)

        # Profiler + optimizer inputs
        ctrl.addWidget(QLabel("Profilo:"))
        self.cmb_profile = QComboBox()
        ctrl.addWidget(self.cmb_profile)

        ctrl.addWidget(QLabel("Stock (mm):"))
        self.sp_stock = QDoubleSpinBox()
        self.sp_stock.setRange(100.0, 12000.0)
        self.sp_stock.setDecimals(1)
        self.sp_stock.setValue(6500.0)  # default tipico
        ctrl.addWidget(self.sp_stock)

        ctrl.addWidget(QLabel("Kerf (mm):"))
        self.sp_kerf = QDoubleSpinBox()
        self.sp_kerf.setRange(0.0, 10.0)
        self.sp_kerf.setDecimals(2)
        self.sp_kerf.setValue(3.0)  # default lama
        ctrl.addWidget(self.sp_kerf)

        ctrl.addWidget(QLabel("Solver:"))
        self.cb_solver = QComboBox()
        self.cb_solver.addItems(["ILP", "BFD"])
        cfg = read_settings()
        if str(cfg.get("solver", "ILP")).upper() in ("ILP", "BFD"):
            self.cb_solver.setCurrentText(str(cfg.get("solver", "ILP")).upper())
        ctrl.addWidget(self.cb_solver)

        ctrl.addWidget(QLabel("TL (s):"))
        self.spin_tl = QSpinBox()
        self.spin_tl.setRange(1, 600)
        self.spin_tl.setValue(int(cfg.get("ilp_time_limit_s", 15)))
        ctrl.addWidget(self.spin_tl)

        btn_opt = QPushButton("Ottimizza profilo")
        btn_opt.setToolTip("Costruisce barre miste (FFD) per il profilo selezionato in base a Stock/Kerf.")
        btn_opt.clicked.connect(self._optimize_profile)
        ctrl.addWidget(btn_opt)

        # Start fisico
        self.chk_start_phys = QCheckBox("Start fisico")
        self.chk_start_phys.setToolTip("Usa il pulsante fisico sulla pulsantiera mobile per avanzare")
        ctrl.addWidget(self.chk_start_phys)

        ctrl.addStretch(1)

        # Corpo
        body = QHBoxLayout()
        body.setSpacing(8)
        root.addLayout(body, 1)

        # Sinistra: contapezzi + cutlist
        left = QFrame()
        body.addWidget(left, 2)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(6, 6, 6, 6)
        ll.setSpacing(8)

        # Contapezzi (stessa logica Semi-Auto)
        cnt_box = QFrame()
        cnt_box.setFixedSize(COUNTER_W, COUNTER_H)
        cnt_box.setFrameShape(QFrame.StyledPanel)
        cnt_l = QVBoxLayout(cnt_box)
        cnt_l.setContentsMargins(8, 8, 8, 8)
        title_cnt = QLabel("CONTAPEZZI")
        title_cnt.setStyleSheet("font-weight:700;")
        cnt_l.addWidget(title_cnt)

        row_t = QHBoxLayout()
        row_t.addWidget(QLabel("Target:"))
        self.spin_target = QSpinBox()
        self.spin_target.setRange(0, 1_000_000)
        self.spin_target.setValue(int(getattr(self.machine, "semi_auto_target_pieces", 0)))
        btn_set_t = QPushButton("Imposta")
        btn_set_t.setToolTip("Imposta manualmente il target (di norma viene armato in automatico)")
        btn_set_t.clicked.connect(self._apply_target)
        row_t.addWidget(self.spin_target)
        row_t.addWidget(btn_set_t)
        row_t.addStretch(1)
        cnt_l.addLayout(row_t)

        row_s = QHBoxLayout()
        self.lbl_done = QLabel("Tagliati: 0")
        self.lbl_done.setStyleSheet("font-weight:700; color:#2ecc71;")
        self.lbl_remaining = QLabel("Rimanenti: -")
        self.lbl_remaining.setStyleSheet("font-weight:700; color:#f39c12;")
        btn_reset = QPushButton("Azzera")
        btn_reset.clicked.connect(self._reset_counter)
        row_s.addWidget(self.lbl_done)
        row_s.addWidget(self.lbl_remaining)
        row_s.addStretch(1)
        row_s.addWidget(btn_reset)
        cnt_l.addLayout(row_s)

        ll.addWidget(cnt_box, 0, alignment=Qt.AlignLeft | Qt.AlignTop)

        # Cutlist importata
        ll.addWidget(QLabel("Cutlist importata (seleziona riga e premi 'Start riga')"))
        self.tbl_cut = QTableWidget(0, 7)
        self.tbl_cut.setHorizontalHeaderLabels(["Profilo", "Elemento", "Lunghezza (mm)", "Ang SX", "Ang DX", "Q.tà", "Note"])
        hdr = self.tbl_cut.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.Stretch)
        ll.addWidget(self.tbl_cut, 4)

        action_row = QHBoxLayout()
        btn_start_one = QPushButton("Start riga")
        btn_start_one.setToolTip("Posiziona alla misura selezionata e blocca. Conta con input lama finché non raggiungi il target, poi sblocca.")
        btn_start_one.clicked.connect(self._start_row)
        action_row.addWidget(btn_start_one)

        btn_next_step = QPushButton("Avanza step (piano)")
        btn_next_step.setToolTip("In modalità Ottimizzazione: arma/posiziona il prossimo pezzo (target=1)")
        btn_next_step.clicked.connect(self._plan_manual_advance)
        action_row.addWidget(btn_next_step)

        action_row.addStretch(1)
        ll.addLayout(action_row)

        # Destra: stato macchina + fuori quota + log
        right = QFrame()
        right.setFixedWidth(PANEL_W + 12)
        body.addWidget(right, 1)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(6, 6, 6, 6)
        rl.setSpacing(8)

        status_wrap = QFrame()
        status_wrap.setFixedSize(PANEL_W, PANEL_H)
        swl = QVBoxLayout(status_wrap)
        swl.setContentsMargins(0, 0, 0, 0)
        self.status = StatusPanel(self.machine, "STATO", status_wrap)
        swl.addWidget(self.status)
        rl.addWidget(status_wrap, 0, alignment=Qt.AlignLeft | Qt.AlignTop)

        fq_box = QFrame()
        fq_box.setFixedSize(PANEL_W, FQ_H)
        fq_box.setFrameShape(QFrame.StyledPanel)
        fql = QHBoxLayout(fq_box)
        fql.setContentsMargins(8, 8, 8, 8)
        self.chk_fuori_quota = QCheckBox("Modalità fuori quota")
        cur_fq = bool(getattr(self.machine, "fuori_quota_mode", False) or getattr(self.machine, "out_of_quota_mode", False))
        self.chk_fuori_quota.setChecked(cur_fq)
        self.chk_fuori_quota.toggled.connect(self._toggle_fuori_quota)
        fql.addWidget(self.chk_fuori_quota)
        fql.addStretch(1)
        rl.addWidget(fq_box, 0, alignment=Qt.AlignLeft)

        rl.addWidget(QLabel("Log"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        rl.addWidget(self.log, 1)

        # Fallback: Space simula Start fisico
        QShortcut(QKeySequence("Space"), self, activated=self._handle_start_trigger)

    # --------------------- Import cutlist ---------------------
    def _import_cutlist(self):
        dlg = OrdersManagerDialog(self, self._orders)
        if dlg.exec() and getattr(dlg, "selected_order_id", None):
            ord_item = self._orders.get_order(int(dlg.selected_order_id))
            if not ord_item:
                QMessageBox.critical(self, "Importa", "Ordine non trovato.")
                return
            data = ord_item.get("data") or {}
            if data.get("type") != "cutlist":
                QMessageBox.information(self, "Importa", "L'ordine selezionato non è una lista di taglio.")
                return
            cuts = data.get("cuts") or []
            if not isinstance(cuts, list) or not cuts:
                QMessageBox.information(self, "Importa", "Lista di taglio vuota.")
                return
            self._load_cutlist(cuts)
            self._toast("Cutlist importata", "ok")

    def _load_cutlist(self, cuts: List[Dict[str, Any]]):
        self._cutlist = list(cuts)
        profs: List[str] = []
        self.tbl_cut.setRowCount(0)
        for c in self._cutlist:
            p = str(c.get("profile", "")).strip()
            if p and p not in profs:
                profs.append(p)
            r = self.tbl_cut.rowCount()
            self.tbl_cut.insertRow(r)
            self.tbl_cut.setItem(r, 0, QTableWidgetItem(str(c.get("profile", ""))))
            self.tbl_cut.setItem(r, 1, QTableWidgetItem(str(c.get("element", ""))))
            self.tbl_cut.setItem(r, 2, QTableWidgetItem(f"{float(c.get('length_mm', 0.0)):.2f}"))
            self.tbl_cut.setItem(r, 3, QTableWidgetItem(f"{float(c.get('ang_sx', 0.0)):.1f}"))
            self.tbl_cut.setItem(r, 4, QTableWidgetItem(f"{float(c.get('ang_dx', 0.0)):.1f}"))
            self.tbl_cut.setItem(r, 5, QTableWidgetItem(str(int(c.get("qty", 0)))))
            self.tbl_cut.setItem(r, 6, QTableWidgetItem(str(c.get("note", ""))))
        self._profiles = profs
        self.cmb_profile.clear()
        self.cmb_profile.addItems(self._profiles)

        # reset stato
        self._mode = "idle"
        self._active_row = None
        self._manual_job = None
        self._active_initial_target = 0
        self._bars.clear()
        self._bar_idx = -1
        self._piece_idx = -1
        self._step_armed = False

    # --------------------- Manuale: riga ---------------------
    def _start_row(self):
        r = self.tbl_cut.currentRow()
        if r < 0:
            QMessageBox.information(self, "Start", "Seleziona una riga.")
            return
        try:
            prof = self.tbl_cut.item(r, 0).text().strip()
            elem = self.tbl_cut.item(r, 1).text().strip()
            length = float(self.tbl_cut.item(r, 2).text())
            ax = float(self.tbl_cut.item(r, 3).text())
            ad = float(self.tbl_cut.item(r, 4).text())
            qty = int(self.tbl_cut.item(r, 5).text())
        except Exception:
            QMessageBox.critical(self, "Start", "Riga non valida.")
            return
        if qty <= 0:
            QMessageBox.information(self, "Start", "Quantità riga esaurita.")
            return

        # Arma contapezzi (target=qty riga, done=0)
        try:
            setattr(self.machine, "semi_auto_target_pieces", int(qty))
            setattr(self.machine, "semi_auto_count_done", 0)
        except Exception:
            pass
        self._active_initial_target = qty

        # Posiziona e BLOCCA
        self._do_position(length, ax, ad, prof, elem)
        self._lock_brake()

        # Stato corrente
        self._mode = "manual"
        self._active_row = r
        self._manual_job = {"profile": prof, "element": elem, "length": length, "ax": ax, "ad": ad}
        self._log(f"Start riga: {prof} | {elem} | {length:.2f} mm (qty={qty})")

    # --------------------- Ottimizzazione per barra ---------------------
    def _optimize_profile(self):
        prof = (self.cmb_profile.currentText() or "").strip()
        if not prof:
            QMessageBox.information(self, "Ottimizza", "Seleziona un profilo.")
            return
        stock = float(self.sp_stock.value() if self.sp_stock else 6500.0)
        kerf = float(self.sp_kerf.value() if self.sp_kerf else 3.0)

        # Colleziona tutte le (len,ax,ad,qty) di questo profilo
        items: Dict[Tuple[float, float, float], int] = defaultdict(int)
        for r in range(self.tbl_cut.rowCount()):
            if self.tbl_cut.item(r, 0) and self.tbl_cut.item(r, 0).text().strip() == prof:
                try:
                    L = round(float(self.tbl_cut.item(r, 2).text()), 2)
                    ax = float(self.tbl_cut.item(r, 3).text())
                    ad = float(self.tbl_cut.item(r, 4).text())
                    q = int(self.tbl_cut.item(r, 5).text())
                except Exception:
                    continue
                if q > 0:
                    items[(L, ax, ad)] += q
        if not items:
            QMessageBox.information(self, "Ottimizza", "Nessun pezzo per questo profilo.")
            return

        # Espandi in lista di pezzi unitari (ogni unità = 1 pezzo)
        pieces = []
        for (L, ax, ad), q in items.items():
            for _ in range(q):
                pieces.append({"len": float(L), "ax": float(ax), "ad": float(ad)})

        # First-Fit Decreasing con kerf
        pieces.sort(key=lambda x: x["len"], reverse=True)
        bars: List[List[Dict[str, float]]] = []
        bars_space: List[float] = []  # spazio residuo effettivo considerando kerf tra tagli
        for p in pieces:
            need = p["len"]
            placed = False
            for i in range(len(bars)):
                # spazio residuo: se in barra già c'è almeno un pezzo, serve aggiungere kerf
                extra = kerf if bars[i] else 0.0
                if bars_space[i] >= (need + extra):
                    bars[i].append(p)
                    bars_space[i] -= (need + extra)
                    placed = True
                    break
            if not placed:
                if need > stock:
                    self._log(f"ATTENZIONE: pezzo {need}mm > stock {stock}mm. Inserito comunque in barra singola.")
                bars.append([p])
                bars_space.append(max(stock - need, 0.0))

        # Salva piano barre
        self._plan_profile = prof
        self._bars = bars
        self._bar_idx = 0
        self._piece_idx = -1
        self._step_armed = False
        self._mode = "plan"

        # Info (opzionale: planner ILP/BFD solo informativo)
        solver = self.cb_solver.currentText()
        jobs = []
        agg_len: Dict[float, int] = defaultdict(int)
        for p in pieces:
            agg_len[round(p["len"], 2)] += 1
        for L, q in sorted(agg_len.items(), key=lambda t: t[0], reverse=True):
            jobs.append({"id": f"{prof} {L:.2f}", "len": float(L), "qty": int(q)})
        try:
            if solver == "ILP":
                self.plan = plan_ilp(jobs, stock=stock, time_limit_s=int(self.spin_tl.value()))
            else:
                self.plan = plan_bfd(jobs, stock=stock)
        except Exception:
            self.plan = {"solver": solver, "steps": [{"id": j["id"], "len": j["len"], "qty": j["qty"]} for j in jobs]}

        self._log(f"Ottimizzazione {solver} per profilo {prof}: barre={len(bars)} (kerf={kerf} mm, stock={stock} mm)")
        for bi, bar in enumerate(bars, start=1):
            tot = sum(x["len"] for x in bar) + max(0, len(bar)-1)*kerf
            self._log(f"  Bar {bi}: pezzi={len(bar)} | somma={tot:.1f} mm")

        self._toast("Piano barre pronto. Usa Start fisico o 'Avanza step (piano)'.", "info")

    def _plan_manual_advance(self):
        # Comportamento identico allo Start fisico in modalità piano
        self._handle_start_trigger(force_plan=True)

    # --------------------- Movimento / Freno / I/O ---------------------
    def _do_position(self, length: float, ax: float, ad: float, profile: str, element: str):
        try:
            if hasattr(self.machine, "position_for_cut"):
                self.machine.position_for_cut(float(length), float(ax), float(ad), profile, element)
            elif hasattr(self.machine, "move_to_length"):
                self.machine.move_to_length(float(length))
            else:
                setattr(self.machine, "pending_cut", {"profile": profile, "element": element,
                                                      "length_mm": float(length), "ang_sx": float(ax), "ang_dx": float(ad)})
            self._log(f"Posizionamento: {profile} | {element} | {length:.2f} ({ax:.1f}/{ad:.1f})")
        except Exception as e:
            QMessageBox.critical(self, "Posizionamento", str(e))

    def _lock_brake(self):
        try:
            if hasattr(self.machine, "set_output"):
                self.machine.set_output("head_brake", True)
                self._brake_locked = True
            elif hasattr(self.machine, "head_brake_lock"):
                self.machine.head_brake_lock()
                self._brake_locked = True
            else:
                setattr(self.machine, "brake_locked", True)
                self._brake_locked = True
            self._log("Freno BLOCCATO")
        except Exception:
            pass

    def _unlock_brake(self):
        try:
            if hasattr(self.machine, "set_output"):
                self.machine.set_output("head_brake", False)
                self._brake_locked = False
            elif hasattr(self.machine, "head_brake_unlock"):
                self.machine.head_brake_unlock()
                self._brake_locked = False
            else:
                setattr(self.machine, "brake_locked", False)
                self._brake_locked = False
            self._log("Freno SBLOCCATO")
        except Exception:
            pass

    def _beep(self):
        try:
            if hasattr(self.machine, "beep"):
                self.machine.beep()
            elif hasattr(self.machine, "buzzer"):
                self.machine.buzzer(True)
        except Exception:
            pass

    def _set_start_light(self, on: bool):
        try:
            if hasattr(self.machine, "set_light"):
                self.machine.set_light("start", bool(on))
            else:
                setattr(self.machine, "start_light_on", bool(on))
        except Exception:
            pass

    def _read_input(self, key: str) -> bool:
        try:
            if hasattr(self.machine, "read_input") and callable(getattr(self.machine, "read_input")):
                return bool(self.machine.read_input(key))
            if hasattr(self.machine, key):
                return bool(getattr(self.machine, key))
        except Exception:
            pass
        return False

    def _read_blade_pulse(self) -> bool:
        # tenta chiavi comuni
        for k in ("blade_cut", "blade_pulse", "cut_pulse", "lama_pulse"):
            if self._read_input(k):
                return True
        return False

    def _read_start_button(self) -> bool:
        for k in ("start_mobile", "mobile_start_pressed", "start_pressed"):
            if self._read_input(k):
                return True
        return False

    # --------------------- Start trigger handler ---------------------
    def _handle_start_trigger(self, force_plan: bool = False):
        if force_plan and self._mode != "plan":
            return

        if self._mode == "plan" and self._bars:
            # Se lo step non è armato o è completo, avanza al prossimo pezzo (target=1)
            done = int(getattr(self.machine, "semi_auto_count_done", 0) or 0)
            target = int(getattr(self.machine, "semi_auto_target_pieces", 0) or 0)
            remaining = max(target - done, 0)

            if not self._step_armed or remaining <= 0:
                # avanti pezzo (o barra)
                if self._bar_idx < 0: self._bar_idx = 0
                if self._bar_idx >= len(self._bars):
                    self._toast("Piano completato.", "ok")
                    self._set_start_light(False)
                    return
                bar = self._bars[self._bar_idx]
                self._piece_idx += 1
                if self._piece_idx >= len(bar):
                    # barra finita → passa alla prossima
                    self._bar_idx += 1
                    self._piece_idx = 0
                    if self._bar_idx >= len(self._bars):
                        self._toast("Piano completato.", "ok")
                        self._set_start_light(False)
                        return
                    bar = self._bars[self._bar_idx]

                piece = bar[self._piece_idx]
                # arma target=1, done=0
                try:
                    setattr(self.machine, "semi_auto_target_pieces", 1)
                    setattr(self.machine, "semi_auto_count_done", 0)
                except Exception:
                    pass
                # posiziona + blocca
                self._do_position(piece["len"], piece["ax"], piece["ad"], self._plan_profile, f"BAR {self._bar_idx+1} #{self._piece_idx+1}")
                self._lock_brake()
                self._step_armed = True
                self._set_start_light(False)
                self._log(f"Step armato: bar={self._bar_idx+1} pezzo={self._piece_idx+1} len={piece['len']:.2f}")
            else:
                # step già armato e non completo → niente; il conteggio avviene sui fronti lama
                self._beep()
            return

        # In manuale lo Start GUI non è necessario (solo per posizionare), il posizionamento lo fai da _start_row
        # Qui non facciamo nulla.

    # --------------------- Contapezzi / Fuori Quota ---------------------
    def _apply_target(self):
        try:
            val = int(self.spin_target.value()) if self.spin_target else 0
            setattr(self.machine, "semi_auto_target_pieces", val)
            self._update_counters_ui()
            self._toast("Target impostato", "ok")
        except Exception:
            pass

    def _reset_counter(self):
        try:
            setattr(self.machine, "semi_auto_count_done", 0)
            self._update_counters_ui()
            self._toast("Contatore azzerato", "ok")
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

        # Sync qty riga attiva (manuale) con remaining
        if self._mode == "manual" and self._active_row is not None and 0 <= self._active_row < (self.tbl_cut.rowCount() if self.tbl_cut else 0):
            # Visualizzo remaining sul campo qty della riga corrente (senza toccare l'array _cutlist)
            if self.tbl_cut:
                self.tbl_cut.setItem(self._active_row, 5, QTableWidgetItem(str(remaining)))

    # --------------------- Sequencer hooks (solo log) ---------------------
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

    def _toast(self, msg, level="info"):
        if hasattr(self.appwin, "toast"):
            try:
                self.appwin.toast.show(msg, level, 2500)
            except Exception:
                pass

    # --------------------- Polling ---------------------
    def on_show(self):
        if self._poll is None:
            self._poll = QTimer(self)
            self._poll.timeout.connect(self._tick)
            self._poll.start(80)  # frequenza alta per edge detection
        self._update_counters_ui()
        if self.status:
            self.status.refresh()

    def _tick(self):
        # Contatori / stato
        self._update_counters_ui()
        if self.status:
            self.status.refresh()

        # Edge detection Start fisico (se abilitato)
        if self.chk_start_phys and self.chk_start_phys.isChecked():
            cur = self._read_start_button()
            if cur and not self._start_prev:
                self._handle_start_trigger()
            self._start_prev = cur
        else:
            self._start_prev = False

        # Edge detection lama → incrementa done quando freno bloccato e target attivo
        cur_blade = self._read_blade_pulse()
        if cur_blade and not self._blade_prev:
            # fronte di salita
            target = int(getattr(self.machine, "semi_auto_target_pieces", 0) or 0)
            done = int(getattr(self.machine, "semi_auto_count_done", 0) or 0)
            remaining = max(target - done, 0)
            if self._brake_locked and target > 0 and remaining > 0:
                try:
                    setattr(self.machine, "semi_auto_count_done", done + 1)
                except Exception:
                    pass
                # Se raggiunto target → sblocco, segnalo e preparo prossimo step selezionabile
                if (done + 1) >= target:
                    self._unlock_brake()
                    self._beep()
                    self._set_start_light(True)  # richiede azione per proseguire
                    # Manuale: riga completata, lasciare all'operatore scegliere nuova riga
                    if self._mode == "manual":
                        # qty a video resta 0 (remaining = 0)
                        self._log("Riga completata. Seleziona una nuova misura.")
                        self._mode = "idle"
                        self._active_row = None
                        self._manual_job = None
                        self._active_initial_target = 0
                    # Plan: step completato, attende nuova pressione per il prossimo pezzo
                    elif self._mode == "plan":
                        self._step_armed = False
        self._blade_prev = cur_blade

    def hideEvent(self, ev):
        if self._poll is not None:
            try:
                self._poll.stop()
            except Exception:
                pass
            self._poll = None
        super().hideEvent(ev)
