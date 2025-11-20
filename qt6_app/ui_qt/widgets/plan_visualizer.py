"""
Widget per la visualizzazione del piano di taglio con gestione avanzata
File: qt6_app/ui_qt/widgets/plan_visualizer.py
Date: 2025-11-20
Author: house79-gex
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, 
    QScrollArea, QPushButton, QSizePolicy
)
from PySide6.QtCore import (
    Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve, 
    QRect, Property, QSize
)
from PySide6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QLinearGradient,
    QFontMetrics
)

import logging

logger = logging.getLogger(__name__)


class PlanVisualizer(QWidget):
    """Widget per visualizzare il piano di taglio con animazioni migliorate"""
    
    bar_selected = Signal(int)  # Emesso quando si seleziona una barra
    job_selected = Signal(int, int)  # Emesso quando si seleziona un job (bar_idx, job_idx)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.plan = None
        self.current_bar_idx = -1
        self.current_job_idx = -1
        self.completed_bars = set()
        self.collapsing_bars = set()
        self.collapse_timers = {}
        
        # Configurazione visualizzazione
        self.bar_height = 80
        self.collapsed_bar_height = 25
        self.job_padding = 2
        self.bar_margin = 10
        self.collapse_delay_ms = 500
        self.min_width = 800
        
        self._setup_ui()
        
    def _setup_ui(self):
        """Setup dell'interfaccia utente"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header con controlli
        header = self._create_header()
        layout.addWidget(header)
        
        # Area scroll per le barre
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid #ccc;
                background-color: #f5f5f5;
            }
        """)
        
        # Container per le barre
        self.bars_container = QWidget()
        self.bars_container.setMinimumWidth(self.min_width)
        self.bars_layout = QVBoxLayout(self.bars_container)
        self.bars_layout.setSpacing(5)
        self.bars_layout.setContentsMargins(10, 10, 10, 10)
        
        self.scroll.setWidget(self.bars_container)
        layout.addWidget(self.scroll)
        
        # Footer con statistiche
        self.footer = self._create_footer()
        layout.addWidget(self.footer)
        
    def _create_header(self) -> QWidget:
        """Crea l'header con i controlli"""
        header = QFrame()
        header.setFrameStyle(QFrame.Box)
        header.setMaximumHeight(40)
        
        layout = QHBoxLayout(header)
        layout.setContentsMargins(10, 5, 10, 5)
        
        # Titolo
        self.title_label = QLabel("Piano di Taglio")
        self.title_label.setFont(QFont("Arial", 10, QFont.Bold))
        layout.addWidget(self.title_label)
        
        layout.addStretch()
        
        # Pulsanti controllo
        self.btn_expand_all = QPushButton("📂 Espandi Tutto")
        self.btn_expand_all.clicked.connect(self._expand_all)
        layout.addWidget(self.btn_expand_all)
        
        self.btn_collapse_all = QPushButton("📁 Comprimi Tutto")
        self.btn_collapse_all.clicked.connect(self._collapse_all)
        layout.addWidget(self.btn_collapse_all)
        
        return header
        
    def _create_footer(self) -> QWidget:
        """Crea il footer con le statistiche"""
        footer = QFrame()
        footer.setFrameStyle(QFrame.Box)
        footer.setMaximumHeight(30)
        
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(10, 2, 10, 2)
        
        # Statistiche
        self.stats_label = QLabel("Nessun piano caricato")
        self.stats_label.setFont(QFont("Arial", 9))
        layout.addWidget(self.stats_label)
        
        layout.addStretch()
        
        # Progresso
        self.progress_label = QLabel("0/0")
        self.progress_label.setFont(QFont("Arial", 9, QFont.Bold))
        layout.addWidget(self.progress_label)
        
        return footer
        
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
        self._update_stats()
        
    def _rebuild_display(self):
        """Ricostruisce la visualizzazione del piano"""
        # Pulisci layout esistente
        while self.bars_layout.count():
            item = self.bars_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        if not self.plan or 'bars' not in self.plan:
            self.stats_label.setText("Nessun piano caricato")
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
        bar_frame.job_clicked.connect(self.job_selected.emit)
        
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
        self._update_stats()
        
    def _handle_bar_completion(self, bar_idx):
        """Gestisce il completamento di una barra con ritardo nel collasso"""
        if bar_idx not in self.completed_bars:
            self.completed_bars.add(bar_idx)
            
            # Crea timer per ritardare il collasso
            if bar_idx not in self.collapse_timers:
                timer = QTimer()
                timer.setSingleShot(True)
                timer.timeout.connect(lambda idx=bar_idx: self._collapse_bar(idx))
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
            return
            
        if bar_idx not in self.collapsing_bars:
            self.collapsing_bars.add(bar_idx)
            
            for i in range(self.bars_layout.count()):
                widget = self.bars_layout.itemAt(i).widget()
                if hasattr(widget, 'bar_idx') and widget.bar_idx == bar_idx:
                    if hasattr(widget, 'animate_collapse'):
                        widget.animate_collapse()
                    break
            
    def _update_bars_display(self):
        """Aggiorna la visualizzazione di tutte le barre"""
        for i in range(self.bars_layout.count()):
            widget = self.bars_layout.itemAt(i).widget()
            if isinstance(widget, BarFrame):
                widget.set_active(False)
                
                if widget.bar_idx == self.current_bar_idx:
                    widget.set_active(True)
                    widget.set_current_job(self.current_job_idx)
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
        self._update_stats()
                
    def reset(self):
        """Reset completo del visualizzatore"""
        self.current_bar_idx = -1
        self.current_job_idx = -1
        self.completed_bars.clear()
        self.collapsing_bars.clear()
        
        for timer in self.collapse_timers.values():
            timer.stop()
        self.collapse_timers.clear()
        
        if self.plan:
            self._rebuild_display()
            self._update_stats()
            
    def _expand_all(self):
        """Espande tutte le barre"""
        for i in range(self.bars_layout.count()):
            widget = self.bars_layout.itemAt(i).widget()
            if isinstance(widget, BarFrame):
                widget.expand()
                
    def _collapse_all(self):
        """Collassa tutte le barre completate"""
        for i in range(self.bars_layout.count()):
            widget = self.bars_layout.itemAt(i).widget()
            if isinstance(widget, BarFrame):
                if widget.bar_idx != self.current_bar_idx and widget.is_completed:
                    widget.set_collapsed(True)
                    
    def _update_stats(self):
        """Aggiorna le statistiche"""
        if not self.plan:
            return
            
        bars = self.plan.get('bars', [])
        total_bars = len(bars)
        completed_bars = len(self.completed_bars)
        
        total_jobs = sum(len(bar.get('jobs', [])) for bar in bars)
        completed_jobs = 0
        
        for i in range(self.bars_layout.count()):
            widget = self.bars_layout.itemAt(i).widget()
            if isinstance(widget, BarFrame):
                completed_jobs += len(widget.completed_jobs)
                
        self.stats_label.setText(
            f"Barre: {completed_bars}/{total_bars} | "
            f"Tagli: {completed_jobs}/{total_jobs}"
        )
        
        # Calcola efficienza
        if total_jobs > 0:
            progress = int((completed_jobs / total_jobs) * 100)
            self.progress_label.setText(f"Progresso: {progress}%")
        else:
            self.progress_label.setText("0%")


