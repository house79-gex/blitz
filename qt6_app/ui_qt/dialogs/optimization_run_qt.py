"""
Dialog per l'esecuzione dell'ottimizzazione del piano di taglio
File: qt6_app/ui_qt/dialogs/optimization_run_qt.py
Date: 2025-11-20
Author: house79-gex
"""

import json
import logging
import time
from datetime import datetime
from typing import Optional, Dict, List, Any

from PySide6.QtWidgets import (
    QDialog,           # Per la classe base del dialog
    QWidget,           # QUESTO È QUELLO CHE MANCA!
    QVBoxLayout,       # Layout verticale
    QHBoxLayout,       # Layout orizzontale
    QLabel,            # Etichette
    QPushButton,       # Pulsanti
    QGroupBox,         # Gruppi
    QSpinBox,          # SpinBox per interi
    QDoubleSpinBox,    # SpinBox per decimali
    QComboBox,         # ComboBox
    QCheckBox,         # CheckBox
    QTextEdit,         # Area di testo
    QTableWidget,      # Tabella
    QTableWidgetItem,  # Elementi tabella
    QHeaderView,       # Header tabella
    QSplitter,         # Splitter
    QFrame,            # Frame
    QProgressBar,      # Barra di progresso
    QTabWidget,        # Tab widget
    QListWidget,       # Lista widget
    QMessageBox,       # Message box
    QFileDialog,       # File dialog
    QGridLayout,       # Grid layout
    QScrollArea,       # Area scroll
    QDialogButtonBox,  # Button box
    QListWidgetItem,   # Item lista
    QStackedWidget     # Stacked widget
)
from PySide6.QtCore import (
    Qt,                # Costanti Qt
    QTimer,            # Timer
    Signal,            # Segnali
    Slot,              # Slot
    QThread,           # Thread
    QObject            # Object base
)

from PySide6.QtGui import (
    QFont,             # Font
    QColor,            # Colori
    QPalette,          # Palette
    QIcon              # Icone
)


# Import locali
from ..widgets.plan_visualizer import PlanVisualizer
from ..logic.planner import plan_ilp, plan_bfd
from ..logic.refiner import refine_plan
from ..logic.sequencer import Sequencer
from ..services.orders_store import OrdersStore
from ..utils.settings import load_settings, save_settings

logger = logging.getLogger(__name__)


class OptimizationWorker(QObject):
    """Worker thread per l'esecuzione dell'ottimizzazione"""
    
    # Segnali
    progress = Signal(int)
    status = Signal(str)
    result = Signal(dict)
    error = Signal(str)
    log = Signal(str)
    
    def __init__(self, jobs: List[Dict], stock: List[Dict], settings: Dict):
        super().__init__()
        self.jobs = jobs
        self.stock = stock
        self.settings = settings
        self.is_running = False
        
    def run(self):
        """Esegue l'ottimizzazione"""
        self.is_running = True
        
        try:
            self.log.emit("Avvio ottimizzazione...")
            self.status.emit("Preparazione dati...")
            self.progress.emit(10)
            
            # Prepara i dati per l'ottimizzatore
            time.sleep(0.5)  # Simula preparazione
            
            self.status.emit("Esecuzione algoritmo di ottimizzazione...")
            self.progress.emit(30)
            
            # Esegui ottimizzazione
            solver = self.settings.get('solver', 'ILP')
            time_limit = self.settings.get('time_limit', 60)
            
            if solver == 'ILP':
                self.log.emit(f"Utilizzo solver ILP con timeout {time_limit}s")
                plan = plan_ilp(self.jobs, self.stock, time_limit)
            else:
                self.log.emit("Utilizzo algoritmo BFD")
                plan = plan_bfd(self.jobs, self.stock)
                
            self.progress.emit(60)
            
            if not plan:
                raise Exception("Ottimizzazione fallita: nessun piano generato")
                
            # Raffina il piano se richiesto
            if self.settings.get('enable_refining', True):
                self.status.emit("Raffinamento del piano...")
                self.log.emit("Applicazione raffinamenti...")
                
                kerf = self.settings.get('kerf', 3.0)
                ripasso = self.settings.get('ripasso', 5.0)
                recupero = self.settings.get('recupero', True)
                
                plan = refine_plan(plan, kerf, ripasso, recupero)
                self.progress.emit(80)
                
            # Sequenziamento se richiesto
            if self.settings.get('enable_sequencing', True):
                self.status.emit("Sequenziamento ottimale...")
                self.log.emit("Calcolo sequenza ottimale...")
                
                sequencer = Sequencer()
                plan = sequencer.sequence_plan(plan)
                self.progress.emit(90)
                
            # Calcola statistiche
            self.status.emit("Calcolo statistiche...")
            stats = self._calculate_stats(plan)
            plan['stats'] = stats
            
            self.log.emit(f"Ottimizzazione completata: {stats['total_bars']} barre, {stats['total_cuts']} tagli")
            self.progress.emit(100)
            
            # Risultato finale
            self.result.emit(plan)
            
        except Exception as e:
            logger.error(f"Errore nell'ottimizzazione: {e}")
            self.error.emit(str(e))
            
    def _calculate_stats(self, plan: Dict) -> Dict:
        """Calcola statistiche del piano"""
        bars = plan.get('bars', [])
        total_cuts = sum(len(bar.get('jobs', [])) for bar in bars)
        total_length = sum(
            sum(job.get('length', 0) for job in bar.get('jobs', []))
            for bar in bars
        )
        total_waste = sum(bar.get('waste', 0) for bar in bars)
        
        efficiency = 0
        if total_length + total_waste > 0:
            efficiency = (total_length / (total_length + total_waste)) * 100
            
        return {
            'total_bars': len(bars),
            'total_cuts': total_cuts,
            'total_length': total_length,
            'total_waste': total_waste,
            'efficiency': efficiency,
            'timestamp': datetime.now().isoformat()
        }
        
    def stop(self):
        """Ferma l'ottimizzazione"""
        self.is_running = False


