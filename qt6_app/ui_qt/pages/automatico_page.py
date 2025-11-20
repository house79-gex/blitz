"""
Pagina Automatico - Gestione ciclo automatico con ottimizzazione e visualizzazione migliorata
Version: 2.1
Date: 2025-11-20
Author: house79-gex
"""

import json
import logging
import time
from datetime import datetime
from typing import Optional, Dict, List, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QGroupBox, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox,
    QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QFrame, QProgressBar, QTabWidget, QListWidget,
    QMessageBox, QFileDialog, QGridLayout, QScrollArea
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QThread, QObject
from PySide6.QtGui import QFont, QColor, QPalette, QIcon

# Fix import paths - usa percorsi relativi corretti
try:
    # Se siamo in qt6_app, dobbiamo salire di un livello per trovare ui
    import sys
    import os
    parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    from ui.shared.machine_state import MachineState
except ImportError:
    # Fallback: usa una classe dummy
    class MachineState:
        def __init__(self):
            self.position = 0
            self.angle_sx = 90
            self.angle_dx = 90
            self.emergency = False
            self.homing_done = False
            
        def do_homing(self):
            self.homing_done = True

# Import locali con percorsi relativi corretti
from ..widgets.toast import Toast
from ..widgets.heads_view import HeadsView
from ..widgets.plan_visualizer import PlanVisualizer  # Import dal modulo widgets
from ..dialogs.optimization_run_qt import OptimizationDialog
from ..dialogs.optimization_settings_qt import OptimizationSettingsDialog
from ..dialogs.cutlist_viewer_qt import CutlistViewerDialog
from ..logic.planner import plan_ilp, plan_bfd
from ..logic.refiner import refine_plan
from ..logic.sequencer import Sequencer
from ..services.orders_store import OrdersStore
from ..utils.settings import load_settings, save_settings

logger = logging.getLogger(__name__)


class AutomaticWorker(QObject):
    """Worker thread per l'esecuzione del ciclo automatico"""
    
    # Segnali
    progress = Signal(int)
    status = Signal(str)
    job_completed = Signal(int, int)  # bar_idx, job_idx
    bar_completed = Signal(int)  # bar_idx
    cycle_completed = Signal()
    error = Signal(str)
    
    def __init__(self, machine_state: MachineState, plan: Dict):
        super().__init__()
        self.machine_state = machine_state
        self.plan = plan
        self.is_running = False
        self.is_paused = False
        
    def run(self):
        """Esegue il ciclo automatico"""
        self.is_running = True
        
        try:
            bars = self.plan.get('bars', [])
            total_jobs = sum(len(bar.get('jobs', [])) for bar in bars)
            completed_jobs = 0
            
            for bar_idx, bar in enumerate(bars):
                if not self.is_running:
                    break
                    
                self.status.emit(f"Lavorazione barra {bar_idx + 1}/{len(bars)}")
                
                jobs = bar.get('jobs', [])
                for job_idx, job in enumerate(jobs):
                    if not self.is_running:
                        break
                        
                    # Pausa se richiesto
                    while self.is_paused and self.is_running:
                        time.sleep(0.1)
                    
                    # Esegui il job
                    self._execute_job(bar_idx, job_idx, job)
                    
                    # Segnala completamento job
                    self.job_completed.emit(bar_idx, job_idx)
                    completed_jobs += 1
                    
                    # Aggiorna progresso
                    progress = int((completed_jobs / total_jobs) * 100) if total_jobs > 0 else 0
                    self.progress.emit(progress)
                
                # Segnala completamento barra
                self.bar_completed.emit(bar_idx)
            
            if self.is_running:
                self.cycle_completed.emit()
                
        except Exception as e:
            logger.error(f"Errore nel ciclo automatico: {e}")
            self.error.emit(str(e))
            
    def _execute_job(self, bar_idx: int, job_idx: int, job: Dict):
        """Esegue un singolo job"""
        # Simula esecuzione (da sostituire con controllo reale macchina)
        length = job.get('length', 0)
        angle_sx = job.get('angle_sx', 90)
        angle_dx = job.get('angle_dx', 90)
        
        self.status.emit(f"Taglio: {length:.1f}mm [{angle_sx}°/{angle_dx}°]")
        
        # Posiziona teste
        if self.machine_state:
            # Movimento simulato
            time.sleep(0.5)  # Simula movimento
            
        # Esegui taglio
        time.sleep(1.0)  # Simula taglio
        
    def stop(self):
        """Ferma il ciclo"""
        self.is_running = False
        
    def pause(self):
        """Mette in pausa il ciclo"""
        self.is_paused = True
        
    def resume(self):
        """Riprende il ciclo"""
        self.is_paused = False