class BarFrame(QFrame):
    """Frame per una singola barra con supporto per animazioni"""
    
    clicked = Signal(int)
    job_clicked = Signal(int, int)  # bar_idx, job_idx
    
    # Property per l'animazione
    def get_animation_height(self):
        return self.maximumHeight()
    
    def set_animation_height(self, height):
        self.setMaximumHeight(height)
        self.setMinimumHeight(min(height, self.expanded_height))
        
    animation_height = Property(int, get_animation_height, set_animation_height)
    
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
        self.expanded_height = 80
        self.collapsed_height = 25
        
        self.setFrameStyle(QFrame.Box)
        self.setMaximumHeight(self.expanded_height)
        self.setMinimumHeight(self.expanded_height)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        self._setup_ui()
        self._apply_default_style()
        
    def _setup_ui(self):
        """Setup dell'interfaccia della barra"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)
        
        # Header con info barra
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # Indicatore stato
        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: gray; font-size: 16px;")
        header_layout.addWidget(self.status_indicator)
        
        # Info barra
        bar_length = self.bar_data.get('length', 0)
        bar_waste = self.bar_data.get('waste', 0)
        
        info_text = f"Barra #{self.bar_idx + 1} - {bar_length:.1f}mm"
        if bar_waste > 0:
            info_text += f" (Sfrido: {bar_waste:.1f}mm)"
            
        self.info_label = QLabel(info_text)
        self.info_label.setFont(QFont("Arial", 9))
        header_layout.addWidget(self.info_label)
        
        # Jobs completati
        self.progress_label = QLabel()
        self._update_progress_label()
        header_layout.addWidget(self.progress_label)
        
        header_layout.addStretch()
        
        # Pulsante espandi/comprimi
        self.toggle_btn = QPushButton("▼")
        self.toggle_btn.setMaximumSize(20, 20)
        self.toggle_btn.clicked.connect(self._toggle_collapsed)
        header_layout.addWidget(self.toggle_btn)
        
        layout.addWidget(header_widget)
        
        # Widget per visualizzare i jobs
        self.jobs_widget = JobsWidget(self.bar_data.get('jobs', []), self.bar_idx)
        self.jobs_widget.job_clicked.connect(self.job_clicked.emit)
        layout.addWidget(self.jobs_widget)
        
    def _apply_default_style(self):
        """Applica lo stile di default"""
        self.setStyleSheet("""
            BarFrame {
                border: 1px solid #ddd;
                background-color: white;
                border-radius: 5px;
            }
            BarFrame:hover {
                border: 1px solid #999;
            }
        """)
        
    def _update_progress_label(self):
        """Aggiorna l'etichetta del progresso"""
        total_jobs = len(self.bar_data.get('jobs', []))
        completed = len(self.completed_jobs)
        
        self.progress_label.setText(f"({completed}/{total_jobs})")
        
        # Colore basato sul progresso
        if completed == 0:
            color = "#666"
        elif completed == total_jobs:
            color = "green"
        else:
            color = "orange"
            
        self.progress_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        
    def set_active(self, active):
        """Imposta lo stato attivo della barra"""
        self.is_active = active
        if active:
            self.status_indicator.setStyleSheet("color: orange; font-size: 16px;")
            self.setStyleSheet("""
                BarFrame {
                    border: 2px solid orange;
                    background-color: rgba(255, 165, 0, 20);
                    border-radius: 5px;
                }
            """)
            # Non collassare mai la barra attiva
            if self.is_collapsed:
                self.expand()
        else:
            self._update_status_indicator()
            self._apply_default_style()
            
    def set_completed(self, completed):
        """Imposta lo stato completato della barra"""
        self.is_completed = completed
        self._update_status_indicator()
        
        if completed:
            self.setStyleSheet("""
                BarFrame {
                    border: 1px solid #90EE90;
                    background-color: rgba(144, 238, 144, 20);
                    border-radius: 5px;
                }
            """)
            
    def set_collapsed(self, collapsed):
        """Imposta lo stato collassato della barra"""
        if collapsed and not self.is_active:
            self.is_collapsed = True
            self.jobs_widget.setVisible(False)
            self.setMaximumHeight(self.collapsed_height)
            self.setMinimumHeight(self.collapsed_height)
            self.toggle_btn.setText("▶")
        else:
            self.expand()
            
    def expand(self):
        """Espande la barra"""
        self.is_collapsed = False
        self.jobs_widget.setVisible(True)
        self.setMaximumHeight(self.expanded_height)
        self.setMinimumHeight(self.expanded_height)
        self.toggle_btn.setText("▼")
        
    def _toggle_collapsed(self):
        """Toggle dello stato collassato"""
        if self.is_collapsed:
            self.expand()
        else:
            self.set_collapsed(True)
            
    def _update_status_indicator(self):
        """Aggiorna l'indicatore di stato"""
        if self.is_completed:
            self.status_indicator.setStyleSheet("color: green; font-size: 16px;")
        elif self.is_active:
            self.status_indicator.setStyleSheet("color: orange; font-size: 16px;")
        else:
            self.status_indicator.setStyleSheet("color: gray; font-size: 16px;")
            
    def set_current_job(self, job_idx):
        """Imposta il job corrente"""
        self.current_job_idx = job_idx
        self.jobs_widget.set_current_job(job_idx)
        
    def mark_job_completed(self, job_idx):
        """Marca un job come completato"""
        self.completed_jobs.add(job_idx)
        self.jobs_widget.mark_job_completed(job_idx)
        self._update_progress_label()
        
        # Se tutti i job sono completati, marca la barra come completata
        total_jobs = len(self.bar_data.get('jobs', []))
        if len(self.completed_jobs) >= total_jobs:
            self.set_completed(True)
            
    def animate_collapse(self):
        """Anima il collasso della barra"""
        if not self.is_active:
            self.animation = QPropertyAnimation(self, b"animation_height")
            self.animation.setDuration(300)
            self.animation.setStartValue(self.expanded_height)
            self.animation.setEndValue(self.collapsed_height)
            self.animation.setEasingCurve(QEasingCurve.InOutQuad)
            
            # Al completamento, nascondi i jobs
            self.animation.finished.connect(lambda: self.set_collapsed(True))
            self.animation.start()
            
    def mousePressEvent(self, event):
        """Gestisce il click sulla barra"""
        if event.button() == Qt.LeftButton:
            # Evita di emettere il segnale se si clicca sul toggle button
            if not self.toggle_btn.underMouse():
                self.clicked.emit(self.bar_idx)
        super().mousePressEvent(event)


