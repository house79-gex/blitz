from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple
from collections import defaultdict
import time

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QComboBox, QSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QMessageBox, QAbstractItemView
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut, QColor, QBrush

from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel

from ui_qt.logic.planner import plan_ilp, plan_bfd
from ui_qt.logic.sequencer import Sequencer

from ui_qt.services.orders_store import OrdersStore
from ui_qt.dialogs.orders_manager_qt import OrdersManagerDialog
from ui_qt.dialogs.optimization_settings_qt import OptimizationSettingsDialog
from ui_qt.dialogs.optimization_run_qt import OptimizationRunDialog

try:
    from ui_qt.utils.settings import read_settings, write_settings
except Exception:
    def read_settings() -> Dict[str, Any]: return {}
    def write_settings(d: Dict[str, Any]) -> None: pass


PANEL_W = 420
PANEL_H = 220


class AutomaticoPage(QWidget):
    """
    Automatico “pulito”:
    - Start riga (manuale): posiziona → attende encoder in‑pos (tol) → BLOCCA → conta lama → SBLOCCA.
    - Ottimizza: apre finestra di riepilogo per profilo; abilita automaticamente Start fisico; si chiude a profilo completato.
    - Cutlist: sola lettura, evidenziazione selezione forte, righe finite in verde.
    """

    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine

        self.plan: Dict[str, Any] = {"solver": "", "steps": []}
        self.seq = Sequencer(appwin)
        self.seq.step_started.connect(self._on_step_started)
        self.seq.step_finished.connect(self._on_step_finished)
        self.seq.finished.connect(self._on_seq_done)

        # UI
        self.status: Optional[StatusPanel] = None
        self._poll: Optional[QTimer] = None
        self.tbl_cut: Optional[QTableWidget] = None
        self.spin_target: Optional[QSpinBox] = None
        self.lbl_done: Optional[QLabel] = None
        self.lbl_remaining: Optional[QLabel] = None
        self.chk_start_phys: Optional[QCheckBox] = None
        self.cmb_profile: Optional[QComboBox] = None

        # Dati
        self._orders = OrdersStore()
        self._cutlist: List[Dict[str, Any]] = []
        self._profiles: List[str] = []

        # Stato
        self._mode: str = "idle"  # idle | manual | plan
        self._active_row: Optional[int] = None
        self._manual_job: Optional[Dict[str, Any]] = None
        self._finished_rows: set[int] = set()

        # Piano
        self._plan_profile: str = ""
        self._bars: List[List[Dict[str, float]]] = []
        self._bar_idx: int = -1
        self._piece_idx: int = -1
        self._opt_dialog: Optional[OptimizationRunDialog] = None

        # IO runtime
        self._brake_locked: bool = False
        self._blade_prev: bool = False
        self._start_prev: bool = False
        self._move_target_mm: float = 0.0
        self._inpos_since: float = 0.0
        self._lock_on_inpos: bool = False

        self._build()

    # ---------------- UI ----------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        root.addWidget(Header(self.appwin, "AUTOMATICO", mode="default",
                              on_home=self._nav_home, on_reset=self._reset_and_home))

        top = QHBoxLayout(); top.setSpacing(8); root.addLayout(top)
        btn_import = QPushButton("Importa…"); btn_import.setMinimumWidth(110)
        btn_import.setToolTip("Importa una cutlist salvata"); btn_import.clicked.connect(self._import_cutlist)
        top.addWidget(btn_import)

        top.addWidget(QLabel("Profilo:"))
        self.cmb_profile = QComboBox(); self.cmb_profile.setMinimumWidth(160)
        top.addWidget(self.cmb_profile)

        btn_settings = QPushButton("Impostazioni…"); btn_settings.setMinimumWidth(130)
        btn_settings.setToolTip("Stock/Kerf/Solver/Time limit"); btn_settings.clicked.connect(self._open_opt_settings)
        top.addWidget(btn_settings)

        btn_opt = QPushButton("Ottimizza"); btn_opt.setMinimumWidth(110)
        btn_opt.setToolTip("Ottimizza per il profilo selezionato"); btn_opt.clicked.connect(self._optimize_profile)
        top.addWidget(btn_opt)

        self.chk_start_phys = QCheckBox("Start fisico")
        self.chk_start_phys.setToolTip("Usa il pulsante fisico per avanzare i pezzi")
        top.addWidget(self.chk_start_phys)

        top.addStretch(1)

        body = QHBoxLayout(); body.setSpacing(8); root.addLayout(body, 1)

        left = QFrame(); body.addWidget(left, 2)
        ll = QVBoxLayout(left); ll.setContentsMargins(6, 6, 6, 6); ll.setSpacing(8)

        cnt = QHBoxLayout()
        cnt.addWidget(QLabel("Target:"))
        self.spin_target = QSpinBox(); self.spin_target.setRange(0, 1_000_000)
        self.spin_target.setValue(int(getattr(self.machine, "semi_auto_target_pieces", 0)))
        btn_set_t = QPushButton("Imposta"); btn_set_t.clicked.connect(self._apply_target)
        cnt.addWidget(self.spin_target); cnt.addWidget(btn_set_t)
        cnt.addSpacing(16)
        self.lbl_done = QLabel("Tagliati: 0"); self.lbl_remaining = QLabel("Rimanenti: -")
        cnt.addWidget(self.lbl_done); cnt.addWidget(self.lbl_remaining); cnt.addStretch(1)
        ll.addLayout(cnt)

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
        self.tbl_cut.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_cut.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_cut.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl_cut.setAlternatingRowColors(True)
        self.tbl_cut.setStyleSheet("QTableWidget::item:selected { background:#1976d2; color:#ffffff; font-weight:700; }")
        ll.addWidget(self.tbl_cut, 1)

        row = QHBoxLayout()
        btn_start_row = QPushButton("Start riga"); btn_start_row.setMinimumWidth(120)
        btn_start_row.setToolTip("Posiziona → in‑pos (encoder) → BLOCCA → conta lama → SBLOCCA")
        btn_start_row.clicked.connect(self._start_row)
        row.addWidget(btn_start_row)

        btn_next = QPushButton("Avanza (piano)"); btn_next.setMinimumWidth(120)
        btn_next.setToolTip("In ottimizzazione: arma pezzo successivo (target=1), posiziona+blocca; conta su input lama")
        btn_next.clicked.connect(lambda: self._handle_start_trigger(force_plan=True))
        row.addWidget(btn_next)
        row.addStretch(1)
        ll.addLayout(row)

        right = QFrame(); right.setFixedWidth(PANEL_W); body.addWidget(right, 0)
        rl = QVBoxLayout(right); rl.setContentsMargins(6, 6, 6, 6)
        self.status = StatusPanel(self.machine, "STATO", right)
        rl.addWidget(self.status, 1)

        QShortcut(QKeySequence("Space"), self, activated=self._handle_start_trigger)

    # --------------- Settings ---------------
    def _open_opt_settings(self):
        dlg = OptimizationSettingsDialog(self)
        dlg.exec()

    # --------------- Navigazione/Reset ---------------
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
        self._finished_rows.clear()
        self._bars.clear(); self._bar_idx = -1; self._piece_idx = -1
        self._opt_dialog = None
        self._brake_locked = False; self._blade_prev = False; self._start_prev = False
        self._move_target_mm = 0.0; self._inpos_since = 0.0; self._lock_on_inpos = False
        if self.tbl_cut: self.tbl_cut.setRowCount(0)

    # --------------- Import cutlist ---------------
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
        self._finished_rows.clear()

    # --------------- Manuale: Start riga ---------------
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
        try:
            setattr(self.machine, "semi_auto_target_pieces", int(qty))
            setattr(self.machine, "semi_auto_count_done", 0)
        except Exception: pass
        self._mode = "manual"; self._active_row = r
        self._manual_job = {"profile": prof, "element": elem, "length": L, "ax": ax, "ad": ad}
        self._move_and_arm(L, ax, ad, prof, elem)

    # --------------- Ottimizza (apre finestra riepilogo) ---------------
    def _optimize_profile(self, profile: Optional[str] = None):
        prof = (profile or self.cmb_profile.currentText() or "").strip()
        if not prof:
            QMessageBox.information(self, "Ottimizza", "Seleziona un profilo."); return
        # costruisci lista per profilo
        rows = [c for c in self._cutlist if str(c.get("profile","")).strip() == prof and int(c.get("qty",0)) > 0]
        if not rows:
            QMessageBox.information(self, "Ottimizza", f"Nessun pezzo per profilo '{prof}'."); return

        # Abilita Start fisico automaticamente
        if self.chk_start_phys: self.chk_start_phys.setChecked(True)

        # Piano per barre (FFD) – stesso algoritmo di prima, ma serve solo per avanzamento “pezzo per pezzo”
        cfg = read_settings()
        stock = float(cfg.get("opt_stock_mm", 6500.0)); kerf = float(cfg.get("opt_kerf_mm", 3.0))
        pieces = []
        for r in rows:
            L = float(r["length_mm"]); ax = float(r["ang_sx"]); ad = float(r["ang_dx"]); q = int(r["qty"])
            for _ in range(q): pieces.append({"len": L, "ax": ax, "ad": ad})
        pieces.sort(key=lambda x: x["len"], reverse=True)
        bars: List[List[Dict[str, float]]] = []; rem: List[float] = []
        for p in pieces:
            need = p["len"]; placed = False
            for i in range(len(bars)):
                extra = kerf if bars[i] else 0.0
                if rem[i] >= (need + extra):
                    bars[i].append(p); rem[i] -= (need + extra); placed = True; break
            if not placed:
                bars.append([p]); rem.append(max(stock - need, 0.0))
        self._plan_profile = prof; self._bars = bars; self._bar_idx = 0; self._piece_idx = -1
        self._mode = "plan"

        # Arma finestra riepilogo
        self._opt_dialog = OptimizationRunDialog(self, profile=prof, rows=rows)
        self._opt_dialog.finished.connect(self._on_opt_dialog_finished)
        self._opt_dialog.show()
        self._opt_dialog.raise_()
        self._opt_dialog.activateWindow()

    def run_optimization_for_profile(self, profile: str):
        """API pubblica per avviare l'ottimizzazione su un profilo (usata da Quote Vani Viewer)."""
        self._optimize_profile(profile)

    def _on_opt_dialog_finished(self, profile: str):
        # quando la finestra si chiude, azzera stato piano
        self._bars.clear(); self._bar_idx = -1; self._piece_idx = -1
        self._mode = "idle"
        self._opt_dialog = None
        self._set_start_light(False)

    # --------------- Movimento/Encoder/Lock ---------------
    def _move_and_arm(self, length: float, ax: float, ad: float, profile: str, element: str):
        self._unlock_brake(silent=True)
        if hasattr(self.machine, "set_active_mode"):
            try: self.machine.set_active_mode("semi")
            except Exception: pass
        try:
            if hasattr(self.machine, "position_for_cut"):
                self.machine.position_for_cut(float(length), float(ax), float(ad), profile, element)
            elif hasattr(self.machine, "move_to_length"):
                self.machine.move_to_length(float(length))
            else:
                setattr(self.machine, "position_current", float(length))
        except Exception as e:
            QMessageBox.critical(self, "Posizionamento", str(e)); return
        self._move_target_mm = float(length); self._inpos_since = 0.0; self._lock_on_inpos = True

    def _try_lock_on_inpos(self):
        if not self._lock_on_inpos: return
        tol = float(read_settings().get("inpos_tol_mm", 0.20))
        pos = getattr(self.machine, "encoder_position", None)
        if pos is None: pos = getattr(self.machine, "position_current", None)
        try: pos = float(pos) if pos is not None else None
        except Exception: pos = None
        in_mov = bool(getattr(self.machine, "positioning_active", False))
        in_pos = (pos is not None) and (abs(pos - self._move_target_mm) <= tol)
        if in_pos and not in_mov:
            now = time.time()
            if self._inpos_since == 0.0:
                self._inpos_since = now; return
            if (now - self._inpos_since) < 0.10:
                return
            self._lock_brake()
            self._lock_on_inpos = False

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

    # --------------- Start fisico / avanzamento piano ---------------
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
        if (self._mode != "plan") and not force_plan:
            return
        if not self._bars:
            return
        # Se già armato (freno attivo e target>done), attendo taglio
        tgt = int(getattr(self.machine, "semi_auto_target_pieces", 0) or 0)
        done = int(getattr(self.machine, "semi_auto_count_done", 0) or 0)
        if self._brake_locked and tgt > 0 and done < tgt:
            self._beep(); return
        # Avanza pezzo
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
        piece = bar[self._piece_idx]
        try:
            setattr(self.machine, "semi_auto_target_pieces", 1)
            setattr(self.machine, "semi_auto_count_done", 0)
        except Exception: pass
        self._move_and_arm(piece["len"], piece["ax"], piece["ad"], self._plan_profile, f"BAR {self._bar_idx+1} #{self._piece_idx+1}")
        self._set_start_light(False)

    # --------------- UI helpers ---------------
    def _apply_target(self):
        try:
            val = int(self.spin_target.value()) if self.spin_target else 0
            setattr(self.machine, "semi_auto_target_pieces", val)
            self._update_counters_ui()
            self._toast("Target impostato", "ok")
        except Exception: pass

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
        self._finished_rows.add(row)
        self._set_row_color(row, "#d5f5e3")
        self.tbl_cut.selectRow(row)

    def _dec_row_qty_match(self, profile: str, length: float, ax: float, ad: float):
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

    def _update_counters_ui(self):
        done = int(getattr(self.machine, "semi_auto_count_done", 0) or 0)
        target = int(getattr(self.machine, "semi_auto_target_pieces", 0) or 0)
        remaining = max(target - done, 0)
        if self.lbl_done: self.lbl_done.setText(f"Tagliati: {done}")
        if self.lbl_remaining: self.lbl_remaining.setText(f"Rimanenti: {remaining}")
        if self.spin_target and self.spin_target.value() != target: self.spin_target.setValue(target)
        if self._mode == "manual" and self._active_row is not None and 0 <= self._active_row < self.tbl_cut.rowCount():
            self.tbl_cut.setItem(self._active_row, 5, QTableWidgetItem(str(remaining)))
            if remaining == 0:
                self._mark_row_finished(self._active_row)

    def _log(self, s: str):
        # opzionale: puoi integrare un registro separato se serve
        pass

    def _toast(self, msg, level="info"):
        if hasattr(self.appwin, "toast"):
            try: self.appwin.toast.show(msg, level, 2500)
            except Exception: pass

    # --------------- Sequencer hooks ---------------
    def _on_step_started(self, idx: int, step: dict): self._log(f"Step {idx+1} start: {step.get('id')}")
    def _on_step_finished(self, idx: int, step: dict): self._log(f"Step {idx+1} done")
    def _on_seq_done(self): self._log("Sequenza completata"); self._toast("Automatico: completato", "ok")

    # --------------- Polling ---------------
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

        # Start fisico
        if self.chk_start_phys and self.chk_start_phys.isChecked():
            cur = self._read_start_button()
            if cur and not self._start_prev:
                self._handle_start_trigger()
            self._start_prev = cur
        else:
            self._start_prev = False

        # Pulse lama
        cur_blade = self._read_blade_pulse()
        if cur_blade and not self._blade_prev:
            tgt = int(getattr(self.machine, "semi_auto_target_pieces", 0) or 0)
            done = int(getattr(self.machine, "semi_auto_count_done", 0) or 0)
            remaining = max(tgt - done, 0)
            if self._brake_locked and tgt > 0 and remaining > 0:
                try: setattr(self.machine, "semi_auto_count_done", done + 1)
                except Exception: pass
                # Scala riga “match” in tabella
                if self._mode == "plan" and self._bars and 0 <= self._bar_idx < len(self._bars) and 0 <= self._piece_idx < len(self._bars[self._bar_idx]):
                    p = self._bars[self._bar_idx][self._piece_idx]
                    self._dec_row_qty_match(self._plan_profile, float(p["len"]), float(p["ax"]), float(p["ad"]))
                    # Aggiorna anche finestra di ottimizzazione
                    if self._opt_dialog:
                        self._opt_dialog.update_after_cut(p["len"], p["ax"], p["ad"])
                # target raggiunto → unlock + luce
                if (done + 1) >= tgt:
                    self._unlock_brake()
                    self._set_start_light(True)
                    if self._mode == "manual" and self._active_row is not None:
                        self._mark_row_finished(self._active_row)
                        self._mode = "idle"
        self._blade_prev = cur_blade

        self._update_counters_ui()

    def hideEvent(self, ev):
        if self._poll is not None:
            try: self._poll.stop()
            except Exception: pass
            self._poll = None
        self._unlock_brake(silent=True)
        super().hideEvent(ev)
