from __future__ import annotations
from typing import List, Dict, Any
from collections import defaultdict

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QBrush, QKeyEvent
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QHBoxLayout, QAbstractItemView, QWidget, QSizePolicy
)

class OptimizationRunDialog(QDialog):
    """
    Finestra di riepilogo ottimizzazione per profilo:
    - Mostra le righe della cutlist del profilo selezionato (aggregate per length/angoli).
    - Evidenziazione forte; righe finite in verde acceso con testo a contrasto.
    - Indicatori di stato START: BLU=pronto a posizionarsi, ROSSO=in posizione (bloccato), VERDE=profilo finito.
    - Funzione di test per simulare la pressione del tasto fisico (pulsante e F9).
    - Non si chiude automaticamente: a fine profilo mostra luce verde e rimane in attesa di nuovo input.
    """
    finished = Signal(str)  # profile

    def __init__(self, parent: QWidget, profile: str, rows: List[Dict[str, Any]]):
        super().__init__(parent)
        self.setWindowTitle(f"Ottimizzazione - {profile}")
        self.setModal(False)
        self.resize(900, 560)
        self.profile = profile
        self._page = parent  # riferimento alla pagina Automatico

        # Aggrega per (len, ang_sx, ang_dx) sommando qty
        agg = defaultdict(int)
        for r in rows:
            k = (round(float(r["length_mm"]), 2), float(r["ang_sx"]), float(r["ang_dx"]))
            agg[k] += int(r["qty"])
        self._data = [(L, ax, ad, q) for (L, ax, ad), q in agg.items()]

        self._poll: QTimer | None = None

        self._build()
        self._fill()
        self._start_poll()

    def _build(self):
        root = QVBoxLayout(self)

        # Banner di stato/avviso
        self.banner = QLabel("START fisico attivo: premi il pulsante fisico oppure 'Simula START (Test)'.")
        self.banner.setStyleSheet("font-weight:700; color:#154360; background:#d6eaf8; padding:8px; border-radius:6px;")
        root.addWidget(self.banner)

        # Riga indicatori + bottone test
        top = QHBoxLayout()
        self.btn_state = QPushButton("PRONTO")
        self.btn_state.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.btn_state.setStyleSheet(self._style_led("blue"))
        self.btn_state.setEnabled(False)
        top.addWidget(QLabel(f"Profilo: {self.profile}"))
        top.addStretch(1)
        top.addWidget(self.btn_state)
        root.addLayout(top)

        # Tabella
        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels(["Profilo", "Elemento", "Lunghezza (mm)", "Ang SX", "Ang DX"])
        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setStyleSheet("""
            QTableWidget::item:selected { background:#1976d2; color:#ffffff; font-weight:700; }
        """)
        root.addWidget(self.tbl, 1)

        # Barra comandi
        bar = QHBoxLayout()
        self.btn_start_sim = QPushButton("Simula START (Test)")
        self.btn_start_sim.setToolTip("Simula la pressione del tasto fisico START per posizionare e bloccare la testa (tasto F9).")
        self.btn_start_sim.clicked.connect(self._simulate_start_pressed)
        bar.addWidget(self.btn_start_sim)
        bar.addStretch(1)
        self.btn_close = QPushButton("Chiudi")
        self.btn_close.clicked.connect(self.close)
        bar.addWidget(self.btn_close)
        root.addLayout(bar)

    def _fill(self):
        self.tbl.setRowCount(0)
        # ordina per lunghezza decrescente
        self._data.sort(key=lambda x: x[0], reverse=True)
        for (L, ax, ad, q) in self._data:
            r = self.tbl.rowCount(); self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(self.profile))
            self.tbl.setItem(r, 1, QTableWidgetItem(f"— x{q}"))
            self.tbl.setItem(r, 2, QTableWidgetItem(f"{float(L):.2f}"))
            self.tbl.setItem(r, 3, QTableWidgetItem(f"{float(ax):.1f}"))
            self.tbl.setItem(r, 4, QTableWidgetItem(f"{float(ad):.1f}"))
            if q == 0:
                self._mark_finished_row(r)

    def _mark_finished_row(self, row: int):
        for c in range(self.tbl.columnCount()):
            it = self.tbl.item(row, c)
            if not it: continue
            it.setBackground(QBrush(QColor("#2ecc71")))  # verde più acceso
            it.setForeground(QBrush(Qt.black))           # testo a contrasto

    def update_after_cut(self, length_mm: float, ang_sx: float, ang_dx: float):
        """Scala qty per la riga che matcha e aggiorna UI; se tutte 0 → stato FINITO (non chiude)."""
        tgtL = round(float(length_mm), 2)
        ax = float(ang_sx); ad = float(ang_dx)
        # Trova riga
        for r in range(self.tbl.rowCount()):
            try:
                L = round(float(self.tbl.item(r, 2).text()), 2)
                a1 = float(self.tbl.item(r, 3).text())
                a2 = float(self.tbl.item(r, 4).text())
            except Exception:
                continue
            if abs(L - tgtL) <= 0.01 and abs(a1 - ax) <= 0.01 and abs(a2 - ad) <= 0.01:
                # parse qty in "— xQ"
                elem = self.tbl.item(r, 1).text()
                try:
                    q = int(elem.split("x")[-1].strip())
                except Exception:
                    q = 1
                q = max(0, q - 1)
                self.tbl.setItem(r, 1, QTableWidgetItem(f"— x{q}"))
                if q == 0:
                    self._mark_finished_row(r)
                break
        # verifica chiusura logica (tutte 0 → VERDE)
        if self._all_zero():
            self.finished.emit(self.profile)
            # mostreremo luce verde e attesa nuovo input; non chiudiamo

    # ---------- Stato/LED ----------
    def _start_poll(self):
        if self._poll is None:
            self._poll = QTimer(self)
            self._poll.timeout.connect(self._update_state)
            self._poll.start(120)

    def _stop_poll(self):
        if self._poll:
            try: self._poll.stop()
            except Exception: pass
            self._poll = None

    def _update_state(self):
        try:
            brake = bool(getattr(self._page, "_brake_locked", False))
        except Exception:
            brake = False

        if self._all_zero():
            # Profilo finito
            self._set_led("green", "FINITO")
            self.banner.setText("Ottimizzazione completata per questo profilo. Attesa nuovo input/sequenza.")
            # assicura sblocco
            try: self._page._unlock_brake(silent=True)
            except Exception: pass
            # disabilita test START
            self.btn_start_sim.setEnabled(False)
            return

        # Non finito: controlla stato freno/posizione
        if brake:
            # in posizione (bloccato) → ROSSO
            self._set_led("red", "IN POSIZIONE")
            self.banner.setText("In posizione. Effettua i tagli necessari (F7 per simulare il taglio nella schermata principale).")
            # test START disabilitato mentre bloccato (attendi tagli)
            self.btn_start_sim.setEnabled(False)
        else:
            # pronto a posizionarsi → BLU
            self._set_led("blue", "PRONTO")
            self.banner.setText("START fisico attivo: premi il pulsante fisico oppure 'Simula START (Test)'.")
            self.btn_start_sim.setEnabled(True)

    def _all_zero(self) -> bool:
        for r in range(self.tbl.rowCount()):
            elem = self.tbl.item(r, 1).text()
            try:
                q = int(elem.split("x")[-1].strip())
            except Exception:
                q = 0
            if q > 0:
                return False
        return True

    def _set_led(self, color: str, text: str):
        self.btn_state.setText(text)
        self.btn_state.setStyleSheet(self._style_led(color))

    def _style_led(self, color: str) -> str:
        # Colori: blue, red, green
        bg = {"blue": "#2980b9", "red": "#e74c3c", "green": "#2ecc71"}.get(color, "#7f8c8d")
        fg = "#ffffff"  # su sfondi saturi, testo bianco offre buon contrasto
        return f"background:{bg}; color:{fg}; font-weight:800; padding:8px 12px; border:none; border-radius:8px;"

    # ---------- Test START ----------
    def _simulate_start_pressed(self):
        # Simula la pressione del tasto fisico START
        try:
            # abilita start fisico nella pagina (se non già)
            if getattr(self._page, "chk_start_phys", None):
                try: self._page.chk_start_phys.setChecked(True)
                except Exception: pass
            self._page._handle_start_trigger()
        except Exception:
            pass

    # ---------- Eventi ----------
    def keyPressEvent(self, ev: QKeyEvent):
        # F9: Simula START (tasto fisico)
        if ev.key() == Qt.Key_F9:
            self._simulate_start_pressed()
            ev.accept(); return
        super().keyPressEvent(ev)

    def closeEvent(self, ev):
        self._stop_poll()
        super().closeEvent(ev)