class JobsWidget(QWidget):
    """Widget per visualizzare i jobs in una barra"""
    
    job_clicked = Signal(int, int)  # bar_idx, job_idx
    
    def __init__(self, jobs, bar_idx, parent=None):
        super().__init__(parent)
        self.jobs = jobs
        self.bar_idx = bar_idx
        self.current_job_idx = -1
        self.completed_jobs = set()
        self.setFixedHeight(35)
        self.setCursor(Qt.PointingHandCursor)
        
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
            
        x = 2
        for idx, job in enumerate(self.jobs):
            job_length = job.get('length', 0)
            job_width = max(20, int((job_length / total_length) * (width - 4)))
            
            # Rettangolo del job
            rect = QRect(x, 2, job_width - 2, height - 4)
            
            # Colore basato sullo stato con gradiente
            if idx in self.completed_jobs:
                # Verde per completato
                gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
                gradient.setColorAt(0, QColor(100, 220, 100))
                gradient.setColorAt(1, QColor(50, 180, 50))
                painter.setBrush(QBrush(gradient))
                painter.setPen(QPen(QColor(40, 140, 40), 1))
            elif idx == self.current_job_idx:
                # Arancione per corrente con pulsazione
                gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
                gradient.setColorAt(0, QColor(255, 200, 100))
                gradient.setColorAt(1, QColor(255, 140, 0))
                painter.setBrush(QBrush(gradient))
                painter.setPen(QPen(QColor(200, 100, 0), 2))
            else:
                # Grigio per pendente
                gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
                gradient.setColorAt(0, QColor(200, 200, 200))
                gradient.setColorAt(1, QColor(150, 150, 150))
                painter.setBrush(QBrush(gradient))
                painter.setPen(QPen(QColor(100, 100, 100), 1))
                
            # Disegna il rettangolo
            painter.drawRoundedRect(rect, 3, 3)
            
            # Disegna info job se c'è spazio
            if job_width > 40:
                painter.setPen(Qt.white if idx in self.completed_jobs or idx == self.current_job_idx else Qt.black)
                painter.setFont(QFont("Arial", 8, QFont.Bold))
                
                # Testo con lunghezza e angoli
                length_text = f"{job_length:.0f}"
                angle_sx = job.get('angle_sx', 90)
                angle_dx = job.get('angle_dx', 90)
                
                if angle_sx != 90 or angle_dx != 90:
                    angle_text = f"[{angle_sx}°/{angle_dx}°]"
                    if job_width > 80:
                        text = f"{length_text}\n{angle_text}"
                    else:
                        text = length_text
                else:
                    text = length_text
                    
                painter.drawText(rect, Qt.AlignCenter, text)
                
            # Indicatore di selezione per job corrente
            if idx == self.current_job_idx:
                painter.setPen(QPen(QColor(255, 100, 0), 3))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), 3, 3)
                
            x += job_width
            
    def set_current_job(self, job_idx):
        """Imposta il job corrente"""
        self.current_job_idx = job_idx
        self.update()
        
    def mark_job_completed(self, job_idx):
        """Marca un job come completato"""
        self.completed_jobs.add(job_idx)
        self.update()
        
    def mousePressEvent(self, event):
        """Gestisce il click su un job"""
        if event.button() == Qt.LeftButton and self.jobs:
            # Calcola quale job è stato cliccato
            x = event.pos().x()
            width = self.width()
            total_length = sum(job.get('length', 0) for job in self.jobs)
            
            if total_length > 0:
                current_x = 2
                for idx, job in enumerate(self.jobs):
                    job_length = job.get('length', 0)
                    job_width = max(20, int((job_length / total_length) * (width - 4)))
                    
                    if current_x <= x <= current_x + job_width:
                        self.job_clicked.emit(self.bar_idx, idx)
                        break
                        
                    current_x += job_width
                    
        super().mousePressEvent(event)


# Alias per compatibilità con vecchi import
PlanVisualizerWidget = PlanVisualizer
