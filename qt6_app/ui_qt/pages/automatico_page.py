from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple
from collections import defaultdict
import time

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QComboBox, QSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QMessageBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut, QColor, QBrush

from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel

from ui_qt.logic.planner import plan_ilp, plan_bfd  # opzionale (info)
from ui_qt.logic.sequencer import Sequencer         # segnali/log (lasciati)

from ui_qt.services.orders_store import OrdersStore
from ui_qt.dialogs.orders_manager_qt import OrdersManagerDialog
from ui_qt.dialogs.optimization_settings_qt import OptimizationSettingsDialog
from ui_qt.dialogs.log_viewer_qt import LogViewerDialog

try:
    from ui_qt.utils.settings import read_settings, write_settings
except Exception:
    def read_settings() -> Dict[str, Any]: return {}
    def write_settings(d: Dict[str, Any]) -> None: pass


PANEL_W = 420
PANEL_H = 220
COUNTER_W = 420
COUNTER_H = 150


class AutomaticoPage(QWidget):
    """
    Automatico (pulito):
    - Un solo pulsante 'Ottimizza' + 'Impostazioni…' in modale.
    - Posizionamento come Semi-Auto: attesa in-pos da encoder → BLOCCA → conta lama → SBLOCCA.
    - Cutlist: evidenzia selezione (forte) e righe finite (verde). In piano, a ogni taglio scala la riga corrispondente.
    - Log in finestra separata 'Registro…' (nascondibile).
    """

    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine

        # Sequencer per log
        self.plan: Dict[str, Any] = {"solver": "", "steps": []}
        self.seq = Sequencer(appwin)
        self.seq.step_started.connect(self._on_step_started)
        self.seq.step_finished.connect(self._on_step_finished)
        self.seq.finished.connect(self._on_seq_done)

        # UI refs
        self.status: Optional[StatusPanel] = None
        self._poll: Optional[QTimer] = None
        self.tbl_cut: Optional[QTableWidget] = None
        self.spin_target: Optional[QSpinBox] = None
        self.lbl_done: Optional[QLabel] = None
        self.lbl_remaining: Optional[QLabel] = None
        self.chk_start_phys: Optional[QCheckBox] = None
        self.cmb_profile: Optional[QComboBox] = None
        self.btn_opt: Optional[QPushButton] = None
        self.btn_settings: Optional[QPushButton] = None
        self.btn_log: Optional[QPushButton] = None

        # Finestra registro
        self._log_dlg: Optional[LogViewerDialog] = None
        self._log_enabled: bool = bool(read_settings().get("opt_log_enabled", False))

        # Dati importati
        self._orders = OrdersStore()
        self._cutlist: List[Dict[str, Any]] = []
        self._profiles: List[str] = []

        # Stato operativo
        self._mode: str = "idle"  # idle | manual | plan

        # Manuale corrente
        self._active_row: Optional[int] = None
        self._manual_job: Optional[Dict[str, Any]] = None

        # Piano per barre
        self._plan_profile: str = ""
        self._bars: List[List[Dict[str, float]]] = []
        self._bar_idx: int = -1
        self._piece_idx: int = -1

        # Evidenziazione righe finite
        self._finished_rows: set[int] = set()

        # I/O runtime
        self._brake_locked: bool = False
        self._blade_prev: bool = False
        self._start_prev: bool = False

        # Movimento
        self._move_target_mm: float = 0.0
        self._inpos_since: float = 0.0
        self._lock_on_inpos: bool = False

        self._build()

    # -------------------- UI --------------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        root.addWidget(Header(self.appwin, "AUTOMATICO", mode="default",
                              on_home=self._nav_home, on_reset=self._reset_and_home))

        # Top bar (pulsanti corti + tooltip)
        top = QHBoxLayout(); top.setSpacing(8); root.addLayout(top)

        btn_import = QPushButton("Importa…"); btn_import.setToolTip("Importa una cutlist salvata")
        btn_import.setMinimumWidth(110); btn_import.clicked.connect(self._import_cutlist)
        top.addWidget(btn_import)

        top.addWidget(QLabel("Profilo:"))
        self.cmb_profile = QComboBox(); self.cmb_profile.setMinimumWidth(150); top.addWidget(self.cmb_profile)

        self.btn_settings = QPushButton("Impostazioni…")
        self.btn_settings.setToolTip("Apri le impostazioni di ottimizzazione (Stock, Kerf, Solver)")
        self.btn_settings.setMinimumWidth(130)
        self.btn_settings.clicked.connect(self._open_opt_settings)
        top.addWidget(self.btn_settings)

        self.btn_opt = QPushButton("Ottimizza")
        self.btn_opt.setToolTip("Ottimizza per il profilo selezionato (barre miste)")
        self.btn_opt.setMinimumWidth(110)
        self.btn_opt.clicked.connect(self._optimize_profile)
        top.addWidget(self.btn_opt)

        self.chk_start_phys = QCheckBox("Start fisico")
        self.chk_start_phys.setToolTip("Usa il pulsante della pulsantiera per avanzare i pezzi")
        top.addWidget(self.chk_start_phys)

        self.btn_log = QPushButton("Registro…")
        self.btn_log.setToolTip("Apri la finestra del registro eventi")
        self.btn_log.setMinimumWidth(110)
        self.btn_log.clicked.connect(self._open_log)
        top.addWidget(self.btn_log)

        top.addStretch(1)

        # Corpo
        body = QHBoxLayout(); body.setSpacing(8); root.addLayout(body, 1)

        left = QFrame(); body.addWidget(left, 2)
        ll = QVBoxLayout(left); ll.setContentsMargins(6, 6, 6, 6); ll.setSpacing(8)

        # Contapezzi compatto
        cnt = QHBoxLayout()
        cnt.addWidget(QLabel("Target:"))
        self.spin_target = QSpinBox(); self.spin_target.setRange(0, 1_000_000)
        self.spin_target.setValue(int(getattr(self.machine, "semi_auto_target_pieces", 0)))
        btn_set_t = QPushButton("Imposta"); btn_set_t.setToolTip("Imposta manualmente il target")
        btn_set_t.clicked.connect(self._apply_target)
        cnt.addWidget(self.spin_target); cnt.addWidget(btn_set_t)
        cnt.addSpacing(16)
        self.lbl_done = QLabel("Tagliati: 0"); self.lbl_remaining = QLabel("Rimanenti: -")
        cnt.addWidget(self.lbl_done); cnt.addWidget(self.lbl_remaining); cnt.addStretch(1)
        ll.addLayout(cnt)

        # Tabella cutlist
        ll.addWidget(QLabel("Cutlist (seleziona riga e premi Start riga)"))
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
        # Evidenziazione selezione forte
        self.tbl_cut.setStyleSheet("""
            QTableWidget::item:selected { background:#1976d2; color:#ffffff; font-weight:700; }
        """)
        ll.addWidget(self.tbl_cut, 1)

        # Azioni
        row = QHBoxLayout()
        btn_start_row = QPushButton("Start riga")
        btn_start_row.setToolTip("Posiziona → (in‑pos encoder) → BLOCCA → conta lama → SBLOCCA")
        btn_start_row.setMinimumWidth(120)
        btn_start_row.clicked.connect(self._start_row)
        row.addWidget(btn_start_row)

        btn_next = QPushButton("Avanza (piano)")
        btn_next.setToolTip("In piano: arma pezzo successivo (target=1), posiziona+blocca; conta su input lama")
        btn_next.setMinimumWidth(120)
        btn_next.clicked.connect(lambda: self._handle_start_trigger(force_plan=True))
        row.addWidget(btn_next)

        row.addStretch(1)
        ll.addLayout(row)

        # Destra: stato macchina
        right = QFrame(); right.setFixedWidth(PANEL_W)
        body.addWidget(right, 0)
        rl = QVBoxLayout(right); rl.setContentsMargins(6, 6, 6, 6)
        self.status = StatusPanel(self.machine, "STATO", right)
        rl.addWidget(self.status, 1)

        # Space = Start fisico (fallback)
        QShortcut(QKeySequence("Space"), self, activated=self._handle_start_trigger)

    # -------------------- Settings / Log windows --------------------
    def _open_opt_settings(self):
        dlg = OptimizationSettingsDialog(self)
        if dlg.exec() and dlg.result_settings:
            # salviamo già in dialog; qui aggiorniamo flag logging
            self._log_enabled = bool(dlg.result_settings.get("opt_log_enabled", False))

    def _open_log(self):
        if not self._log_dlg:
            self._log_dlg = LogViewerDialog(self, "Registro Automatico")
        self._log_dlg.show()
        self._log_dlg.raise_()
        self._log_dlg.activateWindow()

    # -------------------- Helpers nav/reset --------------------
    def _nav_home(self) -> bool:
        if hasattr(self.appwin, "show_page") and callable(getattr(self.appwin, "show_page")):
            try: self.appwin.show_page("home"); return True
            except Exception: pass
        return False

    def _reset_and_home(self):
        try: self.seq.stop()
        except Exception: pass
        self.plan = {"solver": "", "steps": []}
        self._cutlist.clear(); self._profiles.clear()
        self._mode = "idle"; self._active_row = None; self._manual_job = None
        self._bars.clear(); self._bar_idx = -1; self._piece_idx = -1
        self._finished_rows.clear()
        self._brake_locked = False; self._blade_prev = False; self._start_prev = False
        self._move_target_mm = 0.0; self._inpos_since = 0.0; self._lock_on_inpos = False
        if self.tbl_cut: self.tbl_cut.setRowCount(0)

    # -------------------- Import cutlist --------------------
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
            if not isinstance(cuts, list) or not cuts:
                QMessageBox.information(self, "Importa", "Lista di taglio vuota."); return
            self._load_cutlist(cuts)

    def _load_cutlist(self, cuts: List[Dict[str, Any]]):
        self._cutlist = list(cuts)
        seen = set(); profs: List[str] = []
        self.tbl_cut.setRowCount(0)
        for c in self._cutlist:
            p = str(c.get("profile","")).strip()
            if p and p not in seen: seen.add(p); profs.append(p)
            r = self.tbl_cut.rowCount(); self.tbl_cut.insertRow(r)
            self.tbl_cut.setItem(r, 0, QTableWidgetItem(str(c.get("profile",""))))
            self.tbl_cut.setItem(r, 1, QTableWidgetItem(str(c.get("element",""))))
            self.tbl_cut.setItem(r, 2, QTableWidgetItem(f"{float(c.get('length_mm',0.0)):.2f}"))
            self.tbl_cut.setItem(r, 3, QTableWidgetItem(f"{float(c.get('ang_sx',0.0)):.1f}"))
            self.tbl_cut.setItem(r, 4, QTableWidgetItem(f"{float(c.get('ang_dx',0.0)):.1f}"))
            self.tbl_cut.setItem(r, 5, QTableWidgetItem(str(int(c.get("qty",0)))))
            self.tbl_cut.setItem(r, 6, QTableWidgetItem(str(c.get("note",""))))
        self._profiles = profs
        self.cmb_profile.clear(); self.cmb_profile.addItems(self._profiles)
        self._mode = "idle"; self._active_row = None; self._manual_job = None
        self._bars.clear(); self._bar_idx = -1; self._piece_idx = -1
        self._finished_rows.clear()

    # -------------------- Manuale: Start riga --------------------
    def _start_row(self):
        r = self.tbl_cut.currentRow()
        if r < 0:
            QMessageBox.information(self, "Start", "Seleziona una riga."); return
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
            QMessageBox.information(self, "Start", "Quantità esaurita per questa riga."); return

        # Arma contapezzi
        try:
            setattr(self.machine, "semi_auto_target_pieces", int(qty))
            setattr(self.machine, "semi_auto_count_done", 0)
        except Exception: pass

        # Move → lock su in-pos
        self._mode = "manual"
        self._active_row = r
        self._manual_job = {"profile": prof, "element": elem, "length": L, "ax": ax, "ad": ad}
        self._move_and_arm(L, ax, ad, prof, elem)

    # -------------------- Piano: Ottimizza --------------------
    def _optimize_profile(self):
        prof = (self.cmb_profile.currentText() or "").strip()
        if not prof:
            QMessageBox.information(self, "Ottimizza", "Seleziona un profilo."); return

        cfg = read_settings()
        stock = float(cfg.get("opt_stock_mm", 6500.0))
        kerf = float(cfg.get("opt_kerf_mm", 3.0))
        solver = str(cfg.get("opt_solver", "ILP")).upper()
        tl = int(cfg.get("opt_time_limit_s", 15))

        # Collassa in lista pezzi unitari per profilo selezionato
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
            QMessageBox.information(self, "Ottimizza", "Nessun pezzo disponibile per questo profilo."); return

        pieces = []
        for (L, ax, ad), q in items.items():
            for _ in range(q):
                pieces.append({"len": float(L), "ax": float(ax), "ad": float(ad)})
        # First-Fit Decreasing con kerf
        pieces.sort(key=lambda x: x["len"], reverse=True)
        bars: List[List[Dict[str, float]]] = []
        rem: List[float] = []
        for p in pieces:
            need = p["len"]
            placed = False
            for i in range(len(bars)):
                extra = kerf if bars[i] else 0.0
                if rem[i] >= (need + extra):
                    bars[i].append(p); rem[i] -= (need + extra); placed = True; break
            if not placed:
                bars.append([p]); rem.append(max(stock - need, 0.0))

        self._plan_profile = prof
        self._bars = bars
        self._bar_idx = 0
        self._piece_idx = -1
        self._mode = "plan"

        # Piano informativo (facoltativo)
        if solver == "ILP":
            try:
                jobs = []
                agg_len: Dict[float, int] = defaultdict(int)
                for p in pieces: agg_len[round(p["len"], 2)] += 1
                for L, q in sorted(agg_len.items(), key=lambda t: t[0], reverse=True):
                    jobs.append({"id": f"{prof} {L:.2f}", "len": float(L), "qty": int(q)})
                self.plan = plan_ilp(jobs, stock=stock, time_limit_s=tl)
            except Exception:
                self.plan = {"solver":"ILP","steps":[]}
        else:
            try:
                jobs = []
                agg_len: Dict[float, int] = defaultdict(int)
                for p in pieces: agg_len[round(p["len"], 2)] += 1
                for L, q in sorted(agg_len.items(), key=lambda t: t[0], reverse=True):
                    jobs.append({"id": f"{prof} {L:.2f}", "len": float(L), "qty": int(q)})
                self.plan = plan_bfd(jobs, stock=stock)
            except Exception:
                self.plan = {"solver":"BFD","steps":[]}

        self._log(f"Ottimizzato {prof}: barre={len(bars)} (stock={stock:.0f}, kerf={kerf:.2f})")

    # -------------------- Movimento / In-Pos / Freno --------------------
    def _move_and_arm(self, length: float, ax: float, ad: float, profile: str, element: str):
        # sblocca freno per muovere
        self._unlock_brake(silent=True)
        # set modalità coerente
        if hasattr(self.machine, "set_active_mode"):
            try: self.machine.set_active_mode("semi")
            except Exception: pass
        # comanda movimento
        try:
            if hasattr(self.machine, "position_for_cut"):
                self.machine.position_for_cut(float(length), float(ax), float(ad), profile, element)
            elif hasattr(self.machine, "move_to_length"):
                self.machine.move_to_length(float(length))
            else:
                setattr(self.machine, "position_current", float(length))
        except Exception as e:
            QMessageBox.critical(self, "Posizionamento", str(e)); return
        # prepara lock su in-pos
        self._move_target_mm = float(length)
        self._inpos_since = 0.0
        self._lock_on_inpos = True
        self._log(f"Move → {length:.2f} mm")

    def _try_lock_on_inpos(self):
        if not self._lock_on_inpos:
            return
        tol = float(read_settings().get("inpos_tol_mm", 0.20))
        pos = getattr(self.machine, "encoder_position", None)
        if pos is None:
            pos = getattr(self.machine, "position_current", None)
        try: pos = float(pos) if pos is not None else None
        except Exception: pos = None
        positioning_active = bool(getattr(self.machine, "positioning_active", False))
        in_pos = (pos is not None) and (abs(pos - self._move_target_mm) <= tol)
        if in_pos and not positioning_active:
            now = time.time()
            if self._inpos_since == 0.0:
                self._inpos_since = now; return
            if (now - self._inpos_since) < 0.10:
                return
            # lock freno
            self._lock_brake()
            self._lock_on_inpos = False
            self._log(f"In‑pos {pos:.2f} (±{tol:.2f}) → BLOCCA")

    def _lock_brake(self):
        try:
            if hasattr(self.machine, "set_output"):
                self.machine.set_output("head_brake", True)
            elif hasattr(self.machine, "head_brake_lock"):
                self.machine.head_brake_lock()
            else:
                setattr(self.machine, "brake_active", True)
            self._brake_locked = True
        except Exception: pass

    def _unlock_brake(self, silent: bool = False):
        try:
            if hasattr(self.machine, "set_output"):
                self.machine.set_output("head_brake", False)
            elif hasattr(self.machine, "head_brake_unlock"):
                self.machine.head_brake_unlock()
            else:
                setattr(self.machine, "brake_active", False)
            self._brake_locked = False
            if not silent: self._log("SBLOCCA")
        except Exception: pass

    def _beep(self):
        try:
            if hasattr(self.machine, "beep"): self.machine.beep()
            elif hasattr(self.machine, "buzzer"): self.machine.buzzer(True)
        except Exception: pass

    def _set_start_light(self, on: bool):
        try:
            if hasattr(self.machine, "set_light"): self.machine.set_light("start", bool(on))
            else: setattr(self.machine, "start_light_on", bool(on))
        except Exception: pass

    # -------------------- Start fisico / Avanza piano --------------------
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
        for k in ("blade_cut", "blade_pulse", "cut_pulse", "lama_pulse"):
            if self._read_input(k): return True
        return False

    def _read_start_button(self) -> bool:
        for k in ("start_mobile", "mobile_start_pressed", "start_pressed"):
            if self._read_input(k): return True
        return False

    def _handle_start_trigger(self, force_plan: bool = False):
        # Se attivo Start fisico (o Space) in modalità piano, arma un singolo pezzo
        if (self._mode == "plan" or force_plan) and self._bars:
            # se già armato (brake on e target=1 non completato), beep e nulla
            tgt = int(getattr(self.machine, "semi_auto_target_pieces", 0) or 0)
            done = int(getattr(self.machine, "semi_auto_count_done", 0) or 0)
            if self._brake_locked and tgt > 0 and done < tgt:
                self._beep(); return
            # scegli prossimo pezzo
            if self._bar_idx < 0: self._bar_idx = 0
            if self._bar_idx >= len(self._bars):
                self._toast("Piano completato", "ok"); self._set_start_light(False); return
            bar = self._bars[self._bar_idx]
            self._piece_idx += 1
            if self._piece_idx >= len(bar):
                self._bar_idx += 1; self._piece_idx = 0
                if self._bar_idx >= len(self._bars):
                    self._toast("Piano completato", "ok"); self._set_start_light(False); return
                bar = self._bars[self._bar_idx]
            p = bar[self._piece_idx]
            try:
                setattr(self.machine, "semi_auto_target_pieces", 1)
                setattr(self.machine, "semi_auto_count_done", 0)
            except Exception: pass
            self._move_and_arm(p["len"], p["ax"], p["ad"], self._plan_profile, f"BAR {self._bar_idx+1} #{self._piece_idx+1}")
            self._set_start_light(False)
            return
        # in manuale: lo Start avviene con "Start riga"

    # -------------------- Evidenziazione / Quantità UI --------------------
    def _set_row_color(self, row: int, color_hex: Optional[str]):
        if row < 0 or row >= self.tbl_cut.rowCount(): return
        for c in range(self.tbl_cut.columnCount()):
            it = self.tbl_cut.item(row, c)
            if not it: continue
            if color_hex:
                it.setBackground(QBrush(QColor(color_hex)))
            else:
                it.setBackground(QBrush())

    def _mark_row_finished(self, row: int):
        if row is None or row < 0 or row >= self.tbl_cut.rowCount(): return
        self._finished_rows.add(row)
        self._set_row_color(row, "#d5f5e3")  # verde chiaro
        # mantieni selezione se era la riga attiva
        self.tbl_cut.selectRow(row)

    def _dec_row_qty_match(self, profile: str, length: float, ax: float, ad: float):
        # Trova la prima riga con profilo/length/angoli e qty>0
        n = self.tbl_cut.rowCount()
        for r in range(n):
            try:
                p = self.tbl_cut.item(r, 0).text().strip()
                L = float(self.tbl_cut.item(r, 2).text())
                a1 = float(self.tbl_cut.item(r, 3).text())
                a2 = float(self.tbl_cut.item(r, 4).text())
                q = int(self.tbl_cut.item(r, 5).text())
            except Exception:
                continue
            if p == profile and abs(L - length) <= 0.01 and abs(a1 - ax) <= 0.01 and abs(a2 - ad) <= 0.01 and q > 0:
                new_q = q - 1
                self.tbl_cut.setItem(r, 5, QTableWidgetItem(str(new_q)))
                if new_q == 0:
                    self._mark_row_finished(r)
                return

    # -------------------- Fuori quota / Contapezzi --------------------
    def _apply_target(self):
        try:
            val = int(self.spin_target.value()) if self.spin_target else 0
            setattr(self.machine, "semi_auto_target_pieces", val)
            self._update_counters_ui()
            self._toast("Target impostato", "ok")
        except Exception: pass

    def _update_counters_ui(self):
        done = int(getattr(self.machine, "semi_auto_count_done", 0) or 0)
        target = int(getattr(self.machine, "semi_auto_target_pieces", 0) or 0)
        remaining = max(target - done, 0)
        if self.lbl_done: self.lbl_done.setText(f"Tagliati: {done}")
        if self.lbl_remaining: self.lbl_remaining.setText(f"Rimanenti: {remaining}")
        if self.spin_target and self.spin_target.value() != target: self.spin_target.setValue(target)
        # manuale: sincronizza qty riga attiva e colora se finita
        if self._mode == "manual" and self._active_row is not None and 0 <= self._active_row < self.tbl_cut.rowCount():
            self.tbl_cut.setItem(self._active_row, 5, QTableWidgetItem(str(remaining)))
            if remaining == 0:
                self._mark_row_finished(self._active_row)

    # -------------------- Log helpers --------------------
    def _log(self, s: str):
        if not self._log_enabled:
            return
        if not self._log_dlg:
            self._log_dlg = LogViewerDialog(self, "Registro Automatico")
        try:
            self._log_dlg.append(s)
        except Exception:
            pass

    def _toast(self, msg, level="info"):
        if hasattr(self.appwin, "toast"):
            try: self.appwin.toast.show(msg, level, 2500)
            except Exception: pass

    # -------------------- Sequencer log --------------------
    def _on_step_started(self, idx: int, step: dict): self._log(f"Step {idx+1} start: {step.get('id')}")
    def _on_step_finished(self, idx: int, step: dict): self._log(f"Step {idx+1} done")
    def _on_seq_done(self): self._log("Sequenza completata"); self._toast("Automatico: completato", "ok")

    # -------------------- Polling --------------------
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

        # Lock freno al raggiungimento quota (encoder)
        self._try_lock_on_inpos()

        # Edge Start fisico
        if self.chk_start_phys and self.chk_start_phys.isChecked():
            cur = self._read_start_button()
            if cur and not self._start_prev:
                self._handle_start_trigger()
            self._start_prev = cur
        else:
            self._start_prev = False

        # Edge lama → incrementa contapezzi ed effetti collaterali
        cur_blade = self._read_blade_pulse()
        if cur_blade and not self._blade_prev:
            tgt = int(getattr(self.machine, "semi_auto_target_pieces", 0) or 0)
            done = int(getattr(self.machine, "semi_auto_count_done", 0) or 0)
            remaining = max(tgt - done, 0)
            if self._brake_locked and tgt > 0 and remaining > 0:
                try: setattr(self.machine, "semi_auto_count_done", done + 1)
                except Exception: pass
                # Piano: scala una riga corrispondente
                if self._mode == "plan" and self._bars and 0 <= self._bar_idx < len(self._bars) and 0 <= self._piece_idx < len(self._bars[self._bar_idx]):
                    p = self._bars[self._bar_idx][self._piece_idx]
                    self._dec_row_qty_match(self._plan_profile, float(p["len"]), float(p["ax"]), float(p["ad"]))
                # Target raggiunto → sblocca, segnala, luce ON
                if (done + 1) >= tgt:
                    self._unlock_brake()
                    self._beep()
                    self._set_start_light(True)
                    # in manuale: riga finita, resta evidenziata
                    if self._mode == "manual":
                        # already marked in _update_counters_ui
                        self._mode = "idle"
        self._blade_prev = cur_blade

        # Aggiorna UI contatori
        self._update_counters_ui()

    def hideEvent(self, ev):
        if self._poll is not None:
            try: self._poll.stop()
            except Exception: pass
            self._poll = None
        self._unlock_brake(silent=True)
        super().hideEvent(ev)
