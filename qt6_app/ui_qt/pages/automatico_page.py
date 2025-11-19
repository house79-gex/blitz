"""
Pagina Automatico - Gestione ciclo automatico con ottimizzazione e visualizzazione migliorata
Version: 2.0
Date: 2025-11-19
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
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QThread, QObject, QPropertyAnimation, QRect, QEasingCurve
from PySide6.QtGui import QFont, QColor, QPalette, QIcon, QPainter, QBrush, QPen

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
    # Fallback: prova con il percorso relativo diretto
    try:
        from ...ui.shared.machine_state import MachineState
    except ImportError:
        # Se anche questo fallisce, usa una classe dummy
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
from ..dialogs.optimization_run_qt import OptimizationDialog
from ..dialogs.optimization_settings_qt import OptimizationSettingsDialog
from ..dialogs.cutlist_viewer_qt import CutlistViewerDialog
from ..logic.planner import plan_ilp, plan_bfd
from ..logic.refiner import refine_plan
from ..logic.sequencer import Sequencer
from ..services.orders_store import OrdersStore
from ..utils.settings import load_settings, save_settings

logger = logging.getLogger(__name__)


class PlanVisualizer(QWidget):
    """Widget per visualizzare il piano di taglio con animazioni migliorate"""
    
    bar_selected = Signal(int)  # Emesso quando si seleziona una barra
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.plan = None
        self.current_bar_idx = -1
        self.current_job_idx = -1
        self.completed_bars = set()  # Track delle barre completate
        self.collapsing_bars = set()  # Barre in fase di collasso
        self.collapse_timers = {}  # Timer per ritardare il collasso
        
        # Configurazione visualizzazione
        self.bar_height = 60
        self.collapsed_bar_height = 15  # Altezza barra collassata
        self.job_padding = 2
        self.bar_margin = 10
        self.collapse_delay_ms = 500  # Ritardo prima del collasso
        
        self._setup_ui()
        
    def _setup_ui(self):
        """Setup dell'interfaccia utente"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Area scroll per le barre
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Container per le barre
        self.bars_container = QWidget()
        self.bars_layout = QVBoxLayout(self.bars_container)
        self.bars_layout.setSpacing(5)
        
        self.scroll.setWidget(self.bars_container)
        layout.addWidget(self.scroll)
        
    def load_plan(self, plan):
        """Carica un nuovo piano di taglio"""
        self.plan = plan
        self.current_bar_idx = -1
        self.current_job_idx = -1
        self.completed_bars.clear()
        self.collapsing_bars.clear()
        
        # Cancella timer esistenti
        for timer in self.collapse_timers.values():
            timer.stop()
        self.collapse_timers.clear()
        
        self._rebuild_display()
        
    def _rebuild_display(self):
        """Ricostruisce la visualizzazione del piano"""
        # Pulisci layout esistente
        while self.bars_layout.count():
            item = self.bars_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        if not self.plan or 'bars' not in self.plan:
            return
            
        # Crea widget per ogni barra
        for idx, bar_data in enumerate(self.plan['bars']):
            bar_widget = self._create_bar_widget(idx, bar_data)
            self.bars_layout.addWidget(bar_widget)
            
        # Aggiungi spacer finale
        self.bars_layout.addStretch()
        
    def _create_bar_widget(self, bar_idx, bar_data):
        """Crea un widget per una singola barra"""
        bar_frame = BarFrame(bar_idx, bar_data, self)
        
        # Imposta stato iniziale
        if bar_idx in self.completed_bars:
            bar_frame.set_completed(True)
        
        if bar_idx in self.collapsing_bars:
            bar_frame.set_collapsed(True)
        elif bar_idx == self.current_bar_idx:
            bar_frame.set_active(True)
            
        # Connetti segnali
        bar_frame.clicked.connect(lambda idx=bar_idx: self.bar_selected.emit(idx))
        
        return bar_frame
        
    def set_current_position(self, bar_idx, job_idx):
        """Aggiorna la posizione corrente nel piano"""
        old_bar_idx = self.current_bar_idx
        self.current_bar_idx = bar_idx
        self.current_job_idx = job_idx
        
        # Se cambiamo barra, gestisci il collasso della precedente
        if old_bar_idx != bar_idx and old_bar_idx >= 0:
            self._handle_bar_completion(old_bar_idx)
            
        # Aggiorna visualizzazione
        self._update_bars_display()
        
    def _handle_bar_completion(self, bar_idx):
        """Gestisce il completamento di una barra con ritardo nel collasso"""
        if bar_idx not in self.completed_bars:
            self.completed_bars.add(bar_idx)
            
            # Crea timer per ritardare il collasso
            if bar_idx not in self.collapse_timers:
                timer = QTimer()
                timer.setSingleShot(True)
                timer.timeout.connect(lambda: self._collapse_bar(bar_idx))
                self.collapse_timers[bar_idx] = timer
                timer.start(self.collapse_delay_ms)
                
    def _collapse_bar(self, bar_idx):
        """Collassa effettivamente una barra dopo il ritardo"""
        if bar_idx in self.completed_bars and bar_idx != self.current_bar_idx:
            self.collapsing_bars.add(bar_idx)
            
            # Trova il widget della barra e animalo
            for i in range(self.bars_layout.count()):
                widget = self.bars_layout.itemAt(i).widget()
                if isinstance(widget, BarFrame) and widget.bar_idx == bar_idx:
                    widget.animate_collapse()
                    break
                    
        # Rimuovi timer
        if bar_idx in self.collapse_timers:
            del self.collapse_timers[bar_idx]
            
    def collapse_completed_bar(self, bar_idx: int):
        """Collassa una barra completata con animazione ritardata"""
        if bar_idx == self.current_bar_idx:
            # Non collassare la barra attiva
            return
            
        if bar_idx not in self.collapsing_bars:
            self.collapsing_bars.add(bar_idx)
            
            # Trova il widget della barra
            for i in range(self.bars_layout.count()):
                widget = self.bars_layout.itemAt(i).widget()
                if hasattr(widget, 'bar_idx') and widget.bar_idx == bar_idx:
                    # Anima il collasso
                    if hasattr(widget, 'animate_collapse'):
                        widget.animate_collapse()
                    break
            
    def _update_bars_display(self):
        """Aggiorna la visualizzazione di tutte le barre"""
        for i in range(self.bars_layout.count()):
            widget = self.bars_layout.itemAt(i).widget()
            if isinstance(widget, BarFrame):
                # Reset stato
                widget.set_active(False)
                
                # Imposta stato corrente
                if widget.bar_idx == self.current_bar_idx:
                    widget.set_active(True)
                    widget.set_current_job(self.current_job_idx)
                    # Assicura che la barra attiva sia visibile
                    self._ensure_bar_visible(widget)
                elif widget.bar_idx in self.completed_bars:
                    widget.set_completed(True)
                    
    def _ensure_bar_visible(self, bar_widget):
        """Assicura che la barra sia visibile nell'area di scroll"""
        QTimer.singleShot(50, lambda: self.scroll.ensureWidgetVisible(bar_widget))
        
    def mark_job_completed(self, bar_idx, job_idx):
        """Marca un job come completato"""
        for i in range(self.bars_layout.count()):
            widget = self.bars_layout.itemAt(i).widget()
            if isinstance(widget, BarFrame) and widget.bar_idx == bar_idx:
                widget.mark_job_completed(job_idx)
                break


