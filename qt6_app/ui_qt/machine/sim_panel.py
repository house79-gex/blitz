from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QHBoxLayout, QSpinBox, QFormLayout, QCheckBox
from PySide6.QtCore import QTimer, Qt

class SimulationPanel(QWidget):
    """
    Pannello per generare manualmente segnali nei test.
    Da montare solo se la macchina è SimulationMachine.
    """
    def __init__(self, machine, parent=None):
        super().__init__(parent)
        self.machine = machine
        self.setWindowTitle("Simulazione I/O")
        lay = QVBoxLayout(self); lay.setSpacing(6)

        self.lbl_pos = QLabel("Posizione: 0.00 mm")
        lay.addWidget(self.lbl_pos)

        form = QFormLayout()
        self.sp_target = QSpinBox(); self.sp_target.setRange(0,10000); self.sp_target.setValue(1500)
        form.addRow("Target mm", self.sp_target)
        self.sp_cut_len = QSpinBox(); self.sp_cut_len.setRange(10,7000); self.sp_cut_len.setValue(500)
        form.addRow("Len pezzo (test)", self.sp_cut_len)
        lay.addLayout(form)

        btn_move = QPushButton("Simula posizionamento")
        btn_move.clicked.connect(self._do_move)
        lay.addWidget(btn_move)

        btn_cut = QPushButton("Impulso lama (Taglio)")
        btn_cut.clicked.connect(lambda: self.machine.command_sim_cut_pulse())
        lay.addWidget(btn_cut)

        btn_start = QPushButton("Impulso Start")
        btn_start.clicked.connect(lambda: self.machine.command_sim_start_pulse())
        lay.addWidget(btn_start)

        br_row = QHBoxLayout()
        btn_lock = QPushButton("Blocca freno")
        btn_lock.clicked.connect(self.machine.command_lock_brake)
        btn_rel = QPushButton("Rilascia freno")
        btn_rel.clicked.connect(self.machine.command_release_brake)
        br_row.addWidget(btn_lock); br_row.addWidget(btn_rel)
        lay.addLayout(br_row)

        pr_row = QHBoxLayout()
        btn_lp = QPushButton("Lock Pressore SX")
        btn_lp.clicked.connect(lambda: self.machine.command_set_pressers(True, self.machine.right_presser_locked))
        btn_lr = QPushButton("Unlock Pressore SX")
        btn_lr.clicked.connect(lambda: self.machine.command_set_pressers(False, self.machine.right_presser_locked))
        pr_row.addWidget(btn_lp); pr_row.addWidget(btn_lr)
        lay.addLayout(pr_row)

        pr_row2 = QHBoxLayout()
        btn_rp = QPushButton("Lock Pressore DX")
        btn_rp.clicked.connect(lambda: self.machine.command_set_pressers(self.machine.left_presser_locked, True))
        btn_rr = QPushButton("Unlock Pressore DX")
        btn_rr.clicked.connect(lambda: self.machine.command_set_pressers(self.machine.left_presser_locked, False))
        pr_row2.addWidget(btn_rp); pr_row2.addWidget(btn_rr)
        lay.addLayout(pr_row2)

        self.chk_auto_tick = QCheckBox("Auto tick")
        self.chk_auto_tick.setChecked(True)
        lay.addWidget(self.chk_auto_tick)

        self.timer = QTimer(self); self.timer.timeout.connect(self._on_tick)
        self.timer.start(120)

    def _do_move(self):
        if not self.machine.machine_homed:
            return
        self.machine.command_move(self.sp_target.value(), ang_sx=90.0, ang_dx=0.0,
                                  profile="SIM", element="Test")

    def _on_tick(self):
        if self.chk_auto_tick.isChecked():
            self.machine.tick()
        pos = self.machine.get_position()
        self.lbl_pos.setText(f"Posizione: {pos:.2f} mm" if pos is not None else "Posizione: —")