class AutomaticoPage(QWidget):
    """Pagina per la gestione del modo automatico con ottimizzazione"""
    
    def __init__(self, machine_state: MachineState, parent=None):
        super().__init__(parent)
        self.machine_state = machine_state
        self.orders_store = OrdersStore()
        self.current_plan = None
        self.current_bar_idx = -1
        self.current_job_idx = -1
        self.worker = None
        self.worker_thread = None
        self.pieces_cut = 0
        self.cycle_start_time = None
        
        # Timer per aggiornamenti UI
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_ui_state)
        self.update_timer.start(100)
        
        self._init_ui()
        self._load_settings()
        
    def _init_ui(self):
        """Inizializza l'interfaccia utente"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Header
        header_layout = QHBoxLayout()
        
        title = QLabel("Modalità Automatica")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        # Pulsanti modalità
        self.btn_orders = QPushButton("📋 Gestione Ordini")
        self.btn_orders.clicked.connect(self._open_orders_manager)
        header_layout.addWidget(self.btn_orders)
        
        self.btn_optimize = QPushButton("⚡ Ottimizza")
        self.btn_optimize.clicked.connect(self._run_optimization)
        header_layout.addWidget(self.btn_optimize)
        
        layout.addLayout(header_layout)
        
        # Splitter principale
        splitter = QSplitter(Qt.Horizontal)
        
        # Pannello sinistro - Controlli
        left_panel = self._create_left_panel()
        splitter.addWidget(left_panel)
        
        # Pannello centrale - Visualizzazione
        center_panel = self._create_center_panel()
        splitter.addWidget(center_panel)
        
        # Pannello destro - Stato
        right_panel = self._create_right_panel()
        splitter.addWidget(right_panel)
        
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 1)
        
        layout.addWidget(splitter)
        
        # Status bar
        self.status_bar = self._create_status_bar()
        layout.addWidget(self.status_bar)
        
    def _create_left_panel(self) -> QWidget:
        """Crea il pannello sinistro con i controlli"""
        panel = QFrame()
        panel.setFrameStyle(QFrame.Box)
        layout = QVBoxLayout(panel)
        
        # Gruppo controllo ciclo
        cycle_group = QGroupBox("Controllo Ciclo")
        cycle_layout = QVBoxLayout()
        
        # Pulsanti principali
        self.btn_start = QPushButton("▶ AVVIA")
        self.btn_start.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        self.btn_start.clicked.connect(self.start_automatic_cycle)
        cycle_layout.addWidget(self.btn_start)
        
        self.btn_pause = QPushButton("⏸ PAUSA")
        self.btn_pause.setEnabled(False)
        self.btn_pause.setStyleSheet("""
            QPushButton {
                background-color: #ffc107;
                color: black;
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover:enabled {
                background-color: #e0a800;
            }
        """)
        self.btn_pause.clicked.connect(self.pause_automatic_cycle)
        cycle_layout.addWidget(self.btn_pause)
        
        self.btn_stop = QPushButton("⏹ STOP")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover:enabled {
                background-color: #c82333;
            }
        """)
        self.btn_stop.clicked.connect(self.stop_automatic_cycle)
        cycle_layout.addWidget(self.btn_stop)
        
        cycle_group.setLayout(cycle_layout)
        layout.addWidget(cycle_group)
        
        # Gruppo parametri
        params_group = QGroupBox("Parametri Taglio")
        params_layout = QGridLayout()
        
        # Velocità taglio
        params_layout.addWidget(QLabel("Velocità:"), 0, 0)
        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(10, 100)
        self.speed_spin.setValue(50)
        self.speed_spin.setSuffix(" %")
        params_layout.addWidget(self.speed_spin, 0, 1)
        
        # Kerf
        params_layout.addWidget(QLabel("Kerf:"), 1, 0)
        self.kerf_spin = QDoubleSpinBox()
        self.kerf_spin.setRange(0.0, 10.0)
        self.kerf_spin.setValue(3.0)
        self.kerf_spin.setSuffix(" mm")
        self.kerf_spin.setSingleStep(0.1)
        params_layout.addWidget(self.kerf_spin, 1, 1)
        
        # Ripasso
        params_layout.addWidget(QLabel("Ripasso:"), 2, 0)
        self.ripasso_spin = QDoubleSpinBox()
        self.ripasso_spin.setRange(0.0, 50.0)
        self.ripasso_spin.setValue(5.0)
        self.ripasso_spin.setSuffix(" mm")
        params_layout.addWidget(self.ripasso_spin, 2, 1)
        
        # Recupero
        self.recupero_check = QCheckBox("Recupero automatico")
        self.recupero_check.setChecked(True)
        params_layout.addWidget(self.recupero_check, 3, 0, 1, 2)
        
        params_group.setLayout(params_layout)
        layout.addWidget(params_group)
        
        # Gruppo opzioni
        options_group = QGroupBox("Opzioni")
        options_layout = QVBoxLayout()
        
        self.auto_advance_check = QCheckBox("Avanzamento automatico")
        self.auto_advance_check.setChecked(True)
        options_layout.addWidget(self.auto_advance_check)
        
        self.confirm_cut_check = QCheckBox("Conferma taglio")
        self.confirm_cut_check.setChecked(False)
        options_layout.addWidget(self.confirm_cut_check)
        
        self.sound_enabled_check = QCheckBox("Segnali acustici")
        self.sound_enabled_check.setChecked(True)
        options_layout.addWidget(self.sound_enabled_check)
        
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)
        
        layout.addStretch()
        
        return panel
        
    def _create_center_panel(self) -> QWidget:
        """Crea il pannello centrale con visualizzazione piano"""
        panel = QFrame()
        panel.setFrameStyle(QFrame.Box)
        layout = QVBoxLayout(panel)
        
        # Tab widget
        self.tabs = QTabWidget()
        
        # Tab Piano di taglio
        plan_tab = QWidget()
        plan_layout = QVBoxLayout(plan_tab)
        
        # Info piano corrente
        info_frame = QFrame()
        info_frame.setFrameStyle(QFrame.Box)
        info_layout = QHBoxLayout(info_frame)
        
        self.plan_info_label = QLabel("Nessun piano caricato")
        info_layout.addWidget(self.plan_info_label)
        
        info_layout.addStretch()
        
        self.btn_load_plan = QPushButton("📂 Carica Piano")
        self.btn_load_plan.clicked.connect(self._load_plan)
        info_layout.addWidget(self.btn_load_plan)
        
        self.btn_save_plan = QPushButton("💾 Salva Piano")
        self.btn_save_plan.clicked.connect(self._save_plan)
        self.btn_save_plan.setEnabled(False)
        info_layout.addWidget(self.btn_save_plan)
        
        plan_layout.addWidget(info_frame)
        
        # Visualizzatore piano - usa il widget importato
        self.plan_visualizer = PlanVisualizer(self)
        self.plan_visualizer.bar_selected.connect(self._on_bar_selected)
        plan_layout.addWidget(self.plan_visualizer)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        plan_layout.addWidget(self.progress_bar)
        
        self.tabs.addTab(plan_tab, "📊 Piano di Taglio")
        
        # Tab Lista tagli
        cuts_tab = QWidget()
        cuts_layout = QVBoxLayout(cuts_tab)
        
        self.cuts_table = QTableWidget()
        self.cuts_table.setColumnCount(7)
        self.cuts_table.setHorizontalHeaderLabels([
            "Barra", "Pezzo", "Lunghezza", "Ang.SX", "Ang.DX", 
            "Stato", "Note"
        ])
        self.cuts_table.horizontalHeader().setStretchLastSection(True)
        cuts_layout.addWidget(self.cuts_table)
        
        self.tabs.addTab(cuts_tab, "📋 Lista Tagli")
        
        # Tab Log
        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self.log_text)
        
        self.tabs.addTab(log_tab, "📝 Log")
        
        layout.addWidget(self.tabs)
        
        return panel
        
    def _create_right_panel(self) -> QWidget:
        """Crea il pannello destro con lo stato"""
        panel = QFrame()
        panel.setFrameStyle(QFrame.Box)
        layout = QVBoxLayout(panel)
        
        # Stato macchina
        machine_group = QGroupBox("Stato Macchina")
        machine_layout = QVBoxLayout()
        
        # Vista teste
        self.heads_view = HeadsView(self.machine_state)
        self.heads_view.setFixedHeight(100)
        machine_layout.addWidget(self.heads_view)
        
        # Info posizione
        pos_frame = QFrame()
        pos_frame.setFrameStyle(QFrame.Box)
        pos_layout = QGridLayout(pos_frame)
        
        pos_layout.addWidget(QLabel("Posizione:"), 0, 0)
        self.pos_label = QLabel("0.0 mm")
        self.pos_label.setStyleSheet("font-weight: bold;")
        pos_layout.addWidget(self.pos_label, 0, 1)
        
        pos_layout.addWidget(QLabel("Testa SX:"), 1, 0)
        self.angle_sx_label = QLabel("90°")
        self.angle_sx_label.setStyleSheet("font-weight: bold;")
        pos_layout.addWidget(self.angle_sx_label, 1, 1)
        
        pos_layout.addWidget(QLabel("Testa DX:"), 2, 0)
        self.angle_dx_label = QLabel("90°")
        self.angle_dx_label.setStyleSheet("font-weight: bold;")
        pos_layout.addWidget(self.angle_dx_label, 2, 1)
        
        machine_layout.addWidget(pos_frame)
        
        machine_group.setLayout(machine_layout)
        layout.addWidget(machine_group)
        
        # Job corrente
        job_group = QGroupBox("Job Corrente")
        job_layout = QVBoxLayout()
        
        self.current_job_frame = QFrame()
        self.current_job_frame.setFrameStyle(QFrame.Box)
        job_info_layout = QVBoxLayout(self.current_job_frame)
        
        self.current_job_label = QLabel("Nessun job attivo")
        self.current_job_label.setFont(QFont("Arial", 10, QFont.Bold))
        job_info_layout.addWidget(self.current_job_label)
        
        self.current_length_label = QLabel("Lunghezza: -")
        job_info_layout.addWidget(self.current_length_label)
        
        self.current_angle_label = QLabel("Angoli: -")
        job_info_layout.addWidget(self.current_angle_label)
        
        self.current_note_label = QLabel("")
        self.current_note_label.setWordWrap(True)
        job_info_layout.addWidget(self.current_note_label)
        
        job_layout.addWidget(self.current_job_frame)
        
        # Pulsanti job
        job_buttons_layout = QHBoxLayout()
        
        self.btn_skip_job = QPushButton("⏭ Salta")
        self.btn_skip_job.setEnabled(False)
        self.btn_skip_job.clicked.connect(self._skip_current_job)
        job_buttons_layout.addWidget(self.btn_skip_job)
        
        self.btn_retry_job = QPushButton("🔄 Ripeti")
        self.btn_retry_job.setEnabled(False)
        self.btn_retry_job.clicked.connect(self._retry_current_job)
        job_buttons_layout.addWidget(self.btn_retry_job)
        
        job_layout.addLayout(job_buttons_layout)
        
        job_group.setLayout(job_layout)
        layout.addWidget(job_group)
        
        # Statistiche
        stats_group = QGroupBox("Statistiche")
        stats_layout = QGridLayout()
        
        stats_layout.addWidget(QLabel("Pezzi tagliati:"), 0, 0)
        self.pieces_cut_label = QLabel("0")
        self.pieces_cut_label.setStyleSheet("font-weight: bold;")
        stats_layout.addWidget(self.pieces_cut_label, 0, 1)
        
        stats_layout.addWidget(QLabel("Tempo ciclo:"), 1, 0)
        self.cycle_time_label = QLabel("00:00:00")
        self.cycle_time_label.setStyleSheet("font-weight: bold;")
        stats_layout.addWidget(self.cycle_time_label, 1, 1)
        
        stats_layout.addWidget(QLabel("Efficienza:"), 2, 0)
        self.efficiency_label = QLabel("-")
        self.efficiency_label.setStyleSheet("font-weight: bold;")
        stats_layout.addWidget(self.efficiency_label, 2, 1)
        
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)
        
        layout.addStretch()
        
        return panel
        
    def _create_status_bar(self) -> QWidget:
        """Crea la status bar"""
        status = QFrame()
        status.setFrameStyle(QFrame.Box)
        status.setMaximumHeight(30)
        
        layout = QHBoxLayout(status)
        layout.setContentsMargins(5, 2, 5, 2)
        
        # Stato ciclo
        self.cycle_status_label = QLabel("⚪ Inattivo")
        layout.addWidget(self.cycle_status_label)
        
        layout.addWidget(QLabel("|"))
        
        # Messaggio stato
        self.status_message = QLabel("Pronto")
        layout.addWidget(self.status_message)
        
        layout.addStretch()
        
        # Ora
        self.time_label = QLabel()
        self._update_time()
        layout.addWidget(self.time_label)
        
        # Timer per aggiornare l'ora
        time_timer = QTimer(self)
        time_timer.timeout.connect(self._update_time)
        time_timer.start(1000)
        
        return status
        
    def _update_time(self):
        """Aggiorna l'ora nella status bar"""
        now = datetime.now()
        self.time_label.setText(now.strftime("%H:%M:%S"))
        
    def _update_ui_state(self):
        """Aggiorna lo stato dell'interfaccia"""
        if self.machine_state:
            # Aggiorna posizione
            self.pos_label.setText(f"{self.machine_state.position:.1f} mm")
            self.angle_sx_label.setText(f"{self.machine_state.angle_sx}°")
            self.angle_dx_label.setText(f"{self.machine_state.angle_dx}°")
            
            # Aggiorna vista teste
            if self.heads_view:
                self.heads_view.update_state(
                    self.machine_state.position,
                    self.machine_state.angle_sx,
                    self.machine_state.angle_dx
                )
                
    def start_automatic_cycle(self):
        """Avvia il ciclo automatico"""
        if not self.current_plan:
            self.show_toast("Nessun piano di taglio caricato!", "warning")
            return
            
        # Verifica stato macchina
        if not self._check_machine_ready():
            return
            
        self.log_message("Avvio ciclo automatico...")
        
        # Aggiorna UI
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.cycle_status_label.setText("🟢 Attivo")
        self.cycle_status_label.setStyleSheet("color: green; font-weight: bold;")
        
        # Reset contatori
        self.current_bar_idx = 0
        self.current_job_idx = 0
        self.pieces_cut = 0
        self.cycle_start_time = time.time()
        
        # Reset visualizzatore
        if self.plan_visualizer:
            if hasattr(self.plan_visualizer, 'reset'):
                self.plan_visualizer.reset()
            
        # Avvia worker thread
        self._start_worker()
        
        self.show_toast("Ciclo automatico avviato", "success")
        
    def pause_automatic_cycle(self):
        """Mette in pausa il ciclo automatico"""
        if self.worker:
            self.worker.pause()
            
        self.btn_pause.setText("▶ RIPRENDI")
        self.btn_pause.clicked.disconnect()
        self.btn_pause.clicked.connect(self.resume_automatic_cycle)
        
        self.cycle_status_label.setText("⏸ Pausa")
        self.cycle_status_label.setStyleSheet("color: orange; font-weight: bold;")
        
        self.log_message("Ciclo in pausa")
        self.show_toast("Ciclo in pausa", "info")
        
    def resume_automatic_cycle(self):
        """Riprende il ciclo automatico"""
        if self.worker:
            self.worker.resume()
            
        self.btn_pause.setText("⏸ PAUSA")
        self.btn_pause.clicked.disconnect()
        self.btn_pause.clicked.connect(self.pause_automatic_cycle)
        
        self.cycle_status_label.setText("🟢 Attivo")
        self.cycle_status_label.setStyleSheet("color: green; font-weight: bold;")
        
        self.log_message("Ciclo ripreso")
        self.show_toast("Ciclo ripreso", "success")
        
    def stop_automatic_cycle(self):
        """Ferma il ciclo automatico"""
        if self.worker:
            self.worker.stop()
            
        self._cleanup_worker()
        
        # Aggiorna UI
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.cycle_status_label.setText("🔴 Fermato")
        self.cycle_status_label.setStyleSheet("color: red; font-weight: bold;")
        
        self.log_message("Ciclo fermato")
        self.show_toast("Ciclo fermato", "warning")
        
        # Reset dopo 2 secondi
        QTimer.singleShot(2000, self._reset_cycle_status)
        
    def _reset_cycle_status(self):
        """Reset dello stato del ciclo"""
        self.cycle_status_label.setText("⚪ Inattivo")
        self.cycle_status_label.setStyleSheet("")
        
    def _start_worker(self):
        """Avvia il worker thread"""
        if self.worker_thread:
            self._cleanup_worker()
            
        self.worker = AutomaticWorker(self.machine_state, self.current_plan)
        self.worker_thread = QThread()
        
        # Connetti segnali
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.status.connect(self.status_message.setText)
        self.worker.job_completed.connect(self._on_job_completed)
        self.worker.bar_completed.connect(self._on_bar_completed)
        self.worker.cycle_completed.connect(self._on_cycle_completed)
        self.worker.error.connect(self._on_worker_error)
        
        # Avvia thread
        self.worker_thread.start()
        
    def _cleanup_worker(self):
        """Pulisce il worker thread"""
        if self.worker:
            self.worker.stop()
            
        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait()
            
        self.worker = None
        self.worker_thread = None
        
    @Slot(int, int)
    def _on_job_completed(self, bar_idx: int, job_idx: int):
        """Gestisce il completamento di un job"""
        self.pieces_cut += 1
        self.pieces_cut_label.setText(str(self.pieces_cut))
        
        # Aggiorna visualizzatore piano
        if self.plan_visualizer:
            self.plan_visualizer.mark_job_completed(bar_idx, job_idx)
            
        # Aggiorna tabella tagli
        self._update_cuts_table_status(bar_idx, job_idx, "✅ Completato")
        
        # Log
        self.log_message(f"Job completato: Barra {bar_idx+1}, Pezzo {job_idx+1}")
        
        # Avanza se auto-advance attivo
        if self.auto_advance_check.isChecked():
            QTimer.singleShot(200, lambda: self._advance_to_next_job(bar_idx, job_idx))
            
    @Slot(int)
    def _on_bar_completed(self, bar_idx: int):
        """Gestisce il completamento di una barra"""
        self.log_message(f"Barra {bar_idx+1} completata")
        
        # Ritarda il collasso per permettere la visualizzazione
        if self.plan_visualizer:
            if hasattr(self.plan_visualizer, 'collapse_completed_bar'):
                QTimer.singleShot(500, lambda: self.plan_visualizer.collapse_completed_bar(bar_idx))
            
    @Slot()
    def _on_cycle_completed(self):
        """Gestisce il completamento del ciclo"""
        if self.cycle_start_time:
            cycle_time = time.time() - self.cycle_start_time
            hours = int(cycle_time // 3600)
            minutes = int((cycle_time % 3600) // 60)
            seconds = int(cycle_time % 60)
            
            self.cycle_time_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            
            self.log_message(f"Ciclo completato! Tempo totale: {hours:02d}:{minutes:02d}:{seconds:02d}", "success")
        
        self.show_toast("Ciclo completato con successo!", "success")
        
        # Reset UI
        self.stop_automatic_cycle()
        
    @Slot(str)
    def _on_worker_error(self, error_msg: str):
        """Gestisce gli errori del worker"""
        self.log_message(f"ERRORE: {error_msg}", "error")
        QMessageBox.critical(self, "Errore", f"Errore nel ciclo automatico:\n{error_msg}")
        self.stop_automatic_cycle()
        
    def _advance_to_next_job(self, current_bar: int, current_job: int):
        """Avanza al prossimo job nel piano"""
        if not self.current_plan:
            return
            
        bars = self.current_plan.get('bars', [])
        
        # Trova prossimo job
        if current_bar < len(bars):
            bar_jobs = bars[current_bar].get('jobs', [])
            
            if current_job + 1 < len(bar_jobs):
                # Prossimo job nella stessa barra
                new_bar = current_bar
                new_job = current_job + 1
            elif current_bar + 1 < len(bars):
                # Primo job della prossima barra
                new_bar = current_bar + 1
                new_job = 0
            else:
                # Piano completato
                return
                
            # Aggiorna posizione
            self.current_bar_idx = new_bar
            self.current_job_idx = new_job
            
            # Aggiorna visualizzatore
            if self.plan_visualizer:
                self.plan_visualizer.set_current_position(new_bar, new_job)
                
            # Aggiorna info job corrente
            self._update_current_job_info()
            
    def _update_current_job_info(self):
        """Aggiorna le informazioni del job corrente"""
        if not self.current_plan or self.current_bar_idx < 0 or self.current_job_idx < 0:
            self.current_job_label.setText("Nessun job attivo")
            self.current_length_label.setText("Lunghezza: -")
            self.current_angle_label.setText("Angoli: -")
            self.current_note_label.setText("")
            return
            
        bars = self.current_plan.get('bars', [])
        if self.current_bar_idx >= len(bars):
            return
            
        current_bar = bars[self.current_bar_idx]
        jobs = current_bar.get('jobs', [])
        
        if self.current_job_idx >= len(jobs):
            return
            
        current_job = jobs[self.current_job_idx]
        
        # Aggiorna etichette
        self.current_job_label.setText(
            f"Barra {self.current_bar_idx + 1}/{len(bars)} - "
            f"Pezzo {self.current_job_idx + 1}/{len(jobs)}"
        )
        
        self.current_length_label.setText(f"Lunghezza: {current_job.get('length', 0):.1f} mm")
        self.current_angle_label.setText(
            f"Angoli: {current_job.get('angle_sx', 90)}° / {current_job.get('angle_dx', 90)}°"
        )
        
        note = current_job.get('note', '')
        self.current_note_label.setText(f"Note: {note}" if note else "")
        
        # Evidenzia con animazione
        self._highlight_current_job()
        
    def _highlight_current_job(self):
        """Evidenzia visualmente il job corrente"""
        # Animazione highlight
        original_style = self.current_job_frame.styleSheet()
        highlight_style = """
            QFrame {
                background-color: rgba(255, 165, 0, 50);
                border: 2px solid orange;
                border-radius: 5px;
            }
        """
        
        self.current_job_frame.setStyleSheet(highlight_style)
        
        # Rimuovi highlight dopo 500ms
        QTimer.singleShot(500, lambda: self.current_job_frame.setStyleSheet(original_style))
        
    def _run_optimization(self):
        """Apre il dialog di ottimizzazione"""
        dialog = OptimizationDialog(self.orders_store, self)
        
        if dialog.exec():
            plan = dialog.get_optimized_plan()
            if plan:
                self.load_plan(plan)
                self.show_toast("Piano ottimizzato caricato", "success")
                
    def load_plan(self, plan: Dict):
        """Carica un piano di taglio"""
        self.current_plan = plan
        self.current_bar_idx = -1
        self.current_job_idx = -1
        
        # Aggiorna visualizzatore
        if self.plan_visualizer:
            self.plan_visualizer.load_plan(plan)
            
        # Aggiorna info piano
        bars_count = len(plan.get('bars', []))
        jobs_count = sum(len(bar.get('jobs', [])) for bar in plan.get('bars', []))
        
        self.plan_info_label.setText(
            f"Piano caricato: {bars_count} barre, {jobs_count} tagli"
        )
        
        # Abilita salvataggio
        self.btn_save_plan.setEnabled(True)
        
        # Popola tabella tagli
        self._populate_cuts_table()
        
        # Log
        self.log_message(f"Piano caricato: {bars_count} barre, {jobs_count} tagli")
        
    def _populate_cuts_table(self):
        """Popola la tabella dei tagli"""
        if not self.current_plan:
            return
            
        self.cuts_table.setRowCount(0)
        
        for bar_idx, bar in enumerate(self.current_plan.get('bars', [])):
            for job_idx, job in enumerate(bar.get('jobs', [])):
                row = self.cuts_table.rowCount()
                self.cuts_table.insertRow(row)
                
                self.cuts_table.setItem(row, 0, QTableWidgetItem(str(bar_idx + 1)))
                self.cuts_table.setItem(row, 1, QTableWidgetItem(str(job_idx + 1)))
                self.cuts_table.setItem(row, 2, QTableWidgetItem(f"{job.get('length', 0):.1f}"))
                self.cuts_table.setItem(row, 3, QTableWidgetItem(f"{job.get('angle_sx', 90)}°"))
                self.cuts_table.setItem(row, 4, QTableWidgetItem(f"{job.get('angle_dx', 90)}°"))
                self.cuts_table.setItem(row, 5, QTableWidgetItem("⏳ In attesa"))
                self.cuts_table.setItem(row, 6, QTableWidgetItem(job.get('note', '')))
                
    def _update_cuts_table_status(self, bar_idx: int, job_idx: int, status: str):
        """Aggiorna lo stato nella tabella tagli"""
        # Trova la riga corrispondente
        for row in range(self.cuts_table.rowCount()):
            bar_item = self.cuts_table.item(row, 0)
            job_item = self.cuts_table.item(row, 1)
            
            if bar_item and job_item:
                if int(bar_item.text()) == bar_idx + 1 and int(job_item.text()) == job_idx + 1:
                    status_item = self.cuts_table.item(row, 5)
                    if status_item:
                        status_item.setText(status)
                        if "Completato" in status:
                            status_item.setForeground(QColor(0, 200, 0))
                    break
                    
    def _load_plan(self):
        """Carica un piano da file"""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Carica Piano di Taglio",
            "",
            "File JSON (*.json)"
        )
        
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    plan = json.load(f)
                self.load_plan(plan)
                self.show_toast("Piano caricato con successo", "success")
            except Exception as e:
                QMessageBox.critical(self, "Errore", f"Errore nel caricamento del piano:\n{str(e)}")
                
    def _save_plan(self):
        """Salva il piano corrente su file"""
        if not self.current_plan:
            return
            
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Salva Piano di Taglio",
            f"piano_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "File JSON (*.json)"
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(self.current_plan, f, indent=2, ensure_ascii=False)
                self.show_toast("Piano salvato con successo", "success")
            except Exception as e:
                QMessageBox.critical(self, "Errore", f"Errore nel salvataggio del piano:\n{str(e)}")
                
    def _on_bar_selected(self, bar_idx: int):
        """Gestisce la selezione di una barra"""
        if self.worker and hasattr(self.worker, 'is_running') and self.worker.is_running:
            self.show_toast("Impossibile cambiare barra durante l'esecuzione", "warning")
            return
            
        self.current_bar_idx = bar_idx
        self.current_job_idx = 0
        
        if self.plan_visualizer:
            self.plan_visualizer.set_current_position(bar_idx, 0)
            
        self._update_current_job_info()
        
    def _skip_current_job(self):
        """Salta il job corrente"""
        if self.worker and hasattr(self.worker, 'is_running') and self.worker.is_running:
            # Segnala al worker di saltare
            self.log_message(f"Job saltato: Barra {self.current_bar_idx+1}, Pezzo {self.current_job_idx+1}")
            self._advance_to_next_job(self.current_bar_idx, self.current_job_idx)
            
    def _retry_current_job(self):
        """Ripete il job corrente"""
        if self.worker and hasattr(self.worker, 'is_running') and self.worker.is_running:
            self.log_message(f"Ripetizione job: Barra {self.current_bar_idx+1}, Pezzo {self.current_job_idx+1}")
            # TODO: Implementa logica di retry
            
    def _open_orders_manager(self):
        """Apre il gestore ordini"""
        # TODO: Implementa apertura dialog ordini
        self.show_toast("Gestore ordini non ancora implementato", "info")
        
    def _check_machine_ready(self) -> bool:
        """Verifica che la macchina sia pronta"""
        if not self.machine_state:
            QMessageBox.warning(self, "Attenzione", "Stato macchina non disponibile")
            return False
            
        if hasattr(self.machine_state, 'emergency') and self.machine_state.emergency:
            QMessageBox.critical(self, "Errore", "Emergenza attiva! Ripristinare prima di procedere.")
            return False
            
        if hasattr(self.machine_state, 'homing_done') and not self.machine_state.homing_done:
            response = QMessageBox.question(
                self, 
                "Homing non eseguito",
                "L'homing non è stato eseguito. Vuoi eseguirlo ora?",
                QMessageBox.Yes | QMessageBox.No
            )
            if response == QMessageBox.Yes:
                # Esegui homing
                if hasattr(self.machine_state, 'do_homing'):
                    self.machine_state.do_homing()
                    return self.machine_state.homing_done
            return False
            
        return True
        
    def log_message(self, message: str, level: str = "info"):
        """Aggiunge un messaggio al log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Colore basato sul livello
        if level == "error":
            color = "red"
            prefix = "❌"
        elif level == "warning":
            color = "orange"
            prefix = "⚠️"
        elif level == "success":
            color = "green"
            prefix = "✅"
        else:
            color = "white"
            prefix = "ℹ️"
            
        html = f'<span style="color: gray">[{timestamp}]</span> '
        html += f'<span style="color: {color}">{prefix} {message}</span>'
        
        self.log_text.append(html)
        
        # Auto-scroll
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
    def show_toast(self, message: str, toast_type: str = "info"):
        """Mostra un toast di notifica"""
        toast = Toast(message, toast_type, self)
        toast.show()
        
    def _load_settings(self):
        """Carica le impostazioni salvate"""
        settings = load_settings()
        
        if 'automatic' in settings:
            auto_settings = settings['automatic']
            self.speed_spin.setValue(auto_settings.get('speed', 50))
            self.kerf_spin.setValue(auto_settings.get('kerf', 3.0))
            self.ripasso_spin.setValue(auto_settings.get('ripasso', 5.0))
            self.recupero_check.setChecked(auto_settings.get('recupero', True))
            self.auto_advance_check.setChecked(auto_settings.get('auto_advance', True))
            self.confirm_cut_check.setChecked(auto_settings.get('confirm_cut', False))
            self.sound_enabled_check.setChecked(auto_settings.get('sound_enabled', True))
            
    def save_settings(self):
        """Salva le impostazioni correnti"""
        settings = load_settings()
        
        settings['automatic'] = {
            'speed': self.speed_spin.value(),
            'kerf': self.kerf_spin.value(),
            'ripasso': self.ripasso_spin.value(),
            'recupero': self.recupero_check.isChecked(),
            'auto_advance': self.auto_advance_check.isChecked(),
            'confirm_cut': self.confirm_cut_check.isChecked(),
            'sound_enabled': self.sound_enabled_check.isChecked()
        }
        
        save_settings(settings)
        
    def closeEvent(self, event):
        """Gestisce la chiusura della pagina"""
        # Salva impostazioni
        self.save_settings()
        
        # Ferma ciclo se attivo
        if self.worker and hasattr(self.worker, 'is_running') and self.worker.is_running:
            self.stop_automatic_cycle()
            
        # Cleanup
        self._cleanup_worker()
        
        event.accept()