class BarFrame(QFrame):
    """Frame per una singola barra con supporto per animazioni"""
    
    clicked = Signal(int)
    
    def __init__(self, bar_idx, bar_data, parent=None):
        super().__init__(parent)
        self.bar_idx = bar_idx
        self.bar_data = bar_data
        self.is_active = False
        self.is_completed = False
        self.is_collapsed = False
        self.current_job_idx = -1
        self.completed_jobs = set()
        
        # Configurazione dimensioni
        self.expanded_height = 60
        self.collapsed_height = 15
        
        self.setFrameStyle(QFrame.Box)
        self.setFixedHeight(self.expanded_height)
        self.setCursor(Qt.PointingHandCursor)
        
        self._setup_ui()
        
    def _setup_ui(self):
        """Setup dell'interfaccia della barra"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Header con info barra
        header_layout = QHBoxLayout()
        
        # Indicatore stato
        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: gray;")
        header_layout.addWidget(self.status_indicator)
        
        # Info barra
        self.info_label = QLabel(f"Barra #{self.bar_idx + 1} - {self.bar_data.get('length', 0):.1f}mm")
        header_layout.addWidget(self.info_label)
        
        # Jobs completati
        self.progress_label = QLabel()
        self._update_progress_label()
        header_layout.addWidget(self.progress_label)
        
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        # Widget per visualizzare i jobs
        self.jobs_widget = JobsWidget(self.bar_data.get('jobs', []))
        layout.addWidget(self.jobs_widget)
        
    def _update_progress_label(self):
        """Aggiorna l'etichetta del progresso"""
        total_jobs = len(self.bar_data.get('jobs', []))
        completed = len(self.completed_jobs)
        self.progress_label.setText(f"({completed}/{total_jobs})")
        
    def set_active(self, active):
        """Imposta lo stato attivo della barra"""
        self.is_active = active
        if active:
            self.status_indicator.setStyleSheet("color: orange;")
            self.setStyleSheet("""
                BarFrame {
                    border: 2px solid orange;
                    background-color: rgba(255, 165, 0, 20);
                }
            """)
            # Non collassare mai la barra attiva
            if self.is_collapsed:
                self.expand()
        else:
            self._update_status_indicator()
            self.setStyleSheet("")
            
    def set_completed(self, completed):
        """Imposta lo stato completato della barra"""
        self.is_completed = completed
        self._update_status_indicator()
        
    def set_collapsed(self, collapsed):
        """Imposta lo stato collassato della barra"""
        if collapsed and not self.is_active:  # Non collassare se attiva
            self.is_collapsed = True
            self.jobs_widget.setVisible(False)
            self.setFixedHeight(self.collapsed_height)
        else:
            self.expand()
            
    def expand(self):
        """Espande la barra"""
        self.is_collapsed = False
        self.jobs_widget.setVisible(True)
        self.setFixedHeight(self.expanded_height)
        
    def _update_status_indicator(self):
        """Aggiorna l'indicatore di stato"""
        if self.is_completed:
            self.status_indicator.setStyleSheet("color: green;")
        elif self.is_active:
            self.status_indicator.setStyleSheet("color: orange;")
        else:
            self.status_indicator.setStyleSheet("color: gray;")
            
    def set_current_job(self, job_idx):
        """Imposta il job corrente"""
        self.current_job_idx = job_idx
        self.jobs_widget.set_current_job(job_idx)
        
    def mark_job_completed(self, job_idx):
        """Marca un job come completato"""
        self.completed_jobs.add(job_idx)
        self.jobs_widget.mark_job_completed(job_idx)
        self._update_progress_label()
        
    def animate_collapse(self):
        """Anima il collasso della barra"""
        if not self.is_active:  # Non animare se attiva
            animation = QPropertyAnimation(self, b"maximumHeight")
            animation.setDuration(300)
            animation.setStartValue(self.expanded_height)
            animation.setEndValue(self.collapsed_height)
            animation.setEasingCurve(QEasingCurve.InOutQuad)
            animation.finished.connect(lambda: self.set_collapsed(True))
            animation.start()
            
    def mousePressEvent(self, event):
        """Gestisce il click sulla barra"""
        if event.button() == Qt.LeftButton:
            # Se è collassata, espandila temporaneamente
            if self.is_collapsed:
                self.expand()
            self.clicked.emit(self.bar_idx)
        super().mousePressEvent(event)


