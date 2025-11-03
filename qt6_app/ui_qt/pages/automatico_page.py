from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple
from collections import defaultdict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QComboBox, QSpinBox, QTreeWidget, QTreeWidgetItem, QTextEdit, QCheckBox,
    QSizePolicy, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut

from ui_qt.widgets.header import Header
from ui_qt.utils.settings import read_settings
from ui_qt.logic.planner import plan_ilp, plan_bfd  # opzionali (solo suggerimento)
from ui_qt.logic.sequencer import Sequencer         # lasciato per compatibilità segnali/log
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
    Modalità Automatico con controllo 'a colpo' (no ciclo):
    - Import cutlist (type=cutlist)
    - Manuale per riga: seleziona riga -> Start = posizionamento singolo, contapezzi impostato a qty riga e decresce ad ogni taglio (come Semi-Auto)
    - Ottimizzazione per profilo: aggrega tutte le lunghezze del profilo in ordine decrescente; Start fisico avanza gli step (ogni pressione arma/posiziona lo step successivo o ripete quello corrente finché non termina)
    """

    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine

        # Sequencer tenuto per compatibilità (log/eventi), non guidiamo cicli automatici
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
        self.chk_start_phys: Optional[QCheckBox] = None

        self.log: Optional[QTextEdit] = None
        self.tree: Optional[QTreeWidget] = None

        # Cutlist importata
        self._orders = OrdersStore()
        self._cutlist: List[Dict[str, Any]] = []  # {profile, element, length_mm, ang_sx, ang_dx, qty, note}
        self._profiles: List[str] = []

        # Stato operativo
        self._mode: str = "idle"  # idle | manual | plan
        self._active_row: Optional[int] = None
        self._manual_job: Optional[Dict[str, Any]] = None  # prof, elem, L, ax, ad
        self._last_start_edge: bool = False

        # Piano ottimizzato
        self._plan_profile: str = ""
        self._plan_pairs: List[Tuple[float, int]] = []  # [(length, qty)]
        self._plan_idx: int = -1   # indice step corrente (-1 = nessuno)
        self._plan_armed: bool = False  # se abbiamo impostato target/done per lo step corrente

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
        self._cutlist = []
        self._profiles = []
        self._mode = "idle"
        self._active_row = None
        self._manual_job = None
        self._plan_profile = ""
        self._plan_pairs = []
        self._plan_idx = -1
        self._plan_armed = False
        if self.tree:
            self.tree.clear()
        if self.log:
            self.log.clear()
        try:
            self.tbl_cut.clearContents()
            self.tbl_cut.setRowCount(0)
        except Exception:
            pass

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

        # Selettore profilo + optimizer
        ctrl.addWidget(QLabel("Profilo:"))
        self.cmb_profile = QComboBox()
        ctrl.addWidget(self.cmb_profile)

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

        btn_opt = QPushButton("Ottimizza profilo")
        btn_opt.setToolTip("Aggrega tutte le lunghezze del profilo selezionato (ordine decrescente). Non avvia cicli.")
        btn_opt.clicked.connect(self._optimize_profile)
        ctrl.addWidget(btn_opt)

        # Start fisico
        self.chk_start_phys = QCheckBox("Start fisico")
        self.chk_start_phys.setToolTip("Usa il pulsante fisico sulla pulsantiera mobile per i posizionamenti")
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

        # Contapezzi (allineato Semi-Auto)
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
        btn_set_t.setToolTip("Imposta manualmente il target del contapezzi (non necessario in modalità Start per riga/step)")
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
        ll.addWidget(QLabel("Cutlist importata (seleziona riga e premi 'Start posizionamento riga')"))
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
        btn_start_one = QPushButton("Start posizionamento riga")
        btn_start_one.setToolTip("Posiziona la macchina alla misura della riga selezionata e arma il contapezzi con la sua quantità")
        btn_start_one.clicked.connect(self._start_row_positioning)
        action_row.addWidget(btn_start_one)

        btn_start_next_step = QPushButton("Avanza step (piano)")
        btn_start_next_step.setToolTip("Usa quando hai ottimizzato il profilo: arma/posiziona il prossimo step o ripeti quello corrente")
        btn_start_next_step.clicked.connect(self._plan_manual_advance)
        action_row.addWidget(btn_start_next_step)

        action_row.addStretch(1)
        ll.addLayout(action_row)

        # Destra: stato macchina + log + fuori quota
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

        # Shortcut tastiera per simulare Start fisico (barra spaziatrice)
        QShortcut(QKeySequence("Space"), self, activated=self._handle_physical_start_press)

    # --------- Import cutlist ----------
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
            self._load_cutlist(cuts)
            self._toast("Cutlist importata", "ok")

    def _load_cutlist(self, cuts: List[Dict[str, Any]]):
        self._cutlist = list(cuts)
        # Popola profili (ordine di apparizione)
        profs: List[str] = []
        for c in self._cutlist:
            p = str(c.get("profile", "")).strip()
            if p and p not in profs:
                profs.append(p)
        self._profiles = profs
        self.cmb_profile.clear()
        self.cmb_profile.addItems(self._profiles)

        # Tabella
        self.tbl_cut.setRowCount(0)
        for c in self._cutlist:
            r = self.tbl_cut.rowCount()
            self.tbl_cut.insertRow(r)
            self.tbl_cut.setItem(r, 0, QTableWidgetItem(str(c.get("profile", ""))))
            self.tbl_cut.setItem(r, 1, QTableWidgetItem(str(c.get("element", ""))))
            self.tbl_cut.setItem(r, 2, QTableWidgetItem(f"{float(c.get('length_mm', 0.0)):.2f}"))
            self.tbl_cut.setItem(r, 3, QTableWidgetItem(f"{float(c.get('ang_sx', 0.0)):.1f}"))
            self.tbl_cut.setItem(r, 4, QTableWidgetItem(f"{float(c.get('ang_dx', 0.0)):.1f}"))
            self.tbl_cut.setItem(r, 5, QTableWidgetItem(str(int(c.get("qty", 0)))))
            self.tbl_cut.setItem(r, 6, QTableWidgetItem(str(c.get("note", ""))))

        # Reset stato
        self._mode = "idle"
        self._active_row = None
        self._manual_job = None
        self._plan_profile = ""
        self._plan_pairs = []
        self._plan_idx = -1
        self._plan_armed = False

    # --------- Manuale: riga selezionata ----------
    def _start_row_positioning(self):
        r = self.tbl_cut.currentRow()
        if r < 0:
            QMessageBox.information(self, "Posizionamento", "Seleziona una riga.")
            return
        try:
            prof = self.tbl_cut.item(r, 0).text()
            elem = self.tbl_cut.item(r, 1).text()
            length = float(self.tbl_cut.item(r, 2).text())
            ax = float(self.tbl_cut.item(r, 3).text())
            ad = float(self.tbl_cut.item(r, 4).text())
            qty = int(self.tbl_cut.item(r, 5).text())
        except Exception:
            QMessageBox.critical(self, "Posizionamento", "Riga non valida.")
            return
        if qty <= 0:
            QMessageBox.information(self, "Posizionamento", "Quantità già esaurita per questa riga.")
            return

        # Arma contapezzi solo se cambiamo job o non è già armato su questa riga
        if not (self._mode == "manual" and self._active_row == r and self._manual_job and
                getattr(self.machine, "semi_auto_target_pieces", 0) == qty):
            try:
                setattr(self.machine, "semi_auto_target_pieces", int(qty))
                setattr(self.machine, "semi_auto_count_done", 0)
            except Exception:
                pass

        self._active_row = r
        self._manual_job = {"profile": prof, "element": elem, "length": length, "ax": ax, "ad": ad}
        self._mode = "manual"

        # Posiziona una volta (ogni taglio successivo richiede una nuova pressione Start: fisico o bottone)
        self._do_position(length, ax, ad, prof, elem)
        self._log(f"Armata riga: {prof} | {elem} | {length:.2f} mm (qty={qty})")

    # --------- Ottimizzazione per profilo ----------
    def _optimize_profile(self):
        prof = (self.cmb_profile.currentText() or "").strip()
        if not prof:
            QMessageBox.information(self, "Ottimizza", "Seleziona un profilo.")
            return

        # Aggrega tutte le lunghezze del profilo, somma le qty e ordina desc
        agg: Dict[float, int] = defaultdict(int)
        for r in range(self.tbl_cut.rowCount()):
            if self.tbl_cut.item(r, 0) and self.tbl_cut.item(r, 0).text().strip() == prof:
                try:
                    L = round(float(self.tbl_cut.item(r, 2).text()), 2)
                    q = int(self.tbl_cut.item(r, 5).text())
                except Exception:
                    continue
                if q > 0:
                    agg[L] += q
        if not agg:
            QMessageBox.information(self, "Ottimizza", "Nessun pezzo da ottimizzare per questo profilo.")
            return

        pairs = sorted([(L, q) for L, q in agg.items()], key=lambda x: x[0], reverse=True)
        self._plan_profile = prof
        self._plan_pairs = pairs
        self._plan_idx = -1
        self._plan_armed = False
        self._mode = "plan"

        # (Opzionale) suggerimento piano con ILP/BFD
        solver = self.cb_solver.currentText()
        jobs = [{"id": f"{prof} {L:.2f}", "len": float(L), "qty": int(q)} for (L, q) in pairs]
        try:
            if solver == "ILP":
                self.plan = plan_ilp(jobs, stock=None, time_limit_s=int(self.spin_tl.value()))
            else:
                self.plan = plan_bfd(jobs, stock=None)
        except Exception:
            self.plan = {"solver": solver, "steps": [{"id": j["id"], "len": j["len"], "qty": j["qty"]} for j in jobs]}

        # Log del piano
        self._log(f"Piano {self.plan.get('solver','')} per profilo {prof}:")
        for i, st in enumerate(self.plan.get("steps", []), start=1):
            self._log(f"{i:>2}. {st.get('id','')} | len={st.get('len')} | qty={st.get('qty')}")
        self._toast("Ottimizzazione pronta. Usa 'Avanza step (piano)' o lo Start fisico.", "info")

    def _plan_manual_advance(self):
        """Avanza piano manualmente via bottone (equivalente allo Start fisico in modalità plan)"""
        self._handle_start_trigger(mode_hint="plan")

    # --------- Posizionamenti ----------
    def _do_position(self, length: float, ax: float, ad: float, profile: str, element: str):
        try:
            if hasattr(self.machine, "position_for_cut"):
                self.machine.position_for_cut(float(length), float(ax), float(ad), profile, element)
            elif hasattr(self.machine, "move_to_length"):
                self.machine.move_to_length(float(length))
            else:
                setattr(self.machine, "pending_cut", {"profile": profile, "element": element,
                                                      "length_mm": float(length), "ang_sx": float(ax), "ang_dx": float(ad)})
            self._log(f"Posizionamento: {profile} | {element} | {length:.2f} mm ({ax:.1f}/{ad:.1f})")
            self._toast("Posizionamento inviato", "ok")
        except Exception as e:
            QMessageBox.critical(self, "Posizionamento", str(e))

    # --------- Start fisico / handling ----------
    def _read_physical_start(self) -> bool:
        """
        Legge lo stato del pulsante fisico Start sulla pulsantiera mobile.
        Implementazione best-effort: prova diverse proprietà/metodi che potrebbero essere esposti dal driver macchina.
        """
        try:
            if hasattr(self.machine, "mobile_start_pressed"):
                return bool(getattr(self.machine, "mobile_start_pressed"))
            if hasattr(self.machine, "read_input") and callable(getattr(self.machine, "read_input")):
                # se il driver espone una read_input con chiave
                try:
                    return bool(self.machine.read_input("start_mobile"))
                except Exception:
                    pass
            if hasattr(self.machine, "start_pressed"):
                return bool(getattr(self.machine, "start_pressed"))
        except Exception:
            pass
        return False

    def _handle_physical_start_press(self):
        """Fallback da tastiera: Space simula il fronte di Start fisico"""
        self._handle_start_trigger()

    def _handle_start_trigger(self, mode_hint: Optional[str] = None):
        if mode_hint == "plan" and self._mode != "plan":
            # se l'utente chiede di avanzare piano ma non siamo in plan, ignora
            return

        if self._mode == "manual" and self._manual_job:
            # remaining basato su contapezzi
            done = int(getattr(self.machine, "semi_auto_count_done", 0) or 0)
            target = int(getattr(self.machine, "semi_auto_target_pieces", 0) or 0)
            remaining = max(target - done, 0)
            if remaining <= 0:
                self._toast("Riga completata. Seleziona un'altra riga.", "info")
                return
            j = self._manual_job
            self._do_position(j["length"], j["ax"], j["ad"], j["profile"], j["element"])
            return

        if self._mode == "plan" and self._plan_pairs:
            done = int(getattr(self.machine, "semi_auto_count_done", 0) or 0)
            target = int(getattr(self.machine, "semi_auto_target_pieces", 0) or 0)
            remaining = max(target - done, 0)

            if not self._plan_armed or remaining <= 0:
                # Attiva prossimo step
                self._plan_idx += 1
                if self._plan_idx >= len(self._plan_pairs):
                    self._toast("Piano completato.", "ok")
                    self._plan_idx = len(self._plan_pairs) - 1
                    self._plan_armed = False
                    return
                L, q = self._plan_pairs[self._plan_idx]
                try:
                    setattr(self.machine, "semi_auto_target_pieces", int(q))
                    setattr(self.machine, "semi_auto_count_done", 0)
                except Exception:
                    pass
                self._plan_armed = True
                # Angoli ignoti in piano: usiamo 0/0; l'operatore può selezionare misure coerenti con la cutlist originale
                self._do_position(L, 0.0, 0.0, self._plan_profile, f"STEP {self._plan_idx+1}")
            else:
                # Step in corso: ripeti posizionamento stesso step
                L, _q = self._plan_pairs[self._plan_idx]
                self._do_position(L, 0.0, 0.0, self._plan_profile, f"STEP {self._plan_idx+1}")

    # --------- Contapezzi / Fuori Quota ----------
    def _apply_target(self):
        try:
            val = int(self.spin_target.value()) if self.spin_target else 0
            setattr(self.machine, "semi_auto_target_pieces", val)
            # non azzero done qui per non rompere i conteggi durante lavorazioni attive
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

        # Sincronizza qty tabella per riga attiva in manuale
        if self._mode == "manual" and self._active_row is not None and 0 <= self._active_row < self.tbl_cut.rowCount():
            self.tbl_cut.setItem(self._active_row, 5, QTableWidgetItem(str(remaining)))

    # --------- Sequencer hooks (solo log) ----------
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

    # --------- Polling ----------
    def on_show(self):
        if self._poll is None:
            self._poll = QTimer(self)
            self._poll.timeout.connect(self._tick)
            self._poll.start(120)  # refresh veloce per start fisico e contatori
        self._update_counters_ui()
        if self.status:
            self.status.refresh()

    def _tick(self):
        # Aggiorna contatori e stato pannello
        self._update_counters_ui()
        if self.status:
            self.status.refresh()

        # Edge detection del pulsante fisico (se abilitato)
        if self.chk_start_phys and self.chk_start_phys.isChecked():
            cur = self._read_physical_start()
            if cur and not self._last_start_edge:
                self._handle_start_trigger()
            self._last_start_edge = cur

    def hideEvent(self, ev):
        if self._poll is not None:
            try:
                self._poll.stop()
            except Exception:
                pass
            self._poll = None
        super().hideEvent(ev)