class OptimizationDialog(QDialog):
    """Dialog per configurare ed eseguire l'ottimizzazione"""
    
    def __init__(self, orders_store: OrdersStore = None, parent=None):
        super().__init__(parent)
        self.orders_store = orders_store or OrdersStore()
        self.optimized_plan = None
        self.worker = None
        self.worker_thread = None
        
        self.setWindowTitle("Ottimizzazione Piano di Taglio")
        self.setModal(True)
        self.resize(1000, 700)
        
        self._init_ui()
        self._load_settings()
        self._load_orders()
        
    def _init_ui(self):
        """Inizializza l'interfaccia utente"""
        layout = QVBoxLayout(self)
        
        # Stacked widget per le pagine
        self.stack = QStackedWidget()
        
        # Pagina 1: Selezione ordini e stock
        self.selection_page = self._create_selection_page()
        self.stack.addWidget(self.selection_page)
        
        # Pagina 2: Configurazione ottimizzazione
        self.config_page = self._create_config_page()
        self.stack.addWidget(self.config_page)
        
        # Pagina 3: Esecuzione e risultati
        self.results_page = self._create_results_page()
        self.stack.addWidget(self.results_page)
        
        layout.addWidget(self.stack)
        
        # Pulsanti di navigazione
        nav_layout = QHBoxLayout()
        
        self.btn_back = QPushButton("← Indietro")
        self.btn_back.clicked.connect(self._go_back)
        self.btn_back.setEnabled(False)
        nav_layout.addWidget(self.btn_back)
        
        nav_layout.addStretch()
        
        self.btn_cancel = QPushButton("Annulla")
        self.btn_cancel.clicked.connect(self.reject)
        nav_layout.addWidget(self.btn_cancel)
        
        self.btn_next = QPushButton("Avanti →")
        self.btn_next.clicked.connect(self._go_next)
        nav_layout.addWidget(self.btn_next)
        
        layout.addLayout(nav_layout)
        
    def _create_selection_page(self) -> QWidget:
        """Crea la pagina di selezione ordini e stock"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # Titolo
        title = QLabel("Selezione Ordini e Stock")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(title)
        
        # Splitter per ordini e stock
        splitter = QSplitter(Qt.Horizontal)
        
        # Pannello ordini
        orders_group = QGroupBox("Ordini da Ottimizzare")
        orders_layout = QVBoxLayout()
        
        # Lista ordini
        self.orders_list = QListWidget()
        self.orders_list.setSelectionMode(QListWidget.MultiSelection)
        orders_layout.addWidget(self.orders_list)
        
        # Pulsanti ordini
        orders_btn_layout = QHBoxLayout()
        
        self.btn_select_all = QPushButton("Seleziona Tutti")
        self.btn_select_all.clicked.connect(self._select_all_orders)
        orders_btn_layout.addWidget(self.btn_select_all)
        
        self.btn_deselect_all = QPushButton("Deseleziona Tutti")
        self.btn_deselect_all.clicked.connect(self._deselect_all_orders)
        orders_btn_layout.addWidget(self.btn_deselect_all)
        
        orders_layout.addLayout(orders_btn_layout)
        
        # Info ordini selezionati
        self.orders_info = QLabel("0 ordini selezionati")
        orders_layout.addWidget(self.orders_info)
        
        orders_group.setLayout(orders_layout)
        splitter.addWidget(orders_group)
        
        # Pannello stock
        stock_group = QGroupBox("Stock Disponibile")
        stock_layout = QVBoxLayout()
        
        # Tabella stock
        self.stock_table = QTableWidget()
        self.stock_table.setColumnCount(4)
        self.stock_table.setHorizontalHeaderLabels(["ID", "Lunghezza", "Quantità", "Usa"])
        self.stock_table.horizontalHeader().setStretchLastSection(True)
        stock_layout.addWidget(self.stock_table)
        
        # Aggiungi stock standard
        self._add_standard_stock()
        
        # Pulsanti stock
        stock_btn_layout = QHBoxLayout()
        
        self.btn_add_stock = QPushButton("+ Aggiungi")
        self.btn_add_stock.clicked.connect(self._add_stock_row)
        stock_btn_layout.addWidget(self.btn_add_stock)
        
        self.btn_remove_stock = QPushButton("- Rimuovi")
        self.btn_remove_stock.clicked.connect(self._remove_stock_row)
        stock_btn_layout.addWidget(self.btn_remove_stock)
        
        stock_layout.addLayout(stock_btn_layout)
        
        stock_group.setLayout(stock_layout)
        splitter.addWidget(stock_group)
        
        layout.addWidget(splitter)
        
        return page
        
    def _create_config_page(self) -> QWidget:
        """Crea la pagina di configurazione ottimizzazione"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # Titolo
        title = QLabel("Configurazione Ottimizzazione")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(title)
        
        # Gruppo algoritmo
        algo_group = QGroupBox("Algoritmo di Ottimizzazione")
        algo_layout = QGridLayout()
        
        algo_layout.addWidget(QLabel("Solver:"), 0, 0)
        self.solver_combo = QComboBox()
        self.solver_combo.addItems(["ILP (OR-Tools)", "BFD (Best Fit Decreasing)"])
        algo_layout.addWidget(self.solver_combo, 0, 1)
        
        algo_layout.addWidget(QLabel("Timeout (s):"), 1, 0)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(10, 300)
        self.timeout_spin.setValue(60)
        self.timeout_spin.setSuffix(" s")
        algo_layout.addWidget(self.timeout_spin, 1, 1)
        
        algo_group.setLayout(algo_layout)
        layout.addWidget(algo_group)
        
        # Gruppo parametri taglio
        params_group = QGroupBox("Parametri di Taglio")
        params_layout = QGridLayout()
        
        params_layout.addWidget(QLabel("Kerf (mm):"), 0, 0)
        self.kerf_spin = QDoubleSpinBox()
        self.kerf_spin.setRange(0.0, 10.0)
        self.kerf_spin.setValue(3.0)
        self.kerf_spin.setSingleStep(0.1)
        params_layout.addWidget(self.kerf_spin, 0, 1)
        
        params_layout.addWidget(QLabel("Ripasso (mm):"), 1, 0)
        self.ripasso_spin = QDoubleSpinBox()
        self.ripasso_spin.setRange(0.0, 50.0)
        self.ripasso_spin.setValue(5.0)
        params_layout.addWidget(self.ripasso_spin, 1, 1)
        
        params_layout.addWidget(QLabel("Tolleranza (mm):"), 2, 0)
        self.tolerance_spin = QDoubleSpinBox()
        self.tolerance_spin.setRange(0.0, 5.0)
        self.tolerance_spin.setValue(0.5)
        self.tolerance_spin.setSingleStep(0.1)
        params_layout.addWidget(self.tolerance_spin, 2, 1)
        
        params_group.setLayout(params_layout)
        layout.addWidget(params_group)
        
        # Gruppo opzioni
        options_group = QGroupBox("Opzioni")
        options_layout = QVBoxLayout()
        
        self.enable_refining_check = QCheckBox("Abilita raffinamento del piano")
        self.enable_refining_check.setChecked(True)
        options_layout.addWidget(self.enable_refining_check)
        
        self.enable_sequencing_check = QCheckBox("Ottimizza sequenza di taglio")
        self.enable_sequencing_check.setChecked(True)
        options_layout.addWidget(self.enable_sequencing_check)
        
        self.recupero_check = QCheckBox("Abilita recupero sfridi")
        self.recupero_check.setChecked(True)
        options_layout.addWidget(self.recupero_check)
        
        self.group_by_angle_check = QCheckBox("Raggruppa per angolo")
        self.group_by_angle_check.setChecked(False)
        options_layout.addWidget(self.group_by_angle_check)
        
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)
        
        layout.addStretch()
        
        return page
        
    def _create_results_page(self) -> QWidget:
        """Crea la pagina dei risultati"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # Titolo
        title = QLabel("Risultati Ottimizzazione")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(title)
        
        # Tab widget per risultati
        self.results_tabs = QTabWidget()
        
        # Tab visualizzazione piano
        viz_tab = QWidget()
        viz_layout = QVBoxLayout(viz_tab)
        
        # Visualizzatore piano
        self.plan_visualizer = PlanVisualizer()
        viz_layout.addWidget(self.plan_visualizer)
        
        self.results_tabs.addTab(viz_tab, "Visualizzazione Piano")
        
        # Tab statistiche
        stats_tab = QWidget()
        stats_layout = QVBoxLayout(stats_tab)
        
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        stats_layout.addWidget(self.stats_text)
        
        self.results_tabs.addTab(stats_tab, "Statistiche")
        
        # Tab log
        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self.log_text)
        
        self.results_tabs.addTab(log_tab, "Log")
        
        layout.addWidget(self.results_tabs)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Status
        self.status_label = QLabel("Pronto")
        layout.addWidget(self.status_label)
        
        # Pulsanti azione
        action_layout = QHBoxLayout()
        
        self.btn_save_plan = QPushButton("💾 Salva Piano")
        self.btn_save_plan.clicked.connect(self._save_plan)
        self.btn_save_plan.setEnabled(False)
        action_layout.addWidget(self.btn_save_plan)
        
        self.btn_export = QPushButton("📤 Esporta")
        self.btn_export.clicked.connect(self._export_plan)
        self.btn_export.setEnabled(False)
        action_layout.addWidget(self.btn_export)
        
        action_layout.addStretch()
        
        self.btn_run = QPushButton("▶ Esegui Ottimizzazione")
        self.btn_run.clicked.connect(self._run_optimization)
        self.btn_run.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        action_layout.addWidget(self.btn_run)
        
        layout.addLayout(action_layout)
        
        return page
        
    def _go_next(self):
        """Vai alla pagina successiva"""
        current = self.stack.currentIndex()
        
        if current == 0:  # Da selezione a configurazione
            # Verifica selezione
            if not self._get_selected_orders():
                QMessageBox.warning(self, "Attenzione", "Seleziona almeno un ordine")
                return
            if not self._get_stock():
                QMessageBox.warning(self, "Attenzione", "Definisci almeno una barra di stock")
                return
                
        if current < self.stack.count() - 1:
            self.stack.setCurrentIndex(current + 1)
            self.btn_back.setEnabled(True)
            
            if current == 1:  # Arrivati ai risultati
                self.btn_next.setText("Usa Piano")
                self.btn_next.clicked.disconnect()
                self.btn_next.clicked.connect(self.accept)
                self.btn_next.setEnabled(False)
                
    def _go_back(self):
        """Vai alla pagina precedente"""
        current = self.stack.currentIndex()
        if current > 0:
            self.stack.setCurrentIndex(current - 1)
            
            if current == 2:  # Torniamo dalla pagina risultati
                self.btn_next.setText("Avanti →")
                self.btn_next.clicked.disconnect()
                self.btn_next.clicked.connect(self._go_next)
                self.btn_next.setEnabled(True)
                
        if self.stack.currentIndex() == 0:
            self.btn_back.setEnabled(False)
            
    def _load_orders(self):
        """Carica gli ordini disponibili"""
        try:
            orders = self.orders_store.get_all_orders()
            self.orders_list.clear()
            
            for order in orders:
                item_text = f"Ordine #{order.get('id', '')} - {order.get('description', '')} ({order.get('pieces', 0)} pz)"
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, order)
                self.orders_list.addItem(item)
                
        except Exception as e:
            logger.error(f"Errore nel caricamento ordini: {e}")
            
    def _add_standard_stock(self):
        """Aggiunge stock standard"""
        standard_bars = [
            {"id": "STD-6000", "length": 6000, "quantity": 100},
            {"id": "STD-7000", "length": 7000, "quantity": 50},
        ]
        
        for bar in standard_bars:
            self._add_stock_row(bar)
            
    def _add_stock_row(self, data: Dict = None):
        """Aggiunge una riga alla tabella stock"""
        row = self.stock_table.rowCount()
        self.stock_table.insertRow(row)
        
        if data:
            self.stock_table.setItem(row, 0, QTableWidgetItem(data.get('id', f'BAR-{row+1}')))
            self.stock_table.setItem(row, 1, QTableWidgetItem(str(data.get('length', 6000))))
            self.stock_table.setItem(row, 2, QTableWidgetItem(str(data.get('quantity', 1))))
        else:
            self.stock_table.setItem(row, 0, QTableWidgetItem(f'BAR-{row+1}'))
            self.stock_table.setItem(row, 1, QTableWidgetItem("6000"))
            self.stock_table.setItem(row, 2, QTableWidgetItem("1"))
            
        # Checkbox per uso
        check = QCheckBox()
        check.setChecked(True)
        self.stock_table.setCellWidget(row, 3, check)
        
    def _remove_stock_row(self):
        """Rimuove la riga selezionata dalla tabella stock"""
        current_row = self.stock_table.currentRow()
        if current_row >= 0:
            self.stock_table.removeRow(current_row)
            
    def _select_all_orders(self):
        """Seleziona tutti gli ordini"""
        for i in range(self.orders_list.count()):
            self.orders_list.item(i).setSelected(True)
        self._update_orders_info()
        
    def _deselect_all_orders(self):
        """Deseleziona tutti gli ordini"""
        self.orders_list.clearSelection()
        self._update_orders_info()
        
    def _update_orders_info(self):
        """Aggiorna info ordini selezionati"""
        selected = len(self.orders_list.selectedItems())
        total_pieces = sum(
            item.data(Qt.UserRole).get('pieces', 0)
            for item in self.orders_list.selectedItems()
        )
        self.orders_info.setText(f"{selected} ordini selezionati ({total_pieces} pezzi totali)")
        
    def _get_selected_orders(self) -> List[Dict]:
        """Ottiene gli ordini selezionati"""
        orders = []
        for item in self.orders_list.selectedItems():
            order_data = item.data(Qt.UserRole)
            if order_data:
                orders.append(order_data)
        return orders
        
    def _get_stock(self) -> List[Dict]:
        """Ottiene lo stock definito"""
        stock = []
        for row in range(self.stock_table.rowCount()):
            check_widget = self.stock_table.cellWidget(row, 3)
            if check_widget and check_widget.isChecked():
                stock_item = {
                    'id': self.stock_table.item(row, 0).text(),
                    'length': float(self.stock_table.item(row, 1).text()),
                    'quantity': int(self.stock_table.item(row, 2).text())
                }
                stock.append(stock_item)
        return stock
        
    def _run_optimization(self):
        """Esegue l'ottimizzazione"""
        # Prepara i dati
        orders = self._get_selected_orders()
        stock = self._get_stock()
        
        # Converti ordini in jobs
        jobs = []
        for order in orders:
            # TODO: Convertire ordine in lista di tagli
            # Per ora usiamo dati di esempio
            for i in range(order.get('pieces', 1)):
                jobs.append({
                    'id': f"{order['id']}-{i+1}",
                    'length': 1500,  # Esempio
                    'angle_sx': 90,
                    'angle_dx': 90,
                    'order_id': order['id']
                })
                
        settings = {
            'solver': 'ILP' if self.solver_combo.currentIndex() == 0 else 'BFD',
            'time_limit': self.timeout_spin.value(),
            'kerf': self.kerf_spin.value(),
            'ripasso': self.ripasso_spin.value(),
            'recupero': self.recupero_check.isChecked(),
            'enable_refining': self.enable_refining_check.isChecked(),
            'enable_sequencing': self.enable_sequencing_check.isChecked()
        }
        
        # UI per esecuzione
        self.btn_run.setEnabled(False)
        self.btn_save_plan.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # Avvia worker
        self._start_worker(jobs, stock, settings)
        
    def _start_worker(self, jobs: List[Dict], stock: List[Dict], settings: Dict):
        """Avvia il worker thread per l'ottimizzazione"""
        if self.worker_thread:
            self._cleanup_worker()
            
        self.worker = OptimizationWorker(jobs, stock, settings)
        self.worker_thread = QThread()
        
        # Connetti segnali
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.status.connect(self.status_label.setText)
        self.worker.log.connect(self._add_log)
        self.worker.result.connect(self._on_optimization_complete)
        self.worker.error.connect(self._on_optimization_error)
        
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
        
    def _add_log(self, message: str):
        """Aggiunge un messaggio al log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        
    @Slot(dict)
    def _on_optimization_complete(self, plan: Dict):
        """Gestisce il completamento dell'ottimizzazione"""
        self.optimized_plan = plan
        
        # Mostra risultati
        self.plan_visualizer.load_plan(plan)
        
        # Mostra statistiche
        stats = plan.get('stats', {})
        stats_text = f"""
        === STATISTICHE OTTIMIZZAZIONE ===
        
        Barre utilizzate: {stats.get('total_bars', 0)}
        Tagli totali: {stats.get('total_cuts', 0)}
        Lunghezza totale tagliata: {stats.get('total_length', 0):.1f} mm
        Sfrido totale: {stats.get('total_waste', 0):.1f} mm
        Efficienza: {stats.get('efficiency', 0):.1f}%
        
        Timestamp: {stats.get('timestamp', '')}
        """
        self.stats_text.setText(stats_text)
        
        # Abilita pulsanti
        self.btn_run.setEnabled(True)
        self.btn_save_plan.setEnabled(True)
        self.btn_export.setEnabled(True)
        self.btn_next.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        self.status_label.setText("Ottimizzazione completata con successo")
        self._add_log("Ottimizzazione completata!")
        
        # Cleanup
        self._cleanup_worker()
        
    @Slot(str)
    def _on_optimization_error(self, error_msg: str):
        """Gestisce gli errori di ottimizzazione"""
        QMessageBox.critical(self, "Errore", f"Errore durante l'ottimizzazione:\n{error_msg}")
        
        self.btn_run.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Errore nell'ottimizzazione")
        
        self._add_log(f"ERRORE: {error_msg}")
        self._cleanup_worker()
        
    def _save_plan(self):
        """Salva il piano ottimizzato"""
        if not self.optimized_plan:
            return
            
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Salva Piano Ottimizzato",
            f"piano_ottimizzato_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "File JSON (*.json)"
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(self.optimized_plan, f, indent=2, ensure_ascii=False)
                QMessageBox.information(self, "Successo", "Piano salvato con successo")
            except Exception as e:
                QMessageBox.critical(self, "Errore", f"Errore nel salvataggio:\n{str(e)}")
                
    def _export_plan(self):
        """Esporta il piano in altri formati"""
        # TODO: Implementare export in CSV, Excel, etc.
        QMessageBox.information(self, "Info", "Funzionalità di export non ancora implementata")
        
    def _load_settings(self):
        """Carica le impostazioni salvate"""
        settings = load_settings()
        opt_settings = settings.get('optimization', {})
        
        # Applica impostazioni
        self.solver_combo.setCurrentIndex(0 if opt_settings.get('solver', 'ILP') == 'ILP' else 1)
        self.timeout_spin.setValue(opt_settings.get('timeout', 60))
        self.kerf_spin.setValue(opt_settings.get('kerf', 3.0))
        self.ripasso_spin.setValue(opt_settings.get('ripasso', 5.0))
        self.tolerance_spin.setValue(opt_settings.get('tolerance', 0.5))
        self.enable_refining_check.setChecked(opt_settings.get('enable_refining', True))
        self.enable_sequencing_check.setChecked(opt_settings.get('enable_sequencing', True))
        self.recupero_check.setChecked(opt_settings.get('recupero', True))
        self.group_by_angle_check.setChecked(opt_settings.get('group_by_angle', False))
        
    def save_settings(self):
        """Salva le impostazioni correnti"""
        settings = load_settings()
        
        settings['optimization'] = {
            'solver': 'ILP' if self.solver_combo.currentIndex() == 0 else 'BFD',
            'timeout': self.timeout_spin.value(),
            'kerf': self.kerf_spin.value(),
            'ripasso': self.ripasso_spin.value(),
            'tolerance': self.tolerance_spin.value(),
            'enable_refining': self.enable_refining_check.isChecked(),
            'enable_sequencing': self.enable_sequencing_check.isChecked(),
            'recupero': self.recupero_check.isChecked(),
            'group_by_angle': self.group_by_angle_check.isChecked()
        }
        
        save_settings(settings)
        
    def get_optimized_plan(self) -> Optional[Dict]:
        """Restituisce il piano ottimizzato"""
        return self.optimized_plan
        
    def closeEvent(self, event):
        """Gestisce la chiusura del dialog"""
        self.save_settings()
        self._cleanup_worker()
        event.accept()
