"""
Widget migliorato per la visualizzazione del piano di taglio con gestione 
corretta del collasso delle barre e visibilità degli elementi tagliati
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QFrame
from PySide6.QtCore import Qt, Signal, QTimer, QPropertyAnimation, QRect, QEasingCurve
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QFont

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
