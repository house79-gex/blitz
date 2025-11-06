from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple
from collections import defaultdict
import time

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QAbstractItemView, QSizePolicy,
    QDialog, QFormLayout, QLineEdit, QComboBox, QDialogButtonBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut, QColor, QBrush, QFont, QKeyEvent

from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel
from ui_qt.logic.planner import plan_ilp, plan_bfd
from ui_qt.logic.sequencer import Sequencer
from ui_qt.services.orders_store import OrdersStore
from ui_qt.dialogs.orders_manager_qt import OrdersManagerDialog
from ui_qt.dialogs.optimization_run_qt import OptimizationRunDialog

try:
    from ui_qt.utils.settings import read_settings, write_settings
except Exception:
    def read_settings() -> Dict[str, Any]: return {}
    def write_settings(d: Dict[str, Any]) -> None: pass

# Compatibilità QSizePolicy Expanding (varia tra versioni PySide6)
try:
    POL_EXP = QSizePolicy.Policy.Expanding
except AttributeError:
    POL_EXP = QSizePolicy.Expanding

PANEL_W = 420


class OptimizationConfigDialog(QDialog):
    """Dialog per configurare stock/kerf/solver/time limit (persistenza in settings)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurazione ottimizzazione")
        cfg = read_settings()
        stock = str(cfg.get("opt_stock_mm", 6500.0))
        kerf = str(cfg.get("opt_kerf_mm", 3.0))
        solver = str(cfg.get("opt_solver", "ILP")).upper()
        time_limit = str(cfg.get("opt_time_limit_s", 15))

        form = QFormLayout(self)
        self.ed_stock = QLineEdit(stock); self.ed_stock.setPlaceholderText("6500.0")
        self.ed_kerf = QLineEdit(kerf); self.ed_kerf.setPlaceholderText("3.0")
        self.cmb_solver = QComboBox(); self.cmb_solver.addItems(["ILP", "BFD"])
        self.cmb_solver.setCurrentText("ILP" if solver != "BFD" else "BFD")
        self.ed_time = QLineEdit(time_limit); self.ed_time.setPlaceholderText("15")

        form.addRow("Lunghezza barra (mm):", self.ed_stock)
        form.addRow("Kerf (mm):", self.ed_kerf)
        form.addRow("Solver:", self.cmb_solver)
        form.addRow("Time limit (s, ILP):", self.ed_time)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        btns.accepted.connect(self._save_and_close)
        btns.rejected.connect(self.reject)
        form.addRow(btns)
        try:
            self.resize(380, 180)
        except Exception:
            pass

    def _save_and_close(self):
        cfg = dict(read_settings())
        try: cfg["opt_stock_mm"] = float((self.ed_stock.text() or "0").replace(",", "."))
        except Exception: pass
        try: cfg["opt_kerf_mm"] = float((self.ed_kerf.text() or "0").replace(",", "."))
        except Exception: pass
        cfg["opt_solver"] = self.cmb_solver.currentText().upper()
        try: cfg["opt_time_limit_s"] = int(float((self.ed_time.text() or "0").replace(",", ".")))
        except Exception: pass
        write_settings(cfg)
        self.accept()


class AutomaticoPage(QWidget):
    """
    Automatico (layout a due colonne come l'originale):
    - Sinistra: Cutlist viewer in un frame, più alta, con pulsante Start (verde) centrato sotto.
    - Destra: due frame "in alto" (Contapezzi e Status).
    - Toolbar: Importa, Ottimizza, Config. ottimizzazione.
      Nota: "Start fisico" e "Auto-continue" non sono visibili: sono attivi automaticamente.

    Logica:
    - Auto-continue: se il pezzo successivo ha stessa quota/angoli entro tolleranza, prosegue senza
      sbloccare/ribloccare il freno e senza muovere (arma solo contatore).
    - Decremento quantità: la colonna Q.tà nella viewer principale arriva a 0 correttamente.
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
        self.tbl_cut: Optional[QTableWidget] = None
        self.lbl_target: Optional[QLabel] = None
        self.lbl_done: Optional[QLabel] = None
        self.lbl_remaining: Optional[QLabel] = None
        self.status: Optional[StatusPanel] = None
        self.btn_start_row: Optional[QPushButton] = None
        self.viewer_frame: Optional[QFrame] = None  # frame contenitore della cutlist (per overlay della dialog)

        # Dati
        self._orders = OrdersStore()

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

        # Dialog ottimizzazione
        self._opt_dialog: Optional[OptimizationRunDialog] = None

        # IO runtime
        self._brake_locked: bool = False
        self._blade_prev: bool = False
        self._start_prev: bool = False
        self._move_target_mm: float = 0.0
        self._inpos_since: float = 0.0
        self._lock_on_inpos: bool = False
        self._poll: Optional[QTimer] = None

        # Abilitazioni automatiche
        self._start_phys_enabled: bool = True  # sempre attivo
        self._auto_continue_always: bool = True  # sempre attivo

        # Tolleranze auto-continue (da settings se presenti)
        cfg = read_settings()
        try:
            self._same_len_tol = float(cfg.get("auto_same_len_tol_mm", 0.10))
        except Exception:
            self._same_len_tol = 0.10
        try:
            self._same_ang_tol = float(cfg.get("auto_same_ang_tol_deg", 0.10))
        except Exception:
            self._same_ang_tol = 0.10

        self._build()

    # ---------------- UI build ----------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Header
        root.addWidget(Header(self.appwin, "AUTOMATICO", mode="default",
                              on_home=self._nav_home, on_reset=self._reset_and_home))

        # Toolbar
        top = QHBoxLayout()
        btn_import = QPushButton("Importa…")
        btn_import.setToolTip("Importa una cutlist salvata")
        btn_import.clicked.connect(self._import_cutlist)
        top.addWidget(btn_import)

        btn_opt = QPushButton("Ottimizza")
        btn_opt.setToolTip("Ottimizza il profilo dell’intestazione selezionata; se nulla selezionato, usa la prima intestazione.")
        btn_opt.clicked.connect(self._on_optimize_clicked)
        top.addWidget(btn_opt)

        btn_cfg = QPushButton("Config. ottimizzazione…")
        btn_cfg.setToolTip("Configura stock, kerf e solver")
        btn_cfg.clicked.connect(self._open_opt_config)
        top.addWidget(btn_cfg)

        top.addStretch(1)
        root.addLayout(top)

        # Corpo a due colonne
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(8)
        root.addLayout(body, 1)

        # Colonna sinistra: viewer + start
        left = QFrame(); left.setSizePolicy(POL_EXP, POL_EXP)
        ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0); ll.setSpacing(8)

        viewer_frame = QFrame()
        viewer_frame.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius: 6px; }")
        self.viewer_frame = viewer_frame
        vf = QVBoxLayout(viewer_frame); vf.setContentsMargins(6, 6, 6, 6); vf.setSpacing(6)

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
        self.tbl_cut.cellDoubleClicked.connect(self._on_cell_double_clicked)
        vf.addWidget(self.tbl_cut, 1)

        ll.addWidget(viewer_frame, 1)

        start_row = QHBoxLayout(); start_row.addStretch(1)
        self.btn_start_row = QPushButton("Start")
        self.btn_start_row.setToolTip("Posiziona → in‑pos (encoder) → BLOCCA → conta → SBLOCCA")
        self.btn_start_row.setMinimumHeight(48)
        self.btn_start_row.setStyleSheet(
            "QPushButton { background:#2ecc71; color:white; font-weight:800; font-size:18px; "
            "padding:12px 32px; border-radius:10px; } "
            "QPushButton:hover { background:#27ae60; } "
            "QPushButton:pressed { background:#239b56; }"
        )
        self.btn_start_row.clicked.connect(self._start_row)
        start_row.addWidget(self.btn_start_row, 0, Qt.AlignCenter)
        start_row.addStretch(1)
        ll.addLayout(start_row)

        body.addWidget(left, 1)

        # Colonna destra: contapezzi + status
        right = QFrame(); right.setFixedWidth(PANEL_W)
        rl = QVBoxLayout(right); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(8)

        cnt_box = QFrame()
        cnt_box.setFrameShape(QFrame.StyledPanel)
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

        status_wrap = QFrame()
        status_wrap.setFrameShape(QFrame.StyledPanel)
        status_wrap.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius: 6px; }")
        swl = QVBoxLayout(status_wrap); swl.setContentsMargins(6, 6, 6, 6)
        self.status = StatusPanel(self.machine, "STATO", status_wrap)
        swl.addWidget(self.status)
        rl.addWidget(status_wrap, 0)
        rl.addStretch(1)

        body.addWidget(right, 0)

        # Scorciatoia: Space = Start (in plan)
        QShortcut(QKeySequence("Space"), self, activated=self._handle_start_trigger)

    # ---------------- Helpers intestazione ----------------
    def _row_is_header(self, row: int) -> bool:
        it = self.tbl_cut.item(row, 0)
        if not it: return False
        return not bool(it.flags() & Qt.ItemIsSelectable)

    def _find_first_header_profile(self) -> Optional[str]:
        for r in range(self.tbl_cut.rowCount()):
            if self._row_is_header(r):
                it = self.tbl_cut.item(r, 0)
                if it:
                    return it.text().strip()
        return None

    # ---------------- Navigazione/Reset ----------------
    def _nav_home(self) -> bool:
        if hasattr(self.appwin, "show_page") and callable(getattr(self.appwin, "show_page")):
            try: self.appwin.show_page("home"); return True
            except Exception: pass
        return False

    def _reset_and_home(self):
        try: self.seq.stop()
        except Exception: pass
        self.plan = {"solver": "", "steps": []}
        self._mode = "idle"; self._active_row = None; self._manual_job = None
        self._finished_rows.clear()
        self._bars.clear(); self._bar_idx = -1; self._piece_idx = -1
        self._brake_locked = False; self._blade_prev = False; self._start_prev = False
        self._move_target_mm = 0.0; self._inpos_since = 0.0; self._lock_on_inpos = False
        if self.tbl_cut: self.tbl_cut.setRowCount(0)

    # ---------------- Import cutlist ----------------
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

    def _header_items(self, profile: str) -> List[QTableWidgetItem]:
        font = QFont(); font.setBold(True)
        bg = QBrush(QColor("#ecf0f1"))
        items: List[QTableWidgetItem] = []
        itp = QTableWidgetItem(profile or "—")
        itp.setFont(font); itp.setBackground(bg); itp.setForeground(QBrush(Qt.black))
        itp.setFlags(Qt.ItemIsEnabled)
        items.append(itp)
        for _ in range(6):
            it = QTableWidgetItem("")
            it.setFont(font); it.setBackground(bg); it.setFlags(Qt.ItemIsEnabled)
            items.append(it)
        return items

    def _load_cutlist(self, cuts: List[Dict[str, Any]]):
        self.tbl_cut.setRowCount(0)
        groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        order: List[str] = []
        for c in cuts:
            p = str(c.get("profile", "")).strip()
            if p not in groups:
                order.append(p)
            groups[p].append(c)
        for prof in order:
            # header
            r = self.tbl_cut.rowCount(); self.tbl_cut.insertRow(r)
            for col, it in enumerate(self._header_items(prof)):
                self.tbl_cut.setItem(r, col, it)
            # items
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
                for it in row:
                    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                for col, it in enumerate(row):
                    self.tbl_cut.setItem(r, col, it)
        self._mode = "idle"; self._active_row = None; self._manual_job = None
        self._finished_rows.clear()

    # ---------------- Ottimizza ----------------
    def _on_optimize_clicked(self):
        prof = None
        r = self.tbl_cut.currentRow()
        if r is not None and r >= 0 and self._row_is_header(r):
            it = self.tbl_cut.item(r, 0)
            prof = it.text().strip() if it else None
        if not prof:
            prof = self._find_first_header_profile()
        if not prof:
            QMessageBox.information(self, "Ottimizza", "Seleziona un profilo (doppio click su intestazione) o importa una lista.")
            return
        self._optimize_profile(prof)
        self._open_opt_dialog(prof)

    def _on_cell_double_clicked(self, row: int, col: int):
        if self._row_is_header(row):
            profile = self.tbl_cut.item(row, 0).text().strip()
            if profile:
                self._optimize_profile(profile)
                self._open_opt_dialog(profile)

    def _open_opt_config(self):
        dlg = OptimizationConfigDialog(self)
        dlg.exec()
        self._toast("Config ottimizzazione aggiornata.", "ok")

    def _open_opt_dialog(self, profile: str):
        prof = (profile or "").strip()
        if not prof:
            return
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
        if not rows:
            return
        if self._opt_dialog and self._opt_dialog.profile == prof:
            try:
                self._opt_dialog.raise_(); self._opt_dialog.activateWindow()
            except Exception:
                pass
            return

        # Passa il frame della viewer come overlay_target per sovrapporre esattamente
        self._opt_dialog = OptimizationRunDialog(self, prof, rows, overlay_target=self.viewer_frame)
        try:
            self._opt_dialog.simulationRequested.connect(self.simulate_cut_from_dialog)   # F7
        except Exception:
            pass
        try:
            self._opt_dialog.startRequested.connect(self._handle_start_trigger)           # F9
        except Exception:
            pass
        self._opt_dialog.finished.connect(lambda _p: setattr(self, "_opt_dialog", None))
        self._opt_dialog.show()
        self._toast("Ottimizzazione aperta in overlay: F9 = Avanza, F7 = Taglio (grafica adattata al frame).", "info")

    # ---------------- Start riga ----------------
    def _start_row(self):
        r = self.tbl_cut.currentRow()
        if r < 0:
            QMessageBox.information(self, "Start", "Seleziona una riga."); return
        if self._row_is_header(r):
            QMessageBox.information(self, "Start", "Seleziona un elemento (non l’intestazione profilo)."); return
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

    # ---------------- Ottimizza profilo → piano ----------------
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
                if q > 0:
                    items[(L, ax, ad)] += q
        if not items:
            QMessageBox.information(self, "Ottimizza", f"Nessun pezzo per '{prof}'."); return

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

        # Ordine barre: lascia per ultima quella con residuo massimo
        if rem:
            max_idx = max(range(len(rem)), key=lambda i: rem[i])
            if 0 <= max_idx < len(bars) and max_idx != len(bars) - 1:
                last_bar = bars.pop(max_idx); bars.append(last_bar)
                last_res = rem.pop(max_idx); rem.append(last_res)

        self._plan_profile = prof; self._bars = bars; self._bar_idx = 0; self._piece_idx = -1
        self._mode = "plan"

        # Piano informativo (ILP/BFD opzionale)
        try:
            agg_len: Dict[float, int] = defaultdict(int)
            for p in pieces: agg_len[round(p["len"], 2)] += 1
            jobs = [{"id": f"{prof} {L:.2f}", "len": float(L), "qty": int(q)} for L, q in sorted(agg_len.items(), key=lambda t: t[0], reverse=True)]
            solver = str(cfg.get("opt_solver", "ILP")).upper()
            self.plan = plan_ilp(jobs, stock=stock, time_limit_s=int(cfg.get("opt_time_limit_s", 15))) if solver == "ILP" else plan_bfd(jobs, stock=stock)
        except Exception:
            self.plan = {"solver":"BFD","steps":[]}

        self._toast(f"Ottimizzazione pronta per {prof}. Premi Start o Space.", "info")

    # ---------------- Movimento / Encoder / Freno ----------------
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

    def _is_dummy(self) -> bool:
        """Heuristics: ambiente test/senza IO reali."""
        try:
            n = type(self.machine).__name__.lower()
            if "dummy" in n or "mock" in n:
                return True
        except Exception:
            pass
        return (not hasattr(self.machine, "encoder_position")) and (not hasattr(self.machine, "positioning_active"))

    def _ensure_test_lock(self, tgt: int, remaining: int):
        """In dummy, forza lock freno per permettere simulazioni (F7/Space)."""
        if self._is_dummy() and (tgt > 0) and (remaining > 0) and not self._brake_locked:
            self._lock_brake()
            self._lock_on_inpos = False

    def _try_lock_on_inpos(self):
        if not self._lock_on_inpos: return
        if self._is_dummy():
            self._lock_brake()
            self._lock_on_inpos = False
            return

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

    # ---------------- Start fisico / avanzamento piano ----------------
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

    def _handle_start_trigger(self):
        # in piano: arma un pezzo (target=1) e posiziona; se già armato, attende taglio
        if self._mode != "plan" or not self._bars:
            return
        tgt = int(getattr(self.machine, "semi_auto_target_pieces", 0) or 0)
        done = int(getattr(self.machine, "semi_auto_count_done", 0) or 0)
        if self._brake_locked and tgt > 0 and done < tgt:
            return
        if self._bar_idx < 0: self._bar_idx = 0
        if self._bar_idx >= len(self._bars):
            self._toast("Piano completato", "ok"); return
        bar = self._bars[self._bar_idx]
        self._piece_idx += 1
        if self._piece_idx >= len(bar):
            self._bar_idx += 1; self._piece_idx = 0
            if self._bar_idx >= len(self._bars):
                self._toast("Piano completato", "ok"); return
            bar = self._bars[self._bar_idx]
        p = bar[self._piece_idx]
        try:
            setattr(self.machine, "semi_auto_target_pieces", 1)
            setattr(self.machine, "semi_auto_count_done", 0)
        except Exception: pass
        self._move_and_arm(p["len"], p["ax"], p["ad"], self._plan_profile, f"BAR {self._bar_idx+1} #{self._piece_idx+1}")

    # --------- Simulazioni taglio / pulse lama ---------
    def simulate_cut_from_dialog(self):
        self._simulate_cut_once()

    def _simulate_cut_once(self):
        tgt = int(getattr(self.machine, "semi_auto_target_pieces", 0) or 0)
        done = int(getattr(self.machine, "semi_auto_count_done", 0) or 0)
        remaining = max(tgt - done, 0)

        # in dummy, forza lock per permettere la simulazione
        self._ensure_test_lock(tgt, remaining)

        if not (self._brake_locked and tgt > 0 and remaining > 0):
            return

        new_done = done + 1
        try: setattr(self.machine, "semi_auto_count_done", new_done)
        except Exception: pass

        # Pezzo attuale
        cur_piece = None
        if self._mode == "plan" and self._bars and 0 <= self._bar_idx < len(self._bars) and 0 <= self._piece_idx < len(self._bars[self._bar_idx]):
            cur_piece = self._bars[self._bar_idx][self._piece_idx]

        # Decremento robusto sulla tabella principale
        if cur_piece:
            if not self._dec_row_qty_match(self._plan_profile, float(cur_piece["len"]), float(cur_piece["ax"]), float(cur_piece["ad"])):
                try:
                    self._dec_row_qty_match_str(self._plan_profile, f"{float(cur_piece['len']):.2f}",
                                                f"{float(cur_piece['ax']):.1f}", f"{float(cur_piece['ad']):.1f}")
                except Exception:
                    pass

        # Aggiorna dialog (best-effort: evidenzia pezzo tagliato e decrementa qty)
        if self._opt_dialog and cur_piece:
            try:
                self._opt_dialog.update_after_cut(length_mm=float(cur_piece["len"]), ang_sx=float(cur_piece["ax"]), ang_dx=float(cur_piece["ad"]))
            except Exception:
                pass

        if new_done >= tgt:
            # Fine pezzo: decide prossimo
            next_piece = self._peek_next_piece() if self._mode == "plan" else None
            same_next = bool(cur_piece and next_piece and self._same_job(cur_piece, next_piece))

            # azzera contatori
            try:
                setattr(self.machine, "semi_auto_target_pieces", 0)
                setattr(self.machine, "semi_auto_count_done", 0)
            except Exception:
                pass

            if self._mode == "manual" and self._active_row is not None:
                # riflette remaining=0 sulla riga attiva
                self.tbl_cut.setItem(self._active_row, 5, QTableWidgetItem("0"))
                self._mark_row_finished(self._active_row)
                self._mode = "idle"

            if self._mode == "plan" and self._auto_continue_enabled() and same_next:
                if self._brake_locked:
                    if self._advance_to_next_indices():
                        self._arm_next_piece_without_move()
                    else:
                        self._toast("Piano completato", "ok")
                else:
                    self._handle_start_trigger()
            else:
                self._unlock_brake()

        self._update_counters_ui()

    # ---------------- Auto-continue helpers ----------------
    def _auto_continue_enabled(self) -> bool:
        return True  # sempre attivo

    def _peek_next_piece(self) -> Optional[Dict[str, float]]:
        if not self._bars or self._bar_idx >= len(self._bars):
            return None
        next_bar_idx = self._bar_idx if self._bar_idx >= 0 else 0
        if not (0 <= next_bar_idx < len(self._bars)):
            return None
        bar = self._bars[next_bar_idx]
        next_piece_idx = self._piece_idx + 1
        if next_piece_idx >= len(bar):
            next_bar_idx += 1
            if next_bar_idx >= len(self._bars):
                return None
            bar = self._bars[next_bar_idx]
            next_piece_idx = 0
        if 0 <= next_piece_idx < len(bar):
            return bar[next_piece_idx]
        return None

    def _advance_to_next_indices(self) -> bool:
        if not self._bars:
            return False
        bar = self._bars[self._bar_idx] if (0 <= self._bar_idx < len(self._bars)) else []
        if not bar:
            return False
        if self._piece_idx + 1 < len(bar):
            self._piece_idx += 1
            return True
        if self._bar_idx + 1 >= len(self._bars):
            return False
        self._bar_idx += 1
        self._piece_idx = 0
        return True

    def _arm_next_piece_without_move(self):
        try:
            setattr(self.machine, "semi_auto_target_pieces", 1)
            setattr(self.machine, "semi_auto_count_done", 0)
        except Exception:
            pass
        self._lock_on_inpos = False
        self._update_counters_ui()

    def _same_job(self, p1: Dict[str, float], p2: Dict[str, float]) -> bool:
        try:
            dl = abs(float(p1["len"]) - float(p2["len"])) <= self._same_len_tol
            dax = abs(float(p1["ax"]) - float(p2["ax"])) <= self._same_ang_tol
            dad = abs(float(p1["ad"]) - float(p2["ad"])) <= self._same_ang_tol
            return dl and dax and dad
        except Exception:
            return False

    # ---------------- UI helpers ----------------
    def _toast(self, msg: str, level: str = "info"):
        if hasattr(self.appwin, "toast"):
            try:
                self.appwin.toast.show(msg, level, 2500)
            except Exception:
                pass

    def _mark_row_finished(self, row: int):
        self._finished_rows.add(row)
        for c in range(self.tbl_cut.columnCount()):
            it = self.tbl_cut.item(row, c)
            if it:
                it.setBackground(QBrush(QColor("#2ecc71")))
                it.setForeground(QBrush(Qt.black))
        self.tbl_cut.selectRow(row)

    def _dec_row_qty_match(self, profile: str, length: float, ax: float, ad: float) -> bool:
        """
        Decrementa la prima riga che corrisponde (prof, lunghezza≈, angoli≈).
        Ritorna True se ha aggiornato, False se non ha trovato match.
        """
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
                if new_q == 0:
                    self._mark_row_finished(r)
                return True
        return False

    def _dec_row_qty_match_str(self, profile: str, Ls: str, Axs: str, Ads: str) -> bool:
        """
        Decremento di fallback: confronta le stringhe già formattate nelle celle.
        """
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
                if new_q == 0:
                    self._mark_row_finished(r)
                return True
        return False

    def _update_counters_ui(self):
        done = int(getattr(self.machine, "semi_auto_count_done", 0) or 0)
        target = int(getattr(self.machine, "semi_auto_target_pieces", 0) or 0)
        remaining = max(target - done, 0)
        if self.lbl_target: self.lbl_target.setText(str(target))
        if self.lbl_done: self.lbl_done.setText(str(done))
        if self.lbl_remaining: self.lbl_remaining.setText(str(remaining))
        if self._mode == "manual" and self._active_row is not None and 0 <= self._active_row < self.tbl_cut.rowCount():
            if not self._row_is_header(self._active_row):
                self.tbl_cut.setItem(self._active_row, 5, QTableWidgetItem(str(remaining)))
                if remaining == 0:
                    self._mark_row_finished(self._active_row)

    # ---------------- Eventi / Poll ----------------
    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_F7:
            self._simulate_cut_once()
            event.accept(); return
        if event.key() == Qt.Key_Space:
            if self._mode == "plan":
                self._handle_start_trigger()
                event.accept(); return
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

        # Start fisico (sempre abilitato): fronte di salita
        if self._start_phys_enabled:
            cur = self._read_start_button()
            if cur and not self._start_prev:
                self._handle_start_trigger()
            self._start_prev = cur
        else:
            self._start_prev = False

        # Pulse lama reale
        cur_blade = self._read_blade_pulse()
        if cur_blade and not self._blade_prev:
            self._simulate_cut_once()
        self._blade_prev = cur_blade

        self._update_counters_ui()

    def hideEvent(self, ev):
        if self._poll is not None:
            try: self._poll.stop()
            except Exception: pass
            self._poll = None
        self._unlock_brake(silent=True)
        super().hideEvent(ev)

    # --- Sequencer logs (no-op) ---
    def _on_step_started(self, idx: int, step: dict): pass
    def _on_step_finished(self, idx: int, step: dict): pass
    def _on_seq_done(self): self._toast("Automatico: completato", "ok")
