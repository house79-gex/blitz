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
from PySide6.QtGui import QKeySequence, QShortcut, QColor, QBrush, QFont

from ui_qt.widgets.header import Header
        # Status pannello già presente nell'app (mostra IO macchina)
from ui_qt.widgets.status_panel import StatusPanel

from ui_qt.logic.planner import plan_ilp, plan_bfd  # (facoltativo, solo informativo)
from ui_qt.logic.sequencer import Sequencer         # segnali/log (non usiamo ciclo)

from ui_qt.services.orders_store import OrdersStore
from ui_qt.dialogs.orders_manager_qt import OrdersManagerDialog

try:
    from ui_qt.utils.settings import read_settings, write_settings
except Exception:
    def read_settings() -> Dict[str, Any]: return {}
    def write_settings(d: Dict[str, Any]) -> None: pass


PANEL_W = 420
PANEL_H = 220

# Dimensioni maggiorate del riquadro "Numero pezzi"
COUNTER_W = 540
COUNTER_H = 180


class AutomaticoPage(QWidget):
    """
    Automatico (pulito):
    - Lista raggruppata per profilo con righe di intestazione (come la viewer) e sola visualizzazione.
    - Start riga: posiziona, attende in‑pos (encoder, tolleranza), quindi BLOCCA; conteggio su input lama; allo scadere target → SBLOCCA.
    - Riquadro Numero pezzi: sola visualizzazione (Target/Tagliati/Rimanenti), senza input né pulsanti; dimensioni aumentate.
    - Ottimizzazione: resta con pulsante 'Ottimizza' (non mostrata qui per brevità), si può mantenere la logica a pezzo/pressione Start fisico.
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
        self.lbl_target: Optional[QLabel] = None
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

        # Piano (se usi ottimizzazione)
        self._plan_profile: str = ""
        self._bars: List[List[Dict[str, float]]] = []
        self._bar_idx: int = -1
        self._piece_idx: int = -1

        # IO & posizionamento
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

        btn_opt = QPushButton("Ottimizza"); btn_opt.setMinimumWidth(110)
        btn_opt.setToolTip("Ottimizza per il profilo selezionato")
        btn_opt.clicked.connect(self._optimize_profile)
        top.addWidget(btn_opt)

        self.chk_start_phys = QCheckBox("Start fisico")
        self.chk_start_phys.setToolTip("Usa il pulsante fisico per avanzare i pezzi in ottimizzazione")
        top.addWidget(self.chk_start_phys)

        top.addStretch(1)

        body = QHBoxLayout(); body.setSpacing(8); root.addLayout(body, 1)

        # Colonna sinistra: Numero pezzi (visual) + cutlist raggruppata
        left = QFrame(); body.addWidget(left, 2)
        ll = QVBoxLayout(left); ll.setContentsMargins(6, 6, 6, 6); ll.setSpacing(8)

        # Numero pezzi (solo visual, più grande)
        cnt_box = QFrame(); cnt_box.setFixedSize(COUNTER_W, COUNTER_H); cnt_box.setFrameShape(QFrame.StyledPanel)
        cnl = QVBoxLayout(cnt_box); cnl.setContentsMargins(12, 12, 12, 12)
        title_cnt = QLabel("NUMERO PEZZI"); title_cnt.setStyleSheet("font-weight:800; font-size:16px;")
        cnl.addWidget(title_cnt)

        row1 = QHBoxLayout()
        row2 = QHBoxLayout()
        row3 = QHBoxLayout()
        big_font = "font-size:24px; font-weight:800;"
        lbl_t = QLabel("Target:"); lbl_t.setStyleSheet(big_font)
        self.lbl_target = QLabel("0"); self.lbl_target.setStyleSheet(big_font)
        row1.addWidget(lbl_t); row1.addWidget(self.lbl_target); row1.addStretch(1)
        lbl_d = QLabel("Tagliati:"); lbl_d.setStyleSheet(big_font)
        self.lbl_done = QLabel("0"); self.lbl_done.setStyleSheet(big_font + "color:#2ecc71;")
        row2.addWidget(lbl_d); row2.addWidget(self.lbl_done); row2.addStretch(1)
        lbl_r = QLabel("Rimanenti:"); lbl_r.setStyleSheet(big_font)
        self.lbl_remaining = QLabel("-"); self.lbl_remaining.setStyleSheet(big_font + "color:#f39c12;")
        row3.addWidget(lbl_r); row3.addWidget(self.lbl_remaining); row3.addStretch(1)

        cnl.addLayout(row1); cnl.addLayout(row2); cnl.addLayout(row3)
        ll.addWidget(cnt_box, 0, alignment=Qt.AlignLeft | Qt.AlignTop)

        # Cutlist raggruppata per profilo (header rows)
        ll.addWidget(QLabel("Cutlist"))
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

        # Azioni riga/ottimizzazione
        row = QHBoxLayout()
        btn_start_row = QPushButton("Start riga"); btn_start_row.setMinimumWidth(120)
        btn_start_row.setToolTip("Posiziona → in‑pos (encoder) → BLOCCA → conteggio lama → SBLOCCA")
        btn_start_row.clicked.connect(self._start_row)
        row.addWidget(btn_start_row)
        btn_next = QPushButton("Avanza (piano)"); btn_next.setMinimumWidth(120)
        btn_next.setToolTip("In ottimizzazione: arma pezzo successivo (target=1), posiziona+blocca; conta su input lama")
        btn_next.clicked.connect(lambda: self._handle_start_trigger(force_plan=True))
        row.addWidget(btn_next)
        row.addStretch(1)
        ll.addLayout(row)

        # Destra: stato macchina
        right = QFrame(); right.setFixedWidth(PANEL_W); body.addWidget(right, 0)
        rl = QVBoxLayout(right); rl.setContentsMargins(6, 6, 6, 6)
        self.status = StatusPanel(self.machine, "STATO", right)
        rl.addWidget(self.status, 1)

        # Space = Start fisico (fallback)
        QShortcut(QKeySequence("Space"), self, activated=self._handle_start_trigger)

    # -------- Helpers UI --------
    def _header_items(self, profile: str) -> List[QTableWidgetItem]:
        it_prof = QTableWidgetItem(profile)
        it_prof.setData(Qt.UserRole, {"type": "header", "profile": profile})
        font = QFont(); font.setBold(True)
        it_prof.setFont(font)
        bg = QBrush(QColor("#ecf0f1"))
        items = [it_prof]
        for _ in range(6):
            it = QTableWidgetItem("")
            it.setBackground(bg)
            it.setFont(font)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            items.append(it)
        for it in items:
            it.setBackground(bg)
        return items

    def _row_is_header(self, row: int) -> bool:
        it = self.tbl_cut.item(row, 0)
        if not it: return False
        meta = it.data(Qt.UserRole)
        return isinstance(meta, dict) and meta.get("type") == "header"

    def _mark_row_finished(self, row: int):
        self._finished_rows.add(row)
        for c in range(self.tbl_cut.columnCount()):
            it = self.tbl_cut.item(row, c)
            if it:
                it.setBackground(QBrush(QColor("#d5f5e3")))
        self.tbl_cut.selectRow(row)

    # -------- Navigazione/Reset --------
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
        self._brake_locked = False; self._blade_prev = False; self._start_prev = False
        self._move_target_mm = 0.0; self._inpos_since = 0.0; self._lock_on_inpos = False
        if self.tbl_cut: self.tbl_cut.setRowCount(0)

    # -------- Import cutlist --------
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
        # Raggruppa per profilo mantenendo l’ordine di apparizione
        groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        order: List[str] = []
        for c in self._cutlist:
            p = str(c.get("profile", "")).strip()
            if p not in groups:
                order.append(p)
            groups[p].append(c)

        for prof in order:
            if prof and prof not in seen:
                seen.add(prof); profs.append(prof)
            # Header riga
            r = self.tbl_cut.rowCount(); self.tbl_cut.insertRow(r)
            hdr_items = self._header_items(prof or "—")
            for col, it in enumerate(hdr_items):
                self.tbl_cut.setItem(r, col, it)
            # Items
            for c in groups[prof]:
                r = self.tbl_cut.rowCount(); self.tbl_cut.insertRow(r)
                row = [
                    QTableWidgetItem(str(c.get("profile",""))),
                    QTableWidgetItem(str(c.get("element",""))),
                    QTableWidgetItem(f"{float(c.get('length_mm',0.0)):.2f}"),
                    QTableWidgetItem(f"{float(c.get('ang_sx',0.0)):.1f}"),
                    QTableWidgetItem(f"{float(c.get('ang_dx',0.0)):.1f}"),
                    QTableWidgetItem(str(int(c.get("qty",0)))),
                    QTableWidgetItem(str(c.get("note","")))
                ]
                # marca come item
                row[0].setData(Qt.UserRole, {"type": "item", "profile": prof})
                for col, it in enumerate(row):
                    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    self.tbl_cut.setItem(r, col, it)

        self._profiles = profs
        self.cmb_profile.clear(); self.cmb_profile.addItems(self._profiles)
        self._mode = "idle"; self._active_row = None; self._manual_job = None
        self._finished_rows.clear()

    # -------- Manuale: Start riga --------
    def _start_row(self):
        r = self.tbl_cut.currentRow()
        if r < 0:
            QMessageBox.information(self, "Start", "Seleziona una riga."); return
        if self._row_is_header(r):
            QMessageBox.information(self, "Start", "Seleziona una riga di elemento (non l’intestazione profilo)."); return
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
        # Arma contapezzi dai dati della riga
        try:
            setattr(self.machine, "semi_auto_target_pieces", int(qty))
            setattr(self.machine, "semi_auto_count_done", 0)
        except Exception: pass
        self._mode = "manual"; self._active_row = r
        self._manual_job = {"profile": prof, "element": elem, "length": L, "ax": ax, "ad": ad}
        self._move_and_arm(L, ax, ad, prof, elem)

    # -------- Ottimizzazione (facoltativo, logica invariata) --------
    def _optimize_profile(self):
        prof = (self.cmb_profile.currentText() or "").strip()
        if not prof:
            QMessageBox.information(self, "Ottimizza", "Seleziona un profilo."); return
        # Aggrega tutti i pezzi di quel profilo
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
                if q > 0:
                    items[(L, ax, ad)] += q
        if not items:
            QMessageBox.information(self, "Ottimizza", f"Nessun pezzo disponibile per '{prof}'."); return
        cfg = read_settings()
        stock = float(cfg.get("opt_stock_mm", 6500.0))
        kerf = float(cfg.get("opt_kerf_mm", 3.0))
        pieces = []
        for (L, ax, ad), q in items.items():
            for _ in range(q): pieces.append({"len": float(L), "ax": float(ax), "ad": float(ad)})
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
        # stato piano
        self._plan_profile = prof; self._bars = bars; self._bar_idx = 0; self._piece_idx = -1
        self._mode = "plan"
        # (Opz) calcolo informativo con ILP/BFD
        solver = str(cfg.get("opt_solver", "ILP")).upper()
        tl = int(cfg.get("opt_time_limit_s", 15))
        try:
            agg_len: Dict[float, int] = defaultdict(int)
            for p in pieces: agg_len[round(p["len"], 2)] += 1
            jobs = [{"id": f"{prof} {L:.2f}", "len": float(L), "qty": int(q)} for L, q in sorted(agg_len.items(), key=lambda t: t[0], reverse=True)]
            self.plan = plan_ilp(jobs, stock=stock, time_limit_s=tl) if solver == "ILP" else plan_bfd(jobs, stock=stock)
        except Exception:
            self.plan = {"solver": solver, "steps": []}
        # abilita Start fisico auto
        if self.chk_start_phys: self.chk_start_phys.setChecked(True)
        self._toast(f"Ottimizzazione pronta per {prof}. Usa Start fisico o 'Avanza (piano)'.", "info")

    # -------- Movimento / Lock freno --------
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

    # -------- Start fisico / Avanza piano --------
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
        # se già armato (target=1 e freno on), attendi il taglio
        tgt = int(getattr(self.machine, "semi_auto_target_pieces", 0) or 0)
        done = int(getattr(self.machine, "semi_auto_count_done", 0) or 0)
        if self._brake_locked and tgt > 0 and done < tgt:
            return
        # Avanza al prossimo pezzo del piano
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

    # -------- UI update / qty --------
    def _dec_row_qty_match(self, profile: str, length: float, ax: float, ad: float):
        # scala la prima riga che matcha profilo+lunghezza+angoli
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
        if self.lbl_done: self.lbl_done.setText(str(done))
        if self.lbl_target: self.lbl_target.setText(str(target))
        if self.lbl_remaining: self.lbl_remaining.setText(str(remaining))
        # Aggiorna qty riga attiva in manuale
        if self._mode == "manual" and self._active_row is not None and 0 <= self._active_row < self.tbl_cut.rowCount():
            if not self._row_is_header(self._active_row):
                self.tbl_cut.setItem(self._active_row, 5, QTableWidgetItem(str(remaining)))
                if remaining == 0:
                    self._mark_row_finished(self._active_row)

    def _set_start_light(self, on: bool):
        try:
            if hasattr(self.machine, "set_light"): self.machine.set_light("start", bool(on))
            else: setattr(self.machine, "start_light_on", bool(on))
        except Exception: pass

    def _toast(self, msg, level="info"):
        if hasattr(self.appwin, "toast"):
            try: self.appwin.toast.show(msg, level, 2500)
            except Exception: pass

    # -------- Sequencer hooks --------
    def _on_step_started(self, idx: int, step: dict): pass
    def _on_step_finished(self, idx: int, step: dict): pass
    def _on_seq_done(self): self._toast("Automatico: completato", "ok")

    # -------- Polling --------
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

        # Lock su in‑pos encoder
        self._try_lock_on_inpos()

        # Start fisico per piano
        if self.chk_start_phys and self.chk_start_phys.isChecked():
            cur = self._read_start_button()
            if cur and not self._start_prev:
                self._handle_start_trigger()
            self._start_prev = cur
        else:
            self._start_prev = False

        # Pulse lama → incremento contatore + effetti
        cur_blade = self._read_blade_pulse()
        if cur_blade and not self._blade_prev:
            tgt = int(getattr(self.machine, "semi_auto_target_pieces", 0) or 0)
            done = int(getattr(self.machine, "semi_auto_count_done", 0) or 0)
            remaining = max(tgt - done, 0)
            if self._brake_locked and tgt > 0 and remaining > 0:
                try: setattr(self.machine, "semi_auto_count_done", done + 1)
                except Exception: pass
                # In piano: scala anche la tabella
                if self._mode == "plan" and self._bars and 0 <= self._bar_idx < len(self._bars) and 0 <= self._piece_idx < len(self._bars[self._bar_idx]):
                    p = self._bars[self._bar_idx][self._piece_idx]
                    self._dec_row_qty_match(self._plan_profile, float(p["len"]), float(p["ax"]), float(p["ad"]))
                # Target raggiunto → sblocca e abilita luce
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
