"""
Utility — Encoder & Ingressi: categorie / sottocategorie, Waveshare 8+8 canali.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import contextlib
import logging
import math

from PySide6.QtCore import Qt, QTimer, QUrl, QObject, QEvent
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFormLayout,
    QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QScrollArea, QWidget,
    QGroupBox, QMessageBox, QGridLayout, QTextBrowser, QTabWidget,
    QAbstractSpinBox, QSizePolicy, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView,
)

from ui_qt.utils.hardware_config_store import (
    load_hardware_config,
    merge_and_save,
    default_digital_inputs,
    hardware_config_path,
    project_root,
)
from ui_qt.logic.carriage_calibration import compute_two_point_correction

logger = logging.getLogger("utility_encoders")


class _NoWheelFilter(QObject):
    """Blocca la rotella del mouse su spin/combo (evita modifiche accidentali)."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            return True
        return super().eventFilter(obj, event)


# Segnale logico → etichetta UI
SIGNAL_LABELS: Dict[str, str] = {
    "fc_min": "FC_MIN (homing carro, induttivo)",
    "fc_max": "FC_MAX (limite max)",
    "emergency_ok": "EMERG OK (1=OK)",
    "head_sx_zero": "FC testa SX 0° (induttivo)",
    "head_dx_zero": "FC testa DX 0° (induttivo)",
    "piece_count_sx": "Micro SX (conteggio + rientro + fine taglio)",
    "piece_count_dx": "Micro DX (conteggio + rientro + fine taglio)",
    "blade_pulse": "Impulso dedicato (opz., se non usi i micro)",
    "start_pressed": "start_pressed (START)",
    "dx_blade_out": "dx_blade_out (uscita lama DX)",
}

SIGNAL_KEYS = list(SIGNAL_LABELS.keys())
RISERVA = "— riserva —"

# Uscite fisse (solo documentazione UI)
MODULE_OUTPUTS = {
    1: [
        "OUT1 Testa SX 45°",
        "OUT2 Testa SX 0°",
        "OUT3 Testa DX 45°",
        "OUT4 Testa DX 0°",
        "OUT5 Inibizione lama SX (EV)",
        "OUT6 Inibizione lama DX (EV)",
        "OUT7 Inibizione MOTORI lama (service, senza EMG)",
        "OUT8 riserva",
    ],
    2: [
        "OUT1 Morsa SX CHIUDI",
        "OUT2 Morsa SX APRI",
        "OUT3 Morsa DX CHIUDI",
        "OUT4 Morsa DX APRI",
        "OUT5 Freno BLOCCO",
        "OUT6 Freno SBLOCCO",
        "OUT7 Frizione",
        "OUT8 riserva",
    ],
}

MODULE_LETTER = {1: "A", 2: "B"}


