from __future__ import annotations
from typing import Optional, Dict, Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QDoubleSpinBox, QComboBox,
    QSpinBox, QPushButton, QCheckBox
)
from PySide6.QtCore import Qt

try:
    from ui_qt.utils.settings import read_settings, write_settings
except Exception:
    def read_settings() -> Dict[str, Any]: return {}
    def write_settings(d: Dict[str, Any]) -> None: pass


class OptimizationSettingsDialog(QDialog):
    """
    Impostazioni ottimizzazione:
    - Stock barra (mm)
    - Kerf lama (mm)
    - Solver (ILP/BFD)
    - Time limit (s) per ILP
    - Log ottimizzazione abilitato
    """
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Impostazioni ottimizzazione")
        self.setModal(True)
        self.resize(420, 240)
        self._build()
        self._load()

        self.result_settings: Optional[Dict[str, Any]] = None

    def _build(self):
        root = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("Stock (mm):"))
        self.sp_stock = QDoubleSpinBox()
        self.sp_stock.setRange(100.0, 20000.0)
        self.sp_stock.setDecimals(1)
        self.sp_stock.setValue(6500.0)
        row.addWidget(self.sp_stock, 1)
        root.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Kerf (mm):"))
        self.sp_kerf = QDoubleSpinBox()
        self.sp_kerf.setRange(0.0, 10.0)
        self.sp_kerf.setDecimals(2)
        self.sp_kerf.setValue(3.00)
        row2.addWidget(self.sp_kerf, 1)
        root.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Solver:"))
        self.cb_solver = QComboBox()
        self.cb_solver.addItems(["ILP", "BFD"])
        row3.addWidget(self.cb_solver, 1)
        root.addLayout(row3)

        row4 = QHBoxLayout()
        row4.addWidget(QLabel("Time limit (s):"))
        self.sp_tl = QSpinBox()
        self.sp_tl.setRange(1, 600)
        self.sp_tl.setValue(15)
        row4.addWidget(self.sp_tl, 1)
        root.addLayout(row4)

        self.chk_log = QCheckBox("Abilita registro ottimizzazione")
        self.chk_log.setChecked(False)
        root.addWidget(self.chk_log)

        btns = QHBoxLayout()
        btn_cancel = QPushButton("Annulla"); btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("OK"); btn_ok.clicked.connect(self._ok)
        btns.addStretch(1); btns.addWidget(btn_cancel); btns.addWidget(btn_ok)
        root.addLayout(btns)

    def _load(self):
        cfg = read_settings()
        stock = float(cfg.get("opt_stock_mm", 6500.0))
        kerf = float(cfg.get("opt_kerf_mm", 3.0))
        solver = str(cfg.get("opt_solver", "ILP")).upper()
        tl = int(cfg.get("opt_time_limit_s", 15))
        enable_log = bool(cfg.get("opt_log_enabled", False))
        self.sp_stock.setValue(stock)
        self.sp_kerf.setValue(kerf)
        if solver not in ("ILP", "BFD"): solver = "ILP"
        self.cb_solver.setCurrentText(solver)
        self.sp_tl.setValue(tl)
        self.chk_log.setChecked(enable_log)

    def _ok(self):
        self.result_settings = {
            "opt_stock_mm": float(self.sp_stock.value()),
            "opt_kerf_mm": float(self.sp_kerf.value()),
            "opt_solver": str(self.cb_solver.currentText()),
            "opt_time_limit_s": int(self.sp_tl.value()),
            "opt_log_enabled": bool(self.chk_log.isChecked()),
        }
        try:
            cfg = read_settings()
            cfg.update(self.result_settings)
            write_settings(cfg)
        except Exception:
            pass
        self.accept()