class JobsWidget(QWidget):
    """Widget per visualizzare i jobs in una barra"""
    
    def __init__(self, jobs, parent=None):
        super().__init__(parent)
        self.jobs = jobs
        self.current_job_idx = -1
        self.completed_jobs = set()
        self.setFixedHeight(25)
        
    def paintEvent(self, event):
        """Disegna i jobs"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if not self.jobs:
            return
            
        width = self.width()
        height = self.height()
        total_length = sum(job.get('length', 0) for job in self.jobs)
        
        if total_length <= 0:
            return
            
        x = 0
        for idx, job in enumerate(self.jobs):
            job_length = job.get('length', 0)
            job_width = int((job_length / total_length) * width)
            
            # Colore basato sullo stato
            if idx in self.completed_jobs:
                color = QColor(0, 200, 0, 180)  # Verde per completato
            elif idx == self.current_job_idx:
                color = QColor(255, 165, 0, 180)  # Arancione per corrente
            else:
                color = QColor(100, 100, 100, 100)  # Grigio per pendente
                
            painter.fillRect(x, 0, job_width - 1, height, color)
            
            # Disegna info job se c'è spazio
            if job_width > 30:
                painter.setPen(Qt.white)
                painter.setFont(QFont("Arial", 8))
                text = f"{job_length:.0f}"
                painter.drawText(x + 2, 0, job_width - 4, height, 
                               Qt.AlignCenter, text)
                
            x += job_width
            
    def set_current_job(self, job_idx):
        """Imposta il job corrente"""
        self.current_job_idx = job_idx
        self.update()
        
    def mark_job_completed(self, job_idx):
        """Marca un job come completato"""
        self.completed_jobs.add(job_idx)
        self.update()


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
                    progress = int((completed_jobs / total_jobs) * 100)
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
        
        # Visualizzatore piano 
        self.plan_visualizer = PlanVisualizer(self)
        self.plan_visualizer.bar_selected.connect(self._on_bar_selected)
        
        # Scroll area per il visualizzatore
        scroll = QScrollArea()
        scroll.setWidget(self.plan_visualizer)
        scroll.setWidgetResizable(True)
        plan_layout.addWidget(scroll)
        
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
        self.heads_view = HeadsView()
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
            
            self.log_message(f"Ciclo completato! Tempo totale: {hours:02d}:{minutes:02d}:{seconds:02d}")
        
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
        """Evidenzia visivamente il job corrente"""
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
                with open(filename, 'r') as f:
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
                with open(filename, 'w') as f:
                    json.dump(self.current_plan, f, indent=2)
                self.show_toast("Piano salvato con successo", "success")
            except Exception as e:
                QMessageBox.critical(self, "Errore", f"Errore nel salvataggio del piano:\n{str(e)}")
                
    def _on_bar_selected(self, bar_idx: int):
        """Gestisce la selezione di una barra"""
        if self.worker and self.worker.is_running:
            self.show_toast("Impossibile cambiare barra durante l'esecuzione", "warning")
            return
            
        self.current_bar_idx = bar_idx
        self.current_job_idx = 0
        
        if self.plan_visualizer:
            self.plan_visualizer.set_current_position(bar_idx, 0)
            
        self._update_current_job_info()
        
    def _skip_current_job(self):
        """Salta il job corrente"""
        if self.worker and self.worker.is_running:
            # Segnala al worker di saltare
            self.log_message(f"Job saltato: Barra {self.current_bar_idx+1}, Pezzo {self.current_job_idx+1}")
            self._advance_to_next_job(self.current_bar_idx, self.current_job_idx)
            
    def _retry_current_job(self):
        """Ripete il job corrente"""
        if self.worker and self.worker.is_running:
            self.log_message(f"Ripetizione job: Barra {self.current_bar_idx+1}, Pezzo {self.current_job_idx+1}")
            # Implementa logica di retry
            
    def _open_orders_manager(self):
        """Apre il gestore ordini"""
        # Implementa apertura dialog ordini
        self.show_toast("Gestore ordini non ancora implementato", "info")
        
    def _check_machine_ready(self) -> bool:
        """Verifica che la macchina sia pronta"""
        if not self.machine_state:
            QMessageBox.warning(self, "Attenzione", "Stato macchina non disponibile")
            return False
            
        if self.machine_state.emergency:
            QMessageBox.critical(self, "Errore", "Emergenza attiva! Ripristinare prima di procedere.")
            return False
            
        if not self.machine_state.homing_done:
            response = QMessageBox.question(
                self, 
                "Homing non eseguito",
                "L'homing non è stato eseguito. Vuoi eseguirlo ora?",
                QMessageBox.Yes | QMessageBox.No
            )
            if response == QMessageBox.Yes:
                # Esegui homing
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
        
        self.