class EncodersInputsTab(QFrame):
    """
    Configurazione organizzata per categorie:
      Encoder → Carro / Teste
      Sensori FC → Homing / Limite max / Zero teste
      Waveshare → Modulo #1 / Modulo #2 (tutti gli 8 IN)
      Monitor / Documentazione
    """

    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = getattr(appwin, "machine", None)
        # (module, index0) → {combo, active_high}
        self._ch_widgets: Dict[Tuple[int, int], Dict[str, Any]] = {}
        self._monitor_labels: Dict[str, QLabel] = {}
        self._poll: Optional[QTimer] = None
        self._waveshare_unlocked = False
        self._no_wheel = _NoWheelFilter(self)
        self._calib_capture: Dict[str, Optional[float]] = {
            "enc_near": None,
            "enc_far": None,
        }
        self._build()
        self._load()
        self._start_monitor()

    # ------------------------------------------------------------------ UI root
    def _build(self):
        self.setStyleSheet(
            "EncodersInputsTab { border: 1px solid #3b4b5a; border-radius: 6px; }"
            "QGroupBox { font-weight: 700; margin-top: 14px; padding-top: 12px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }"
            "QTabWidget::pane { border: 1px solid #3b4b5a; top: -1px; padding: 8px; }"
            "QHeaderView::section { background: #2c3e50; padding: 6px; border: none; }"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(10)

        title = QLabel("Configurazione macchina (I/O, encoder, sensori)")
        title.setStyleSheet("font-size: 15pt; font-weight: 700;")
        outer.addWidget(title)

        hint = QLabel(
            "Tutto in un unico menu: bus Modbus (Modulo A/B), encoder rotativi, "
            "sensori, calibrazione. File: data/hardware_config.json. "
            "Dopo cambio GPIO riavviare l'app."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #bdc3c7;")
        outer.addWidget(hint)

        cats = QTabWidget()
        cats.setDocumentMode(True)
        cats.addTab(self._cat_bus(), "0. Bus Modbus")
        cats.addTab(self._cat_encoders(), "1. Encoder")
        cats.addTab(self._cat_sensors(), "2. Sensori / FC")
        cats.addTab(self._cat_waveshare(), "3. Waveshare A/B")
        cats.addTab(self._cat_calibration(), "4. Calibrazione")
        cats.addTab(self._cat_monitor(), "5. Monitor")
        cats.addTab(self._cat_docs(), "6. Documentazione")
        outer.addWidget(cats, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_reload = QPushButton("Ricarica da file")
        btn_reload.clicked.connect(self._load)
        btn_row.addWidget(btn_reload)
        btn_save = QPushButton("Salva configurazione")
        btn_save.setStyleSheet(
            "QPushButton { background:#27ae60; color:white; font-weight:700; "
            "padding:10px 18px; border-radius:6px; border:none; }"
        )
        btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_save)
        outer.addLayout(btn_row)

    def _scroll(self, inner: QWidget) -> QScrollArea:
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setWidget(inner)
        return sc

    def _spin_int(self, lo: int, hi: int, val: int) -> QSpinBox:
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(val)
        s.setMinimumWidth(100)
        s.installEventFilter(self._no_wheel)
        return s

    def _spin_float(self, lo: float, hi: float, val: float, dec: int = 3) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(dec)
        s.setValue(val)
        s.setMinimumWidth(120)
        s.installEventFilter(self._no_wheel)
        return s

    def _section_title(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setStyleSheet(
            "font-size: 12pt; font-weight: 700; color: #5dade2; "
            "padding: 4px 0 8px 0; border-bottom: 1px solid #3b4b5a; margin-bottom: 6px;"
        )
        return lab

    def _tip(self, w: QWidget, text: str) -> QWidget:
        """Assegna tooltip e restituisce il widget (per chaining)."""
        w.setToolTip(text)
        return w

    # ============================================================== 0. Bus
    def _cat_bus(self) -> QWidget:
        """Porta RS485 + indirizzi Modulo A/B (ex Configurazione)."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(12)
        lay.addWidget(self._section_title("Bus RS485 Modbus RTU — Waveshare Modulo A / Modulo B"))

        try:
            from ui_qt.services.rs485_manager import RS485Manager, list_serial_ports_safe
        except Exception:
            RS485Manager = None  # type: ignore

            def list_serial_ports_safe():
                return ["COM3", "/dev/ttyUSB0"]

        self._rs485 = RS485Manager() if RS485Manager else None

        g = QGroupBox("Collegamento")
        form = QFormLayout(g)
        form.setContentsMargins(12, 18, 12, 12)
        form.setSpacing(10)

        self.cmb_port = QComboBox()
        self.cmb_port.installEventFilter(self._no_wheel)
        for p in list_serial_ports_safe():
            self.cmb_port.addItem(p)
        btn_ref = QPushButton("Aggiorna porte")
        btn_ref.clicked.connect(self._refresh_ports)
        port_row = QWidget()
        ph = QHBoxLayout(port_row)
        ph.setContentsMargins(0, 0, 0, 0)
        ph.addWidget(self.cmb_port, 1)
        ph.addWidget(btn_ref)

        self.cmb_baud = QComboBox()
        self.cmb_baud.addItems([str(b) for b in (9600, 19200, 38400, 57600, 115200)])
        self.cmb_baud.setCurrentText("115200")
        self.cmb_baud.installEventFilter(self._no_wheel)
        self.cmb_par = QComboBox()
        self.cmb_par.addItems(["N", "E", "O"])
        self.cmb_par.installEventFilter(self._no_wheel)
        self.cmb_stop = QComboBox()
        self.cmb_stop.addItems(["1", "2"])
        self.cmb_stop.installEventFilter(self._no_wheel)
        self.spin_addr_a = self._spin_int(1, 247, 1)
        self.spin_addr_b = self._spin_int(1, 247, 2)
        self.chk_autoconnect = QCheckBox("Autoconnetti all'apertura Utility")
        self.chk_autoconnect.setChecked(True)

        self._tip(self.cmb_port, "Porta seriale USB-RS485 (es. /dev/ttyUSB0 o COMx).")
        self._tip(self.spin_addr_a, "Indirizzo Modbus del Modulo A (Waveshare ID=1, inclinazioni/lame/FC).")
        self._tip(self.spin_addr_b, "Indirizzo Modbus del Modulo B (Waveshare ID=2, morse/freno/conteggi).")

        form.addRow("Porta seriale:", port_row)
        form.addRow("Baud:", self.cmb_baud)
        form.addRow("Parità:", self.cmb_par)
        form.addRow("Stop bits:", self.cmb_stop)
        form.addRow("Modulo A (addr):", self.spin_addr_a)
        form.addRow("Modulo B (addr):", self.spin_addr_b)
        form.addRow("", self.chk_autoconnect)

        btns = QHBoxLayout()
        self.btn_rs_conn = QPushButton("Connetti")
        self.btn_rs_conn.clicked.connect(lambda: self._rs485_connect(False))
        self.btn_rs_disc = QPushButton("Disconnetti")
        self.btn_rs_disc.clicked.connect(self._rs485_disconnect)
        self.btn_rs_read = QPushButton("Leggi ingressi A/B")
        self.btn_rs_read.clicked.connect(self._rs485_read_once)
        self.btn_rs_save = QPushButton("Salva bus in settings")
        self.btn_rs_save.clicked.connect(self._rs485_save_settings)
        btns.addWidget(self.btn_rs_conn)
        btns.addWidget(self.btn_rs_disc)
        btns.addWidget(self.btn_rs_read)
        btns.addWidget(self.btn_rs_save)
        btns.addStretch(1)

        self.lbl_bus_io = QLabel("Ingressi: —")
        self.lbl_bus_io.setWordWrap(True)
        self.lbl_bus_io.setStyleSheet("font-family: Consolas, monospace;")

        note = QLabel(
            "Nomenclatura: Modulo A = Waveshare ID 1 · Modulo B = Waveshare ID 2. "
            "La mappa canale→segnale è nella scheda «3. Waveshare A/B»."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#95a5a6;")

        lay.addWidget(g)
        lay.addLayout(btns)
        lay.addWidget(self.lbl_bus_io)
        lay.addWidget(note)
        lay.addStretch(1)
        self._rs485_load_settings()
        return self._scroll(w)

    def _refresh_ports(self):
        try:
            from ui_qt.services.rs485_manager import list_serial_ports_safe
        except Exception:
            def list_serial_ports_safe():
                return []
        cur = self.cmb_port.currentText()
        self.cmb_port.clear()
        for p in list_serial_ports_safe():
            self.cmb_port.addItem(p)
        if cur:
            if self.cmb_port.findText(cur) < 0:
                self.cmb_port.addItem(cur)
            self.cmb_port.setCurrentText(cur)

    def _rs485_cfg(self) -> Dict[str, Any]:
        return {
            "port": (self.cmb_port.currentText() or "").strip(),
            "baud": int(self.cmb_baud.currentText()),
            "par": (self.cmb_par.currentText() or "N")[:1],
            "stop": int(self.cmb_stop.currentText()),
            "addr_a": int(self.spin_addr_a.value()),
            "addr_b": int(self.spin_addr_b.value()),
            "autoconn": bool(self.chk_autoconnect.isChecked()),
        }

    def _rs485_save_settings(self):
        from ui_qt.utils.settings import read_settings, write_settings
        cfg = dict(read_settings())
        io = dict(cfg.get("io", {}) or {})
        c = self._rs485_cfg()
        io["rs485"] = {
            "port": c["port"],
            "baud": c["baud"],
            "parity": c["par"],
            "stopbits": c["stop"],
        }
        io["modA"] = {"addr": c["addr_a"]}
        io["modB"] = {"addr": c["addr_b"]}
        io["autoconnect"] = c["autoconn"]
        cfg["io"] = io
        write_settings(cfg)
        # Sync anche hardware_config modbus
        merge_and_save({
            "modbus": {
                "port": c["port"],
                "baudrate": c["baud"],
                "module1_addr": c["addr_a"],
                "module2_addr": c["addr_b"],
            }
        })
        self._show_toast("Impostazioni bus salvate")

    def _rs485_load_settings(self):
        from ui_qt.utils.settings import read_settings
        cfg = read_settings()
        io = cfg.get("io", {}) or {}
        rs = io.get("rs485", {}) or {}
        if rs.get("port"):
            if self.cmb_port.findText(rs["port"]) < 0:
                self.cmb_port.addItem(rs["port"])
            self.cmb_port.setCurrentText(rs["port"])
        if rs.get("baud"):
            self.cmb_baud.setCurrentText(str(rs["baud"]))
        if rs.get("parity"):
            self.cmb_par.setCurrentText(str(rs["parity"]).upper()[:1])
        if rs.get("stopbits"):
            self.cmb_stop.setCurrentText(str(int(rs["stopbits"])))
        self.spin_addr_a.setValue(int((io.get("modA") or {}).get("addr", 1)))
        self.spin_addr_b.setValue(int((io.get("modB") or {}).get("addr", 2)))
        self.chk_autoconnect.setChecked(bool(io.get("autoconnect", True)))
        if self.chk_autoconnect.isChecked():
            QTimer.singleShot(200, lambda: self._rs485_connect(True))

    def _rs485_connect(self, silent: bool = False):
        if not self._rs485:
            if not silent:
                self._show_toast("RS485 non disponibile")
            return
        c = self._rs485_cfg()
        ok = self._rs485.connect(
            port=c["port"], baudrate=c["baud"], parity=c["par"],
            stopbits=c["stop"], timeout=0.5,
        )
        if not silent:
            self._show_toast("Connesso RS485" if ok else "Connessione RS485 fallita")

    def _rs485_disconnect(self):
        if self._rs485:
            self._rs485.disconnect()
            self._show_toast("RS485 disconnesso")

    def _rs485_read_once(self):
        if not self._rs485 or not self._rs485.is_connected():
            self._show_toast("Non connesso RS485")
            return
        c = self._rs485_cfg()
        a = self._rs485.read_discrete_inputs(unit=c["addr_a"], address=0, count=8)
        b = self._rs485.read_discrete_inputs(unit=c["addr_b"], address=0, count=8)
        def fmt(mod, vals):
            bits = " ".join(
                f"IN{i+1}={'ON' if (i < len(vals) and vals[i]) else 'off'}"
                for i in range(8)
            )
            return f"{mod}: {bits}"
        self.lbl_bus_io.setText(fmt("A", a) + "\n" + fmt("B", b))

    # ============================================================== 1. Encoder
    def _cat_encoders(self) -> QWidget:
        tabs = QTabWidget()
        tabs.addTab(self._sub_encoder_carro(), "1.1 Carro (ELTRA)")
        tabs.addTab(self._sub_encoder_teste(), "1.2 Teste inclinazione")
        return tabs

    def _sub_encoder_carro(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(12)
        lay.addWidget(self._section_title("Encoder carro — AL-ZARD #1 → GPIO Pi"))

        g = QGroupBox("GPIO e calibrazione")
        form = QFormLayout(g)
        form.setSpacing(10)
        form.setContentsMargins(12, 18, 12, 12)

        self.spin_enc_a = self._spin_int(0, 27, 17)
        self.spin_enc_b = self._spin_int(0, 27, 27)
        self.spin_enc_z = self._spin_int(0, 27, 22)
        self.chk_enc_index = QCheckBox("Abilita impulso Z (index) per homing")
        self.chk_enc_index.setChecked(True)
        self.spin_enc_ppr = self._spin_int(100, 10000, 1000)
        self.cmb_enc_quad = QComboBox()
        self.cmb_enc_quad.addItems(["x1", "x2", "x4"])
        self.cmb_enc_quad.setCurrentText("x4")
        self.spin_pulley = self._spin_float(10.0, 200.0, 60.0, 1)
        self.spin_ppm = self._spin_float(0.001, 1000.0, 84.880, 3)
        self.chk_enc_invert = QCheckBox("Inverti verso conteggio")

        form.addRow("GPIO canale A:", self.spin_enc_a)
        form.addRow("GPIO canale B:", self.spin_enc_b)
        form.addRow("GPIO index Z:", self.spin_enc_z)
        form.addRow("", self.chk_enc_index)
        form.addRow("PPR encoder:", self.spin_enc_ppr)
        form.addRow("Quadratura:", self.cmb_enc_quad)
        form.addRow("Diametro puleggia (mm):", self.spin_pulley)
        form.addRow("Impulsi / mm:", self.spin_ppm)
        form.addRow("", self.chk_enc_invert)
        btn_calc = QPushButton("Ricalcola impulsi/mm da diametro e PPR")
        btn_calc.clicked.connect(self._recalc_pulses_per_mm)
        form.addRow("", btn_calc)

        self._tip(self.spin_enc_a, "GPIO BCM canale A encoder carro dopo AL-ZARD #1 (default 17).")
        self._tip(self.spin_enc_b, "GPIO BCM canale B encoder carro (default 27).")
        self._tip(self.spin_enc_z, "GPIO BCM impulso Z (index) per homing fine (default 22).")
        self._tip(self.spin_enc_ppr, "Impulsi per giro encoder ELTRA (tipico 1000 PPR).")
        self._tip(self.cmb_enc_quad, "Moltiplicatore quadratura: x4 = 4 conteggi per impulso.")
        self._tip(self.spin_pulley, "Diametro puleggia cinghia (mm). Usato per calcolare impulsi/mm.")
        self._tip(
            self.spin_ppm,
            "Impulsi per millimetro effettivi. Dopo calibrazione a 2 punti può differire dal nominale.",
        )

        note = QLabel(
            "Default GPIO 17/27/22. Non collegare NPN 12V direttamente al Pi: passare dall'AL-ZARD."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#95a5a6; padding-top:4px;")

        lay.addWidget(g)
        lay.addWidget(note)
        lay.addStretch(1)
        return self._scroll(w)

    def _recalc_pulses_per_mm(self):
        ppr = int(self.spin_enc_ppr.value())
        quad = {"x1": 1, "x2": 2, "x4": 4}.get(self.cmb_enc_quad.currentText(), 4)
        diam = float(self.spin_pulley.value())
        if diam <= 0:
            return
        self.spin_ppm.setValue((ppr * quad) / (math.pi * diam))

    def _sub_encoder_teste(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(12)
        lay.addWidget(
            self._section_title(
                "Encoder rotativi inclinazione teste — AL-ZARD #2 → GPIO (niente Arduino/MT6701)"
            )
        )

        g = QGroupBox("GPIO e taratura (encoder incrementali AB)")
        form = QFormLayout(g)
        form.setSpacing(10)
        form.setContentsMargins(12, 18, 12, 12)

        self.chk_head_enc_en = QCheckBox("Abilitati")
        self.chk_head_enc_en.setChecked(True)
        # Solo GPIO: Arduino Nano + MT6701 non più usati
        self.cmb_head_iface = QComboBox()
        self.cmb_head_iface.addItems(["gpio"])
        self.cmb_head_iface.setEnabled(False)
        self.spin_head_ppr = self._spin_int(100, 5000, 600)
        self.spin_head_quad = self._spin_int(1, 4, 4)
        self.spin_sx_a = self._spin_int(0, 27, 5)
        self.spin_sx_b = self._spin_int(0, 27, 6)
        self.spin_dx_a = self._spin_int(0, 27, 19)
        self.spin_dx_b = self._spin_int(0, 27, 26)
        self.spin_off_sx = self._spin_float(-45.0, 45.0, 0.0, 2)
        self.spin_off_dx = self._spin_float(-45.0, 45.0, 0.0, 2)
        self.chk_inv_sx = QCheckBox("Inverti SX")
        self.chk_inv_dx = QCheckBox("Inverti DX")
        # Placeholder nascosti per compatibilità load/save legacy
        self.spin_modbus_sx = self._spin_int(1, 247, 20)
        self.spin_modbus_dx = self._spin_int(1, 247, 21)
        self.spin_modbus_sx.hide()
        self.spin_modbus_dx.hide()

        self._tip(self.spin_head_ppr, "Impulsi per giro dell'encoder rotativo testa (tipico 600 P/R).")
        self._tip(self.spin_sx_a, "GPIO BCM canale A testa SX dopo AL-ZARD (default 5).")
        self._tip(self.spin_off_sx, "Offset meccanico zero SX in gradi, dopo azzeramento su FC 0°.")

        form.addRow("", self.chk_head_enc_en)
        form.addRow("Interfaccia:", QLabel("GPIO + AL-ZARD (encoder rotativi)"))
        form.addRow("PPR:", self.spin_head_ppr)
        form.addRow("Quadratura:", self.spin_head_quad)
        form.addRow("GPIO SX A / B:", self._pair(self.spin_sx_a, self.spin_sx_b))
        form.addRow("GPIO DX A / B:", self._pair(self.spin_dx_a, self.spin_dx_b))
        form.addRow("Offset zero SX / DX (°):", self._pair(self.spin_off_sx, self.spin_off_dx))
        form.addRow("", self._pair(self.chk_inv_sx, self.chk_inv_dx))

        note = QLabel(
            "Percorso ufficiale: encoder rotativo NPN 12 V → AL-ZARD → GPIO 5/6 (SX) e 19/26 (DX). "
            "Arduino Nano + encoder magnetici MT6701 non sono più necessari né configurabili."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#95a5a6;")

        lay.addWidget(g)
        lay.addWidget(note)
        lay.addStretch(1)
        return self._scroll(w)

    def _pair(self, a: QWidget, b: QWidget) -> QWidget:
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(a)
        h.addWidget(b)
        h.addStretch(1)
        return box

    # ========================================================= 2. Sensori / FC
    def _cat_sensors(self) -> QWidget:
        tabs = QTabWidget()
        tabs.addTab(self._sub_fc_homing(), "2.1 Homing carro (FC_MIN)")
        tabs.addTab(self._sub_fc_max(), "2.2 Limite max (FC_MAX)")
        tabs.addTab(self._sub_fc_heads(), "2.3 Zero teste 0°")
        tabs.addTab(self._sub_cut_cycle(), "2.4 Micro taglio / conteggio")
        return tabs

    def _sub_fc_homing(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(12)
        lay.addWidget(self._section_title("Sensore induttivo homing carro — FC_MIN (parametri zero)"))

        info = QLabel(
            "Induttivo M12 NPN NO 24 V sul minimo carro. "
            "Questi parametri affinano lo zero software dopo il trigger FC "
            "(come sulla vecchia logica CNC: approccio, creep, offset, debounce)."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#bdc3c7;")

        g = QGroupBox("Parametri calibrabili")
        form = QFormLayout(g)
        form.setContentsMargins(12, 18, 12, 12)
        form.setSpacing(10)

        self.chk_homing_en = QCheckBox("Usa FC_MIN in homing carro")
        self.chk_homing_en.setChecked(True)
        self.spin_approach = self._spin_float(10.0, 3000.0, 500.0, 1)
        self.spin_approach.setSuffix(" mm/s")
        self.spin_creep = self._spin_float(5.0, 500.0, 80.0, 1)
        self.spin_creep.setSuffix(" mm/s")
        self.spin_backoff = self._spin_float(0.0, 50.0, 5.0, 1)
        self.spin_backoff.setSuffix(" mm")
        self.spin_offset_fc = self._spin_float(0.0, 200.0, 30.0, 1)
        self.spin_offset_fc.setSuffix(" mm")
        self.spin_zero_off = self._spin_float(-50.0, 50.0, 0.0, 2)
        self.spin_zero_off.setSuffix(" mm")
        self.spin_fc_settle = self._spin_int(0, 2000, 200)
        self.spin_fc_settle.setSuffix(" ms")
        self.spin_fc_deb = self._spin_int(0, 500, 30)
        self.spin_fc_deb.setSuffix(" ms")
        self.chk_use_z = QCheckBox("Usa anche impulso Z encoder (se disponibile)")
        self.chk_use_z.setChecked(True)

        form.addRow("", self.chk_homing_en)
        form.addRow("Velocità approccio:", self.spin_approach)
        form.addRow("Velocità creep (dopo FC):", self.spin_creep)
        form.addRow("Backoff dopo FC:", self.spin_backoff)
        form.addRow("Offset dopo FC (quota zero):", self.spin_offset_fc)
        form.addRow("Ritocco zero (taratura fine):", self.spin_zero_off)
        form.addRow("Settle dopo FC:", self.spin_fc_settle)
        form.addRow("Debounce lettura:", self.spin_fc_deb)
        form.addRow("", self.chk_use_z)

        self._tip(self.spin_approach, "Velocità di avvicinamento a FC_MIN (mm/s).")
        self._tip(self.spin_creep, "Velocità lenta dopo il primo contatto FC, prima dello zero.")
        self._tip(self.spin_backoff, "Arretramento dopo FC prima del creep (mm).")
        self._tip(
            self.spin_offset_fc,
            "Distanza oltre FC che diventa lo zero software (≈ min_position).",
        )
        self._tip(self.spin_zero_off, "Ritocco fine ±mm dopo la procedura (taratura sul campo).")
        self._tip(self.spin_fc_deb, "Anti-rimbalzo lettura induttivo FC_MIN (ms).")

        tip = QLabel(
            "Quota software di zero ≈ min_position = offset_after_fc + zero_offset. "
            "Canale fisico: Waveshare (default Modulo #1 IN1). "
            "Non confondere con i FC 0° delle teste."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#95a5a6;")

        lay.addWidget(info)
        lay.addWidget(g)
        lay.addWidget(tip)
        lay.addStretch(1)
        return self._scroll(w)

    def _sub_cut_cycle(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(12)
        lay.addWidget(self._section_title("Micro sulle teste = conteggio + rientro + fine ciclo"))

        info = QLabel(
            "I microswitch SX/DX che contano i pezzi sono gli stessi che indicano "
            "testa rientrata e fine ciclo di taglio. "
            "L'uscita lama è abilitata solo se la lama è ON (interlock elettrico in quadro: "
            "contatti ausiliari / relè — da verificare sul schema). "
            "In software, Automatico/Semi attendono questi micro come blade_pulse/cut_done."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#bdc3c7;")

        g = QGroupBox("Logica software")
        form = QFormLayout(g)
        form.setContentsMargins(12, 18, 12, 12)
        form.setSpacing(10)

        self.chk_pc_is_cut = QCheckBox("I micro conteggio sono anche fine-ciclo / rientro")
        self.chk_pc_is_cut.setChecked(True)
        self.cmb_blade_src = QComboBox()
        self.cmb_blade_src.addItem("Dai micro SX/DX (consigliato)", "piece_count")
        self.cmb_blade_src.addItem("Ingresso dedicato blade_pulse", "dedicated")
        self.cmb_blade_src.installEventFilter(self._no_wheel)
        self.spin_cut_deb = self._spin_int(0, 500, 40)
        self.spin_cut_deb.setSuffix(" ms")
        self.chk_count_active = QCheckBox("Conta solo sulle teste non inibite (lama attiva lato)")
        self.chk_count_active.setChecked(True)
        self.chk_blade_hw = QCheckBox("Uscita lama richiede lama ON (interlock HW quadro)")
        self.chk_blade_hw.setChecked(True)

        form.addRow("", self.chk_pc_is_cut)
        form.addRow("Sorgente blade_pulse / cut_done:", self.cmb_blade_src)
        form.addRow("Debounce micro:", self.spin_cut_deb)
        form.addRow("", self.chk_count_active)
        form.addRow("", self.chk_blade_hw)

        self._tip(
            self.cmb_blade_src,
            "Consigliato: usare i micro SX/DX come blade_pulse/cut_done. "
            "«Ingresso dedicato» solo se hai un canale Waveshare separato.",
        )
        self._tip(self.spin_cut_deb, "Anti-rimbalzo sui micro di conteggio/fine ciclo (ms).")
        self._tip(
            self.chk_blade_hw,
            "Ricorda l'interlock elettrico in quadro: uscita lama solo con motore lama ON.",
        )

        tip = QLabel(
            "Modalità speciali: dopo ogni step di taglio attendere cut_done dai micro "
            "della testa usata; l'inibizione lama (OUT5/OUT6) resta comando SW. "
            "Se in quadro mancano i contatti ausiliari lama→uscita, documentarli nello schema."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#95a5a6;")

        lay.addWidget(info)
        lay.addWidget(g)
        lay.addWidget(tip)
        lay.addStretch(1)
        return self._scroll(w)

    def _sub_fc_max(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(12)
        lay.addWidget(self._section_title("Finecorsa massimo carro — FC_MAX"))

        g = QGroupBox("Riferimento cablaggio")
        form = QFormLayout(g)
        form.setContentsMargins(12, 18, 12, 12)
        form.addRow("Tipo:", QLabel("Microswitch NA (tipico)"))
        form.addRow("Segnale logico:", QLabel("fc_max"))
        form.addRow("Default I/O:", QLabel("Modulo #1 · IN2"))
        form.addRow("Uso:", QLabel("Limite soft/hard corsa max"))

        lay.addWidget(g)
        lay.addStretch(1)
        return self._scroll(w)

    def _sub_fc_heads(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(12)
        lay.addWidget(self._section_title("Finecorsa induttivi 0° teste SX / DX"))

        info = QLabel(
            "Due induttivi M12 NPN NO (uno per testa) sul blocco meccanico 0°. "
            "Non sono gli unici induttivi: c'è anche FC_MIN homing carro (sottocategoria 2.1)."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#bdc3c7;")

        g = QGroupBox("Parametri homing / settle (software)")
        form = QFormLayout(g)
        form.setSpacing(10)
        form.setContentsMargins(12, 18, 12, 12)

        self.chk_fc_en = QCheckBox("Abilitati in homing")
        self.chk_fc_en.setChecked(True)
        self.spin_settle = self._spin_int(50, 5000, 400)
        self.spin_settle.setSuffix(" ms")
        self.spin_stable = self._spin_float(0.05, 5.0, 0.2, 2)
        self.spin_fc_timeout = self._spin_float(1.0, 60.0, 8.0, 1)
        self.chk_auto_zero = QCheckBox("auto_zero (solo test: azzera encoder al FC)")
        self.chk_heads_req = QCheckBox("heads_required in homing")
        self.chk_fc_active_high = QCheckBox("Attivo alto (NPN NO tipico)")
        self.chk_fc_active_high.setChecked(True)

        form.addRow("", self.chk_fc_en)
        form.addRow("Settle stabilizzazione:", self.spin_settle)
        form.addRow("Angolo stabile entro (°):", self.spin_stable)
        form.addRow("Timeout homing (s):", self.spin_fc_timeout)
        form.addRow("", self.chk_fc_active_high)
        form.addRow("", self.chk_auto_zero)
        form.addRow("", self.chk_heads_req)

        note = QLabel(
            "Canali fisici: default Modulo #1 IN4=SX, IN5=DX — assegnabili in «3. Waveshare». "
            "Zero encoder dopo settle_ms a testa ferma, non al primo contatto."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#95a5a6;")

        lay.addWidget(info)
        lay.addWidget(g)
        lay.addWidget(note)
        lay.addStretch(1)
        return self._scroll(w)

    # ============================================================ 3. Waveshare
    def _cat_waveshare(self) -> QWidget:
        wrap = QWidget()
        root = QVBoxLayout(wrap)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        lock_bar = QFrame()
        lock_bar.setStyleSheet(
            "QFrame { background:#2c3e50; border:1px solid #e67e22; border-radius:8px; }"
        )
        lock_row = QHBoxLayout(lock_bar)
        lock_row.setContentsMargins(12, 10, 12, 10)
        self.lbl_ws_lock = QLabel("Canali in SOLA LETTURA — premi il pulsante per modificare")
        self.lbl_ws_lock.setStyleSheet("color:#f5b041; font-weight:700;")
        self.btn_ws_unlock = QPushButton("ABILITA MODIFICA")
        self.btn_ws_unlock.setCheckable(True)
        self.btn_ws_unlock.setChecked(False)
        self.btn_ws_unlock.setMinimumHeight(40)
        self.btn_ws_unlock.setMinimumWidth(180)
        self.btn_ws_unlock.setToolTip(
            "Attiva/disattiva la modifica dei canali Modulo A/B. "
            "Da disattivato evita cambi accidentali con lo scroll del mouse."
        )
        self.btn_ws_unlock.toggled.connect(self._on_ws_unlock_toggled)
        lock_row.addWidget(self.lbl_ws_lock, 1)
        lock_row.addWidget(self.btn_ws_unlock, 0)
        root.addWidget(lock_bar)
        # Alias per codice load() che cerca chk_ws_unlock
        self.chk_ws_unlock = self.btn_ws_unlock

        tabs = QTabWidget()
        tabs.addTab(self._sub_module(1), "3.1 Modulo A (8 IN / 8 OUT)")
        tabs.addTab(self._sub_module(2), "3.2 Modulo B (8 IN / 8 OUT)")
        tabs.addTab(self._sub_waveshare_overview(), "3.3 Panoramica 16 IN")
        root.addWidget(tabs, 1)
        QTimer.singleShot(0, lambda: self._set_waveshare_unlocked(False))
        return wrap

    def _on_ws_unlock_toggled(self, checked: bool):
        self._set_waveshare_unlocked(checked)
        if checked:
            self.btn_ws_unlock.setText("BLOCCA MODIFICA")
            self.btn_ws_unlock.setStyleSheet(
                "QPushButton { background:#c0392b; color:white; font-weight:700; "
                "padding:8px 14px; border-radius:6px; }"
            )
        else:
            self.btn_ws_unlock.setText("ABILITA MODIFICA")
            self.btn_ws_unlock.setStyleSheet(
                "QPushButton { background:#27ae60; color:white; font-weight:700; "
                "padding:8px 14px; border-radius:6px; }"
            )

    def _set_waveshare_unlocked(self, unlocked: bool):
        self._waveshare_unlocked = bool(unlocked)
        if hasattr(self, "btn_ws_unlock") and self.btn_ws_unlock.isChecked() != unlocked:
            self.btn_ws_unlock.blockSignals(True)
            self.btn_ws_unlock.setChecked(unlocked)
            self.btn_ws_unlock.blockSignals(False)
            self._on_ws_unlock_toggled(unlocked)
        if hasattr(self, "lbl_ws_lock"):
            if unlocked:
                self.lbl_ws_lock.setText("Modifica ATTIVA — ricorda di bloccare quando hai finito")
                self.lbl_ws_lock.setStyleSheet("color:#2ecc71; font-weight:700;")
            else:
                self.lbl_ws_lock.setText(
                    "Canali in SOLA LETTURA — premi «ABILITA MODIFICA» per cambiare i canali"
                )
                self.lbl_ws_lock.setStyleSheet("color:#f5b041; font-weight:700;")
        for wdg in self._ch_widgets.values():
            wdg["combo"].setEnabled(unlocked)
            wdg["active_high"].setEnabled(unlocked)

    def _signal_combo(self) -> QComboBox:
        cmb = QComboBox()
        cmb.addItem(RISERVA, "")
        for key in SIGNAL_KEYS:
            cmb.addItem(SIGNAL_LABELS[key], key)
        cmb.setMinimumWidth(260)
        cmb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        cmb.installEventFilter(self._no_wheel)
        return cmb

    def _sub_module(self, module: int) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(14)
        letter = MODULE_LETTER.get(module, str(module))
        lay.addWidget(
            self._section_title(
                f"Waveshare Modulo {letter} (ID={module}) — 8 ingressi e 8 uscite"
            )
        )

        # --- Ingressi ---
        gin = QGroupBox(f"Ingressi digitali IN1…IN8 — Modulo {letter}")
        gin_lay = QVBoxLayout(gin)
        gin_lay.setContentsMargins(8, 16, 8, 8)
        gin_lay.setSpacing(6)

        table = QTableWidget(8, 4)
        table.setHorizontalHeaderLabels(["Canale", "Segnale logico assegnato", "Attivo alto", "Stato"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QAbstractItemView.NoSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setMinimumHeight(280)
        table.setAlternatingRowColors(True)

        for i in range(8):
            ch_item = QTableWidgetItem(f"IN{i + 1}")
            ch_item.setFlags(Qt.ItemIsEnabled)
            table.setItem(i, 0, ch_item)

            cmb = self._signal_combo()
            ah = QCheckBox()
            ah.setChecked(True)
            ah.setToolTip("Deselezionare per micro NC (conteggi tipici)")
            st = QLabel("—")
            st.setAlignment(Qt.AlignCenter)

            table.setCellWidget(i, 1, cmb)
            wrap = QWidget()
            wh = QHBoxLayout(wrap)
            wh.setContentsMargins(8, 0, 8, 0)
            wh.addWidget(ah, 0, Qt.AlignCenter)
            table.setCellWidget(i, 2, wrap)
            table.setCellWidget(i, 3, st)

            self._ch_widgets[(module, i)] = {
                "combo": cmb,
                "active_high": ah,
                "status": st,
                "table": table,
            }
            cmb.currentIndexChanged.connect(self._on_channel_signal_changed)

        gin_lay.addWidget(table)

        # --- Uscite (sola lettura) ---
        gout = QGroupBox(f"Uscite relè OUT1…OUT8 — Modulo {letter} (mappa schema)")
        gout_lay = QVBoxLayout(gout)
        gout_lay.setContentsMargins(12, 16, 12, 12)
        for line in MODULE_OUTPUTS.get(module, []):
            lab = QLabel("· " + line)
            lab.setStyleSheet("font-family: Consolas, monospace; color:#d5dbdb;")
            gout_lay.addWidget(lab)

        tip = QLabel(
            "Assegna un segnale a ogni IN, oppure lascia «riserva». "
            "Un segnale può stare su un solo canale (controllo al salvataggio)."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#95a5a6;")

        lay.addWidget(gin)
        lay.addWidget(gout)
        lay.addWidget(tip)
        lay.addStretch(1)
        return self._scroll(w)

    def _sub_waveshare_overview(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(12)
        lay.addWidget(self._section_title("Panoramica — 16 ingressi (2 × 8 canali)"))

        self.tbl_overview = QTableWidget(16, 5)
        self.tbl_overview.setHorizontalHeaderLabels(
            ["Modulo", "Canale", "Segnale", "Attivo alto", "Note"]
        )
        self.tbl_overview.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_overview.verticalHeader().setVisible(False)
        self.tbl_overview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_overview.setMinimumHeight(420)
        self.tbl_overview.setAlternatingRowColors(True)
        lay.addWidget(self.tbl_overview, 1)

        btn = QPushButton("Aggiorna panoramica dalle assegnazioni")
        btn.clicked.connect(self._refresh_overview)
        lay.addWidget(btn)
        return w

    def _on_channel_signal_changed(self, *_args):
        # Aggiorna panoramica se esiste
        if hasattr(self, "tbl_overview"):
            self._refresh_overview()

    def _refresh_overview(self):
        if not hasattr(self, "tbl_overview"):
            return
        row = 0
        for module in (1, 2):
            for idx in range(8):
                wdg = self._ch_widgets.get((module, idx))
                if not wdg:
                    continue
                cmb: QComboBox = wdg["combo"]
                key = cmb.currentData() or ""
                label = cmb.currentText()
                ah = wdg["active_high"].isChecked()
                note = ""
                if key in ("fc_min", "head_sx_zero", "head_dx_zero"):
                    note = "Sensore induttivo"
                elif key in ("piece_count_sx", "piece_count_dx"):
                    note = "Micro: conteggio + rientro + fine ciclo"
                elif not key:
                    note = "Non cablato / libero"
                self.tbl_overview.setItem(row, 0, QTableWidgetItem(f"#{module}"))
                self.tbl_overview.setItem(row, 1, QTableWidgetItem(f"IN{idx + 1}"))
                self.tbl_overview.setItem(row, 2, QTableWidgetItem(label))
                self.tbl_overview.setItem(row, 3, QTableWidgetItem("Sì" if ah else "No"))
                self.tbl_overview.setItem(row, 4, QTableWidgetItem(note))
                row += 1

    # ======================================================== 4. Calibrazione
    def _cat_calibration(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(12)
        lay.addWidget(
            self._section_title(
                "Calibrazione lineare carro (2 punti) — encoder vs misura reale"
            )
        )

        info = QLabel(
            "Su guide tonde, sulla lunga distanza encoder e quota reale possono divergere. "
            "Procedura (come sul vecchio CNC): porta il carro a una quota vicina (es. 400 mm) "
            "e a una lontana (es. 3600 mm), misura con metro/laser, calcola "
            "correction_factor = Δmisura / Δencoder e aggiorna impulsi/mm."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#bdc3c7;")
        lay.addWidget(info)

        g_pts = QGroupBox("Punti di calibrazione")
        form = QFormLayout(g_pts)
        form.setContentsMargins(12, 18, 12, 12)
        form.setSpacing(10)

        self.spin_cal_near_nom = self._spin_float(50.0, 2000.0, 400.0, 1)
        self.spin_cal_far_nom = self._spin_float(500.0, 8000.0, 3600.0, 1)
        self.spin_cal_enc_near = self._spin_float(0.0, 8000.0, 0.0, 2)
        self.spin_cal_enc_far = self._spin_float(0.0, 8000.0, 0.0, 2)
        self.spin_cal_meas_near = self._spin_float(0.0, 8000.0, 0.0, 2)
        self.spin_cal_meas_far = self._spin_float(0.0, 8000.0, 0.0, 2)
        self.spin_cal_ppm_nom = self._spin_float(0.001, 1000.0, 84.880, 4)
        self.lbl_cal_factor = QLabel("Fattore: —")
        self.lbl_cal_ppm_eff = QLabel("ppm effettivo: —")
        self.lbl_cal_msg = QLabel("")
        self.lbl_cal_msg.setWordWrap(True)
        self._last_cal_result = None

        self._tip(self.spin_cal_near_nom, "Quota target del punto vicino (mm) per la procedura a 2 punti.")
        self._tip(self.spin_cal_far_nom, "Quota target del punto lontano (mm). Maggiore distanza → migliore correzione.")
        self._tip(self.spin_cal_meas_near, "Misura reale con metro/laser al punto vicino (mm).")
        self._tip(self.spin_cal_meas_far, "Misura reale con metro/laser al punto lontano (mm).")

        form.addRow("Quota nominale punto vicino:", self.spin_cal_near_nom)
        form.addRow("Quota nominale punto lontano:", self.spin_cal_far_nom)

        row_n = QHBoxLayout()
        row_n.addWidget(self.spin_cal_enc_near)
        btn_cap_n = QPushButton("Cattura encoder QUI (vicino)")
        btn_cap_n.clicked.connect(lambda: self._capture_encoder_point("near"))
        row_n.addWidget(btn_cap_n)
        form.addRow("Encoder letto (vicino):", row_n)

        row_f = QHBoxLayout()
        row_f.addWidget(self.spin_cal_enc_far)
        btn_cap_f = QPushButton("Cattura encoder QUI (lontano)")
        btn_cap_f.clicked.connect(lambda: self._capture_encoder_point("far"))
        row_f.addWidget(btn_cap_f)
        form.addRow("Encoder letto (lontano):", row_f)

        form.addRow("Misura reale vicino (mm):", self.spin_cal_meas_near)
        form.addRow("Misura reale lontano (mm):", self.spin_cal_meas_far)
        form.addRow("ppm nominale (da Ø/PPR):", self.spin_cal_ppm_nom)
        form.addRow("", self.lbl_cal_factor)
        form.addRow("", self.lbl_cal_ppm_eff)
        form.addRow("", self.lbl_cal_msg)

        btn_row = QHBoxLayout()
        btn_goto_n = QPushButton("Vai a quota vicino")
        btn_goto_n.clicked.connect(lambda: self._goto_cal_point("near"))
        btn_goto_f = QPushButton("Vai a quota lontano")
        btn_goto_f.clicked.connect(lambda: self._goto_cal_point("far"))
        btn_calc = QPushButton("Calcola correzione")
        btn_calc.clicked.connect(self._calc_correction)
        btn_apply = QPushButton("Applica e salva")
        btn_apply.setStyleSheet(
            "QPushButton { background:#27ae60; color:white; font-weight:700; padding:8px 14px; }"
        )
        btn_apply.clicked.connect(self._apply_correction)
        btn_row.addWidget(btn_goto_n)
        btn_row.addWidget(btn_goto_f)
        btn_row.addWidget(btn_calc)
        btn_row.addWidget(btn_apply)
        btn_row.addStretch(1)

        lay.addWidget(g_pts)
        lay.addLayout(btn_row)

        # --- Modalità servizio: misura lama-lama senza emergenza ---
        g_svc = QGroupBox("Modalità servizio — misura lama↔lama (senza emergenza)")
        svc = QVBoxLayout(g_svc)
        svc.setContentsMargins(12, 18, 12, 12)
        svc.setSpacing(8)
        info_svc = QLabel(
            "Il selettore a chiave sulla pulsantiera mette l'emergenza e blocca anche il carro. "
            "Qui invece: relè OUT7 Modulo A interrompe le bobine dei teleruttori motori lama "
            "(non partono), ma carro e teste restano movimentabili per parametrizzare. "
            "Poi puoi far scendere le lame (pneumatica) e misurare con laser la distanza lama-lama."
        )
        info_svc.setWordWrap(True)
        info_svc.setStyleSheet("color:#bdc3c7;")
        svc.addWidget(info_svc)

        row_svc = QHBoxLayout()
        self.btn_svc_motors = QPushButton("1) INIBISCI MOTORI LAMA (service ON)")
        self.btn_svc_motors.setCheckable(True)
        self.btn_svc_motors.setMinimumHeight(40)
        self.btn_svc_motors.setToolTip(
            "Attiva OUT7 Modulo A: toglie alimentazione alle bobine dei teleruttori motori lama. "
            "NON attiva emergenza → puoi ancora muovere il carro e le teste."
        )
        self.btn_svc_motors.toggled.connect(self._toggle_service_blade_motors)
        self.btn_svc_blades = QPushButton("2) Prepara uscita lame per misura")
        self.btn_svc_blades.setMinimumHeight(40)
        self.btn_svc_blades.setToolTip(
            "Rilascia inibizione EV lama e (in sim) porta le lame fuori. "
            "In reale: usa la pulsantiera per la discesa pneumatica con motori già inibiti."
        )
        self.btn_svc_blades.clicked.connect(self._prepare_blades_for_measure)
        self.btn_svc_off = QPushButton("3) Esci da service (ripristina)")
        self.btn_svc_off.setMinimumHeight(40)
        self.btn_svc_off.setToolTip(
            "Disattiva OUT7 e ripristina uscite service dopo la misura."
        )
        self.btn_svc_off.clicked.connect(self._exit_service_measure)
        row_svc.addWidget(self.btn_svc_motors)
        row_svc.addWidget(self.btn_svc_blades)
        row_svc.addWidget(self.btn_svc_off)
        svc.addLayout(row_svc)
        self.lbl_svc = QLabel("Service: OFF")
        self.lbl_svc.setStyleSheet("font-weight:700; color:#95a5a6;")
        svc.addWidget(self.lbl_svc)

        lay.addWidget(g_svc)
        lay.addStretch(1)
        return self._scroll(w)

    def _mio_or_raw(self):
        return getattr(self.appwin, "machine_adapter", None) or self.machine

    def _toggle_service_blade_motors(self, on: bool):
        src = self._mio_or_raw()
        ok = False
        if src and hasattr(src, "command_set_blade_motors_inhibit"):
            try:
                ok = bool(src.command_set_blade_motors_inhibit(bool(on)))
            except Exception as e:
                logger.error("service motors: %s", e)
        elif src and hasattr(getattr(src, "_raw", src), "command_set_blade_motors_inhibit"):
            try:
                ok = bool(src._raw.command_set_blade_motors_inhibit(bool(on)))
            except Exception as e:
                logger.error("service motors raw: %s", e)
        if on:
            self.btn_svc_motors.setText("1) MOTORI LAMA INIBITI (premi per spegnere)")
            self.lbl_svc.setText("Service: motori lama INIBITI — carro/teste OK")
            self.lbl_svc.setStyleSheet("font-weight:700; color:#e67e22;")
            self._show_toast("Motori lama inibiti (senza emergenza)" if ok else "Comando non disponibile")
        else:
            self.btn_svc_motors.setText("1) INIBISCI MOTORI LAMA (service ON)")
            self.lbl_svc.setText("Service: OFF")
            self.lbl_svc.setStyleSheet("font-weight:700; color:#95a5a6;")
            self._show_toast("Inibizione motori lama disattivata")

    def _prepare_blades_for_measure(self):
        src = self._mio_or_raw()
        raw = getattr(src, "_raw", src) if src else None
        # Assicurati che i motori siano inibiti
        if hasattr(self, "btn_svc_motors") and not self.btn_svc_motors.isChecked():
            self.btn_svc_motors.setChecked(True)
        target = raw or src
        if target and hasattr(target, "command_prepare_blade_measure"):
            try:
                target.command_prepare_blade_measure(True)
                self.lbl_svc.setText(
                    "Service: motori inibiti + lame in misura — usa laser lama↔lama"
                )
                self.lbl_svc.setStyleSheet("font-weight:700; color:#2ecc71;")
                self._show_toast("Pronto per misura lama-lama")
                return
            except Exception as e:
                logger.error("blade measure: %s", e)
        # Fallback: solo rilascio inibizione EV
        if target and hasattr(target, "command_set_blade_inhibit"):
            with contextlib.suppress(Exception):
                target.command_set_blade_inhibit(left=False, right=False)
        QMessageBox.information(
            self,
            "Misura lama-lama",
            "Motori lama inibiti (se supportato).\n"
            "Con la pulsantiera fai scendere le lame (solo pneumatica): "
            "i motori non possono avviarsi.\n"
            "Misura con laser la distanza lama↔lama, poi «Esci da service».",
        )

    def _exit_service_measure(self):
        src = self._mio_or_raw()
        raw = getattr(src, "_raw", src) if src else None
        target = raw or src
        if hasattr(self, "btn_svc_motors") and self.btn_svc_motors.isChecked():
            self.btn_svc_motors.setChecked(False)
        if target and hasattr(target, "command_prepare_blade_measure"):
            with contextlib.suppress(Exception):
                target.command_prepare_blade_measure(False)
        if target and hasattr(target, "command_set_blade_motors_inhibit"):
            with contextlib.suppress(Exception):
                target.command_set_blade_motors_inhibit(False)
        self.lbl_svc.setText("Service: OFF")
        self.lbl_svc.setStyleSheet("font-weight:700; color:#95a5a6;")
        self._show_toast("Modalità service terminata")

    def _current_encoder_mm(self) -> Optional[float]:
        mio = getattr(self.appwin, "machine_adapter", None)
        raw = self.machine
        if mio and hasattr(mio, "get_position"):
            try:
                p = mio.get_position()
                if p is not None:
                    return float(p)
            except Exception:
                pass
        if raw is not None:
            for attr in ("encoder_position", "position_current", "_position_mm"):
                v = getattr(raw, attr, None)
                if v is not None:
                    try:
                        return float(v)
                    except Exception:
                        pass
        return None

    def _capture_encoder_point(self, which: str):
        pos = self._current_encoder_mm()
        if pos is None:
            QMessageBox.warning(self, "Encoder", "Quota encoder non disponibile.")
            return
        if which == "near":
            self.spin_cal_enc_near.setValue(pos)
            self._calib_capture["enc_near"] = pos
        else:
            self.spin_cal_enc_far.setValue(pos)
            self._calib_capture["enc_far"] = pos
        self._show_toast(f"Encoder catturato ({which}): {pos:.2f} mm")

    def _goto_cal_point(self, which: str):
        target = (
            float(self.spin_cal_near_nom.value())
            if which == "near"
            else float(self.spin_cal_far_nom.value())
        )
        mio = getattr(self.appwin, "machine_adapter", None)
        raw = self.machine
        moved = False
        for src in (mio, raw):
            if src and hasattr(src, "command_move"):
                try:
                    moved = bool(src.command_move(target))
                    break
                except Exception as e:
                    logger.error("goto cal: %s", e)
        if moved:
            self._show_toast(f"Posizionamento verso {target:.1f} mm…")
        else:
            QMessageBox.warning(
                self,
                "Movimento",
                "Impossibile avviare il movimento (homing? emergenza? adapter?).",
            )

    def _calc_correction(self):
        res = compute_two_point_correction(
            encoder_near_mm=float(self.spin_cal_enc_near.value()),
            encoder_far_mm=float(self.spin_cal_enc_far.value()),
            measured_near_mm=float(self.spin_cal_meas_near.value()),
            measured_far_mm=float(self.spin_cal_meas_far.value()),
            pulses_per_mm_nominal=float(self.spin_cal_ppm_nom.value()),
        )
        self._last_cal_result = res
        self.lbl_cal_factor.setText(f"Fattore correzione: {res.correction_factor:.6f}")
        self.lbl_cal_ppm_eff.setText(
            f"ppm effettivo: {res.pulses_per_mm_effective:.4f} "
            f"(nominale {res.pulses_per_mm_nominal:.4f})"
        )
        col = "#2ecc71" if res.ok else "#e74c3c"
        self.lbl_cal_msg.setText(res.message)
        self.lbl_cal_msg.setStyleSheet(f"color:{col}; font-weight:600;")

    def _apply_correction(self):
        if self._last_cal_result is None:
            self._calc_correction()
        res = self._last_cal_result
        if res is None or not res.ok:
            QMessageBox.warning(
                self,
                "Calibrazione",
                "Correzione non valida. Calcola prima e verifica le misure "
                "(tolleranza ±10%).",
            )
            return
        self.spin_ppm.setValue(res.pulses_per_mm_effective)
        with contextlib.suppress(Exception):
            raw = getattr(self.machine, "_raw", self.machine)
            if hasattr(raw, "apply_carriage_calibration"):
                raw.apply_carriage_calibration(
                    res.pulses_per_mm_effective, res.correction_factor
                )
        self._save()

    def _show_toast(self, msg: str):
        if hasattr(self.appwin, "toast"):
            with contextlib.suppress(Exception):
                self.appwin.toast.show(msg, "info", 2200)
        elif hasattr(self.appwin, "show_toast"):
            with contextlib.suppress(Exception):
                self.appwin.show_toast(msg, "info")

    # =============================================================== 5. Monitor
    def _cat_monitor(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(12)
        lay.addWidget(self._section_title("Monitor live macchina / adapter"))

        g = QGroupBox("Valori correnti")
        grid = QGridLayout(g)
        grid.setSpacing(10)
        grid.setContentsMargins(12, 18, 12, 12)
        keys = [
            ("pos", "Quota carro"),
            ("enc_sx", "Angolo SX misurato"),
            ("enc_dx", "Angolo DX misurato"),
            ("fc_min", "FC_MIN (homing)"),
            ("fc_sx", "FC SX 0°"),
            ("fc_dx", "FC DX 0°"),
            ("blade", "blade_pulse / cut_done"),
            ("pc_sx", "Micro SX (conteggio)"),
            ("pc_dx", "Micro DX (conteggio)"),
            ("start", "start_pressed"),
            ("emerg", "emergenza"),
        ]
        for i, (k, title) in enumerate(keys):
            grid.addWidget(QLabel(title + ":"), i, 0)
            lab = QLabel("—")
            lab.setStyleSheet("font-weight:700; font-family: Consolas, monospace;")
            grid.addWidget(lab, i, 1)
            self._monitor_labels[k] = lab

        btn = QPushButton("Aggiorna ora")
        btn.clicked.connect(self._refresh_monitor)
        lay.addWidget(g)
        lay.addWidget(btn)
        lay.addStretch(1)
        return self._scroll(w)

    # ======================================================== 5. Documentazione
    def _cat_docs(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(
            """
            <h3>Manuale Configurazione</h3>
            <p>Vedi <code>docs/MANUALE_CONFIGURAZIONE.md</code> — Utility unificata Modulo A/B,
            sblocco Waveshare, calibrazione carro, service OUT7 senza emergenza.</p>
            <h3>Integrazione Raspberry Pi 5</h3>
            <ul>
              <li><b>MD25HV</b>: GPIO 12 / 13 / 16</li>
              <li><b>Encoder carro</b>: AL-ZARD #1 → GPIO 17 / 27 / 22</li>
              <li><b>Encoder teste</b>: rotativi + AL-ZARD #2 → GPIO 5 / 6 / 19 / 26
                  (niente Arduino Nano / MT6701)</li>
              <li><b>I/O campo</b>: 2 moduli Waveshare 8IN/8OUT (A=ID1, B=ID2)</li>
              <li><b>OUT7 Modulo A</b>: inibizione motori lama (service, no EMG)</li>
            </ul>
            <h3>Sensori induttivi</h3>
            <ul>
              <li><b>FC_MIN</b> — homing carro</li>
              <li><b>FC_HEAD_SX_0 / DX_0</b> — zero teste</li>
            </ul>
            <p>Mai 12V/24V sui GPIO. Schema: <code>docs/WIRING_SENSORS_RPI.md</code></p>
            """
        )
        lay.addWidget(browser, 1)
        row = QHBoxLayout()
        for label, rel in (
            ("Manuale Configurazione", "docs/MANUALE_CONFIGURAZIONE.md"),
            ("WIRING_SENSORS_RPI.md", "docs/WIRING_SENSORS_RPI.md"),
            ("Encoder teste", "docs/HEAD_ENCODERS.md"),
            ("Calibrazione carro", "docs/CALIBRATION_CARRIAGE.md"),
            ("Schema elettrico", "docs/blitz/recap/schema_elettrico_blitz_recap.md"),
            ("SVG cablaggio", "docs/blitz/layouts/wiring_sensors_rpi.svg"),
        ):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, r=rel: self._open_doc(r))
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        return w

    def _open_doc(self, rel: str):
        path = project_root() / rel
        if not path.exists():
            QMessageBox.warning(self, "Documento", f"File non trovato:\n{path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # ---------------------------------------------------------------- load/save
    def _clear_channel_assignments(self):
        for wdg in self._ch_widgets.values():
            wdg["combo"].blockSignals(True)
            wdg["combo"].setCurrentIndex(0)
            wdg["active_high"].setChecked(True)
            wdg["combo"].blockSignals(False)

    def _assign_channel(self, module: int, index: int, signal: str, active_high: bool):
        wdg = self._ch_widgets.get((module, index))
        if not wdg:
            return
        cmb: QComboBox = wdg["combo"]
        cmb.blockSignals(True)
        idx = cmb.findData(signal)
        if idx < 0:
            idx = 0
        cmb.setCurrentIndex(idx)
        wdg["active_high"].setChecked(bool(active_high))
        cmb.blockSignals(False)

    def _load(self):
        cfg = load_hardware_config()
        motion = cfg.get("motion_control") or {}
        ge = motion.get("gpio_encoder") or {}
        cal = motion.get("encoder_calibration") or {}
        self.spin_enc_a.setValue(int(ge.get("channel_a_pin", 17)))
        self.spin_enc_b.setValue(int(ge.get("channel_b_pin", 27)))
        self.spin_enc_z.setValue(int(ge.get("index_z_pin", 22)))
        self.chk_enc_index.setChecked(bool(ge.get("enable_index", True)))
        self.spin_enc_ppr.setValue(int(cal.get("encoder_ppr", 1000)))
        q = str(cal.get("quadrature_mode", "x4"))
        if q in ("x1", "x2", "x4"):
            self.cmb_enc_quad.setCurrentText(q)
        self.spin_pulley.setValue(float(cal.get("pulley_diameter_mm", 60.0)))
        self.spin_ppm.setValue(float(cal.get("pulses_per_mm", 84.880)))
        self.chk_enc_invert.setChecked(bool(ge.get("invert", False)))

        he = cfg.get("head_encoders") or {}
        gpio = he.get("gpio") or {}
        self.chk_head_enc_en.setChecked(bool(he.get("enabled", True)))
        iface = "gpio"  # encoder rotativi + AL-ZARD: unico percorso supportato
        self.cmb_head_iface.setCurrentText("gpio")
        self.spin_head_ppr.setValue(int(he.get("ppr", 600)))
        self.spin_head_quad.setValue(int(he.get("quadrature", 4)))
        self.spin_sx_a.setValue(int(gpio.get("sx_a", 5)))
        self.spin_sx_b.setValue(int(gpio.get("sx_b", 6)))
        self.spin_dx_a.setValue(int(gpio.get("dx_a", 19)))
        self.spin_dx_b.setValue(int(gpio.get("dx_b", 26)))
        self.spin_off_sx.setValue(float(he.get("zero_offset_sx_deg", 0.0)))
        self.spin_off_dx.setValue(float(he.get("zero_offset_dx_deg", 0.0)))
        self.chk_inv_sx.setChecked(bool(he.get("invert_sx", False)))
        self.chk_inv_dx.setChecked(bool(he.get("invert_dx", False)))
        self.spin_modbus_sx.setValue(int(he.get("sx_addr", 20)))
        self.spin_modbus_dx.setValue(int(he.get("dx_addr", 21)))

        fc = cfg.get("head_home_fc") or {}
        self.chk_fc_en.setChecked(bool(fc.get("enabled", True)))
        self.spin_settle.setValue(int(fc.get("settle_ms", 400)))
        self.spin_stable.setValue(float(fc.get("stable_deg", 0.2)))
        self.spin_fc_timeout.setValue(float(fc.get("homing_timeout_s", 8.0)))
        self.chk_auto_zero.setChecked(bool(fc.get("auto_zero", False)))
        self.chk_heads_req.setChecked(bool(fc.get("heads_required", False)))
        self.chk_fc_active_high.setChecked(bool(fc.get("active_high", True)))

        # Homing carro FC_MIN
        ch = cfg.get("carriage_homing") or {}
        if hasattr(self, "chk_homing_en"):
            self.chk_homing_en.setChecked(bool(ch.get("enabled", True)))
            self.spin_approach.setValue(float(ch.get("approach_speed_mm_s", 500.0)))
            self.spin_creep.setValue(float(ch.get("creep_speed_mm_s", 80.0)))
            self.spin_backoff.setValue(float(ch.get("backoff_mm", 5.0)))
            self.spin_offset_fc.setValue(float(ch.get("offset_after_fc_mm", 30.0)))
            self.spin_zero_off.setValue(float(ch.get("zero_offset_mm", 0.0)))
            self.spin_fc_settle.setValue(int(ch.get("settle_ms", 200)))
            self.spin_fc_deb.setValue(int(ch.get("debounce_ms", 30)))
            self.chk_use_z.setChecked(bool(ch.get("use_index_z", True)))

        # Cut cycle / micro
        cc = cfg.get("cut_cycle") or {}
        if hasattr(self, "chk_pc_is_cut"):
            self.chk_pc_is_cut.setChecked(bool(cc.get("piece_count_is_cut_done", True)))
            src = str(cc.get("blade_pulse_source", "piece_count")).lower()
            idx = self.cmb_blade_src.findData(
                "piece_count" if src in ("piece_count", "micros", "cut_done") else "dedicated"
            )
            if idx >= 0:
                self.cmb_blade_src.setCurrentIndex(idx)
            self.spin_cut_deb.setValue(int(cc.get("debounce_ms", 40)))
            self.chk_count_active.setChecked(bool(cc.get("count_uses_active_heads", True)))
            self.chk_blade_hw.setChecked(bool(cc.get("blade_out_requires_blade_on_hw", True)))

        # Calibrazione carro
        ccal = cfg.get("carriage_calibration") or {}
        if hasattr(self, "spin_cal_near_nom"):
            self.spin_cal_near_nom.setValue(float(ccal.get("point_near_nominal_mm", 400.0)))
            self.spin_cal_far_nom.setValue(float(ccal.get("point_far_nominal_mm", 3600.0)))
            ppm_nom = float(ccal.get("pulses_per_mm_nominal") or cal.get("pulses_per_mm") or 84.880)
            self.spin_cal_ppm_nom.setValue(ppm_nom)
            ppm_eff = float(ccal.get("pulses_per_mm_effective") or self.spin_ppm.value())
            self.spin_ppm.setValue(ppm_eff)
            if ccal.get("last_encoder_near_mm") is not None:
                self.spin_cal_enc_near.setValue(float(ccal["last_encoder_near_mm"]))
            if ccal.get("last_encoder_far_mm") is not None:
                self.spin_cal_enc_far.setValue(float(ccal["last_encoder_far_mm"]))
            if ccal.get("last_measured_near_mm") is not None:
                self.spin_cal_meas_near.setValue(float(ccal["last_measured_near_mm"]))
            if ccal.get("last_measured_far_mm") is not None:
                self.spin_cal_meas_far.setValue(float(ccal["last_measured_far_mm"]))
            factor = float(ccal.get("correction_factor", 1.0))
            self.lbl_cal_factor.setText(f"Fattore correzione: {factor:.6f}")
            self.lbl_cal_ppm_eff.setText(f"ppm effettivo: {ppm_eff:.4f}")

        # Canali Waveshare: default + override digital_inputs
        self._clear_channel_assignments()
        defaults = default_digital_inputs()
        dig = cfg.get("digital_inputs") or {}
        for key in SIGNAL_KEYS:
            meta = dict(defaults.get(key) or {})
            if isinstance(dig.get(key), dict):
                meta.update(dig[key])
            self._assign_channel(
                int(meta.get("module", 1)),
                int(meta.get("index", 0)),
                key,
                bool(meta.get("active_high", True)),
            )

        self._refresh_overview()
        if hasattr(self, "chk_ws_unlock"):
            self.chk_ws_unlock.setChecked(False)
            self._set_waveshare_unlocked(False)
        logger.info("Config encoder/ingressi caricata da %s", hardware_config_path())

    def _collect_digital_inputs(self) -> Dict[str, Any]:
        digital: Dict[str, Any] = {
            "description": "Mappa segnali logici → Waveshare (vista per canale in Utility)",
        }
        for (module, index), wdg in self._ch_widgets.items():
            key = wdg["combo"].currentData() or ""
            if not key:
                continue
            digital[key] = {
                "module": int(module),
                "index": int(index),
                "active_high": bool(wdg["active_high"].isChecked()),
                "label": SIGNAL_LABELS.get(key, key),
            }
        return digital

    def _collect_updates(self) -> Dict[str, Any]:
        digital = self._collect_digital_inputs()
        # Allinea head_home_fc agli assegnamenti SX/DX se presenti
        sx = digital.get("head_sx_zero") or {}
        dx = digital.get("head_dx_zero") or {}
        head_fc = {
            "enabled": bool(self.chk_fc_en.isChecked()),
            "settle_ms": int(self.spin_settle.value()),
            "stable_deg": float(self.spin_stable.value()),
            "homing_timeout_s": float(self.spin_fc_timeout.value()),
            "auto_zero": bool(self.chk_auto_zero.isChecked()),
            "heads_required": bool(self.chk_heads_req.isChecked()),
            "active_high": bool(self.chk_fc_active_high.isChecked()),
        }
        if sx:
            head_fc["module"] = int(sx.get("module", 1))
            head_fc["sx_input_index"] = int(sx.get("index", 3))
        if dx:
            head_fc["dx_input_index"] = int(dx.get("index", 4))
            if "module" not in head_fc:
                head_fc["module"] = int(dx.get("module", 1))

        from datetime import datetime

        ppm_nom = float(self.spin_cal_ppm_nom.value()) if hasattr(self, "spin_cal_ppm_nom") else float(self.spin_ppm.value())
        ppm_eff = float(self.spin_ppm.value())
        factor = 1.0
        if self._last_cal_result is not None and self._last_cal_result.ok:
            factor = float(self._last_cal_result.correction_factor)
            ppm_eff = float(self._last_cal_result.pulses_per_mm_effective)
            ppm_nom = float(self._last_cal_result.pulses_per_mm_nominal)

        carriage_homing = {
            "enabled": bool(self.chk_homing_en.isChecked()) if hasattr(self, "chk_homing_en") else True,
            "approach_speed_mm_s": float(self.spin_approach.value()) if hasattr(self, "spin_approach") else 500.0,
            "creep_speed_mm_s": float(self.spin_creep.value()) if hasattr(self, "spin_creep") else 80.0,
            "backoff_mm": float(self.spin_backoff.value()) if hasattr(self, "spin_backoff") else 5.0,
            "offset_after_fc_mm": float(self.spin_offset_fc.value()) if hasattr(self, "spin_offset_fc") else 30.0,
            "zero_offset_mm": float(self.spin_zero_off.value()) if hasattr(self, "spin_zero_off") else 0.0,
            "settle_ms": int(self.spin_fc_settle.value()) if hasattr(self, "spin_fc_settle") else 200,
            "debounce_ms": int(self.spin_fc_deb.value()) if hasattr(self, "spin_fc_deb") else 30,
            "use_index_z": bool(self.chk_use_z.isChecked()) if hasattr(self, "chk_use_z") else True,
        }

        blade_src = "piece_count"
        if hasattr(self, "cmb_blade_src"):
            blade_src = self.cmb_blade_src.currentData() or "piece_count"

        cut_cycle = {
            "piece_count_is_cut_done": bool(self.chk_pc_is_cut.isChecked()) if hasattr(self, "chk_pc_is_cut") else True,
            "blade_pulse_source": blade_src,
            "debounce_ms": int(self.spin_cut_deb.value()) if hasattr(self, "spin_cut_deb") else 40,
            "count_uses_active_heads": bool(self.chk_count_active.isChecked()) if hasattr(self, "chk_count_active") else True,
            "blade_out_requires_blade_on_hw": bool(self.chk_blade_hw.isChecked()) if hasattr(self, "chk_blade_hw") else True,
        }

        carriage_calibration = {
            "point_near_nominal_mm": float(self.spin_cal_near_nom.value()) if hasattr(self, "spin_cal_near_nom") else 400.0,
            "point_far_nominal_mm": float(self.spin_cal_far_nom.value()) if hasattr(self, "spin_cal_far_nom") else 3600.0,
            "last_encoder_near_mm": float(self.spin_cal_enc_near.value()) if hasattr(self, "spin_cal_enc_near") else None,
            "last_encoder_far_mm": float(self.spin_cal_enc_far.value()) if hasattr(self, "spin_cal_enc_far") else None,
            "last_measured_near_mm": float(self.spin_cal_meas_near.value()) if hasattr(self, "spin_cal_meas_near") else None,
            "last_measured_far_mm": float(self.spin_cal_meas_far.value()) if hasattr(self, "spin_cal_meas_far") else None,
            "correction_factor": factor,
            "pulses_per_mm_nominal": ppm_nom,
            "pulses_per_mm_effective": ppm_eff,
            "last_calibrated_at": datetime.now().isoformat(timespec="seconds"),
        }

        return {
            "motion_control": {
                "gpio_encoder": {
                    "channel_a_pin": int(self.spin_enc_a.value()),
                    "channel_b_pin": int(self.spin_enc_b.value()),
                    "index_z_pin": int(self.spin_enc_z.value()),
                    "enable_index": bool(self.chk_enc_index.isChecked()),
                    "invert": bool(self.chk_enc_invert.isChecked()),
                },
                "encoder_calibration": {
                    "encoder_ppr": int(self.spin_enc_ppr.value()),
                    "quadrature_mode": self.cmb_enc_quad.currentText(),
                    "pulley_diameter_mm": float(self.spin_pulley.value()),
                    "pulses_per_mm": ppm_eff,
                    "pulses_per_revolution": int(self.spin_enc_ppr.value())
                    * {"x1": 1, "x2": 2, "x4": 4}.get(self.cmb_enc_quad.currentText(), 4),
                },
            },
            "head_encoders": {
                "enabled": bool(self.chk_head_enc_en.isChecked()),
                "interface": "gpio",
                "ppr": int(self.spin_head_ppr.value()),
                "quadrature": int(self.spin_head_quad.value()),
                "zero_offset_sx_deg": float(self.spin_off_sx.value()),
                "zero_offset_dx_deg": float(self.spin_off_dx.value()),
                "invert_sx": bool(self.chk_inv_sx.isChecked()),
                "invert_dx": bool(self.chk_inv_dx.isChecked()),
                "gpio": {
                    "sx_a": int(self.spin_sx_a.value()),
                    "sx_b": int(self.spin_sx_b.value()),
                    "dx_a": int(self.spin_dx_a.value()),
                    "dx_b": int(self.spin_dx_b.value()),
                },
            },
            "head_home_fc": head_fc,
            "carriage_homing": carriage_homing,
            "carriage_calibration": carriage_calibration,
            "cut_cycle": cut_cycle,
            "digital_inputs": digital,
            "transmission": {
                "correction_factor": factor,
            },
        }

    def _validate(self) -> List[str]:
        errors: List[str] = []
        pins = [
            ("carro A", self.spin_enc_a.value()),
            ("carro B", self.spin_enc_b.value()),
            ("carro Z", self.spin_enc_z.value()),
            ("teste SX A", self.spin_sx_a.value()),
            ("teste SX B", self.spin_sx_b.value()),
            ("teste DX A", self.spin_dx_a.value()),
            ("teste DX B", self.spin_dx_b.value()),
        ]
        reserved_motor = {12, 13, 16}
        seen: Dict[int, str] = {}
        for name, pin in pins:
            if pin in reserved_motor:
                errors.append(f"• {name}: GPIO {pin} riservato a MD25HV (12/13/16)")
            if pin in seen:
                errors.append(f"• Conflitto GPIO {pin}: {seen[pin]} e {name}")
            else:
                seen[pin] = name

        used_signals: Dict[str, str] = {}
        for (module, index), wdg in self._ch_widgets.items():
            key = wdg["combo"].currentData() or ""
            if not key:
                continue
            slot = f"Modulo #{module} IN{index + 1}"
            if key in used_signals:
                errors.append(
                    f"• Segnale «{key}» assegnato a {used_signals[key]} e {slot}"
                )
            else:
                used_signals[key] = slot
        return errors

    def _save(self):
        errors = self._validate()
        if errors:
            QMessageBox.critical(
                self,
                "Errori configurazione",
                "Correggere prima di salvare:\n\n" + "\n".join(errors),
            )
            return
        updates = self._collect_updates()
        if not merge_and_save(updates):
            QMessageBox.critical(self, "Errore", "Salvataggio hardware_config.json fallito.")
            return
        with contextlib.suppress(Exception):
            raw = getattr(self.machine, "_raw", self.machine)
            if hasattr(raw, "reload_digital_inputs"):
                raw.reload_digital_inputs(updates.get("digital_inputs"))
            elif hasattr(raw, "_digital_inputs"):
                raw._digital_inputs = updates.get("digital_inputs")
        self._refresh_overview()
        QMessageBox.information(
            self,
            "Salvato",
            f"Configurazione salvata in:\n{hardware_config_path()}\n\n"
            "Per pin GPIO riavviare l'applicazione.",
        )

    # ---------------------------------------------------------------- monitor
    def _start_monitor(self):
        self._poll = QTimer(self)
        self._poll.setInterval(400)
        self._poll.timeout.connect(self._refresh_monitor)
        self._poll.start()

    def _get_input(self, name: str) -> Optional[bool]:
        mio = getattr(self.appwin, "machine_adapter", None)
        raw = self.machine
        for src in (mio, raw):
            if src and hasattr(src, "get_input"):
                try:
                    return bool(src.get_input(name))
                except Exception:
                    pass
        return None

    def _set_onoff(self, key: str, v: Optional[bool]):
        lab = self._monitor_labels.get(key)
        if not lab:
            return
        if v is None:
            lab.setText("—")
            lab.setStyleSheet("font-weight:700; color:#7f8c8d;")
        else:
            lab.setText("ON" if v else "OFF")
            lab.setStyleSheet(
                f"font-weight:700; color:{'#2ecc71' if v else '#7f8c8d'};"
            )

    def _refresh_monitor(self):
        mio = getattr(self.appwin, "machine_adapter", None)
        raw = self.machine
        pos = None
        if mio and hasattr(mio, "get_position"):
            with contextlib.suppress(Exception):
                pos = mio.get_position()
        if pos is None and raw is not None:
            pos = getattr(raw, "encoder_position", None) or getattr(raw, "position_current", None)

        sx = getattr(raw, "measured_left_head_angle", None) if raw else None
        dx = getattr(raw, "measured_right_head_angle", None) if raw else None
        if sx is None and raw is not None:
            sx = getattr(raw, "left_head_angle", None)
        if dx is None and raw is not None:
            dx = getattr(raw, "right_head_angle", None)

        self._monitor_labels["pos"].setText(f"{float(pos):.2f} mm" if pos is not None else "—")
        self._monitor_labels["enc_sx"].setText(f"{float(sx):.2f}°" if sx is not None else "—")
        self._monitor_labels["enc_dx"].setText(f"{float(dx):.2f}°" if dx is not None else "—")

        self._set_onoff("fc_min", self._get_input("fc_min"))
        self._set_onoff("fc_sx", self._get_input("head_sx_zero"))
        self._set_onoff("fc_dx", self._get_input("head_dx_zero"))
        self._set_onoff("blade", self._get_input("blade_pulse"))
        self._set_onoff("pc_sx", self._get_input("piece_count_sx"))
        self._set_onoff("pc_dx", self._get_input("piece_count_dx"))
        self._set_onoff("start", self._get_input("start_pressed"))
        self._set_onoff("emerg", self._get_input("emergency_active"))

        # Stato canali in tabella Waveshare (se mappati)
        for (module, index), wdg in self._ch_widgets.items():
            key = wdg["combo"].currentData() or ""
            st: QLabel = wdg["status"]
            if not key:
                st.setText("—")
                st.setStyleSheet("color:#7f8c8d;")
                continue
            v = self._get_input(key)
            if v is None:
                st.setText("?")
                st.setStyleSheet("color:#7f8c8d;")
            else:
                st.setText("ON" if v else "OFF")
                st.setStyleSheet(f"color:{'#2ecc71' if v else '#7f8c8d'}; font-weight:700;")


__all__ = ["EncodersInputsTab"]
