"""
Cutlist Page - Standalone cutlist management with import/export and optimization
File: qt6_app/ui_qt/pages/cutlist_page.py
"""

from typing import Dict, Any, List, Optional
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSpinBox, QDoubleSpinBox, QMessageBox, QInputDialog,
    QGroupBox, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Signal

from ui_qt.widgets.header import Header
from ui_qt.widgets.cutlist_table_widget import CutlistTableWidget
from ui_qt.widgets.optimization_results_widget import OptimizationResultsWidget
from ui_qt.widgets.import_export_dialog import ImportExportDialog

from ui_qt.utils.cutlist_importer import CutlistImporter
from ui_qt.utils.cutlist_exporter import CutlistExporter
from ui_qt.utils.project_manager import ProjectManager


class CutlistPage(QWidget):
    """
    Cutlist Page - Standalone interface for managing cut lists.
    
    Features:
    - Import/export from multiple formats (CSV, Excel, TXT, JSON)
    - Manual editing with validation
    - Optimization integration
    - Project management (save/load)
    """
    
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        
        # Services
        self.importer = CutlistImporter()
        self.exporter = CutlistExporter()
        self.project_manager = ProjectManager()
        
        # Current state
        self.current_project_name = ""
        self.optimization_results = None
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        # Header
        layout.addWidget(Header(
            self.appwin,
            "📋 Cutlist Manager",
            mode="cutlist",
            show_home=True
        ))
        
        # Main content in scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(12)
        
        # Import section
        content_layout.addWidget(self._create_import_section())
        
        # Table section
        content_layout.addWidget(self._create_table_section())
        
        # Parameters section
        content_layout.addWidget(self._create_parameters_section())
        
        # Action buttons
        content_layout.addWidget(self._create_action_buttons())
        
        # Results section
        content_layout.addWidget(self._create_results_section())
        
        # Recent projects section
        content_layout.addWidget(self._create_recent_projects_section())
        
        scroll.setWidget(content)
        layout.addWidget(scroll)
    
    def _create_import_section(self) -> QWidget:
        """Create import buttons section."""
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QHBoxLayout(frame)
        
        label = QLabel("Importa:")
        label.setStyleSheet("font-weight: bold;")
        layout.addWidget(label)
        
        btn_csv = QPushButton("📂 CSV")
        btn_csv.clicked.connect(lambda: self._import_file('csv'))
        layout.addWidget(btn_csv)
        
        btn_excel = QPushButton("📊 Excel")
        btn_excel.clicked.connect(lambda: self._import_file('excel'))
        layout.addWidget(btn_excel)
        
        btn_txt = QPushButton("📄 TXT")
        btn_txt.clicked.connect(lambda: self._import_file('txt'))
        layout.addWidget(btn_txt)
        
        btn_json = QPushButton("📦 JSON")
        btn_json.clicked.connect(lambda: self._import_file('json'))
        layout.addWidget(btn_json)
        
        layout.addStretch()
        
        return frame
    
    def _create_table_section(self) -> QWidget:
        """Create table editor section."""
        group = QGroupBox("Lista Pezzi")
        layout = QVBoxLayout(group)
        
        # Table
        self.table_widget = CutlistTableWidget(self)
        self.table_widget.data_changed.connect(self._update_totals)
        layout.addWidget(self.table_widget)
        
        # Table controls
        controls_layout = QHBoxLayout()
        
        btn_add = QPushButton("+ Aggiungi Riga")
        btn_add.clicked.connect(self._add_row)
        controls_layout.addWidget(btn_add)
        
        btn_remove = QPushButton("− Rimuovi Selezionati")
        btn_remove.clicked.connect(self._remove_rows)
        controls_layout.addWidget(btn_remove)
        
        btn_duplicate = QPushButton("📋 Duplica")
        btn_duplicate.clicked.connect(self._duplicate_row)
        controls_layout.addWidget(btn_duplicate)
        
        btn_clear = QPushButton("🗑️ Cancella Tutto")
        btn_clear.clicked.connect(self._clear_all)
        controls_layout.addWidget(btn_clear)
        
        controls_layout.addStretch()
        
        layout.addLayout(controls_layout)
        
        # Totals display
        totals_frame = QFrame()
        totals_frame.setFrameShape(QFrame.Shape.StyledPanel)
        totals_frame.setStyleSheet("background-color: #e8f4f8; padding: 8px;")
        totals_layout = QHBoxLayout(totals_frame)
        
        self.label_totals = QLabel("Totale: 0 pezzi | 0.00 metri lineari")
        self.label_totals.setStyleSheet("font-weight: bold;")
        totals_layout.addWidget(self.label_totals)
        
        layout.addWidget(totals_frame)
        
        return group
    
    def _create_parameters_section(self) -> QWidget:
        """Create optimization parameters section."""
        group = QGroupBox("Parametri Ottimizzazione")
        layout = QHBoxLayout(group)
        
        # Stock length
        layout.addWidget(QLabel("Lunghezza stock:"))
        self.spin_stock_length = QDoubleSpinBox()
        self.spin_stock_length.setRange(100, 100000)
        self.spin_stock_length.setValue(6500)
        self.spin_stock_length.setSuffix(" mm")
        self.spin_stock_length.valueChanged.connect(self._on_stock_length_changed)
        layout.addWidget(self.spin_stock_length)
        
        layout.addSpacing(20)
        
        # Kerf
        layout.addWidget(QLabel("Kerf lama:"))
        self.spin_kerf = QDoubleSpinBox()
        self.spin_kerf.setRange(0, 50)
        self.spin_kerf.setValue(3)
        self.spin_kerf.setSuffix(" mm")
        layout.addWidget(self.spin_kerf)
        
        layout.addStretch()
        
        return group
    
    def _create_action_buttons(self) -> QWidget:
        """Create main action buttons."""
        frame = QFrame()
        layout = QHBoxLayout(frame)
        
        btn_optimize = QPushButton("⚙️ OTTIMIZZA")
        btn_optimize.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 10px 20px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        btn_optimize.clicked.connect(self._optimize)
        layout.addWidget(btn_optimize)
        
        btn_save_project = QPushButton("💾 Salva Progetto")
        btn_save_project.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 10px 20px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
        """)
        btn_save_project.clicked.connect(self._save_project)
        layout.addWidget(btn_save_project)
        
        layout.addStretch()
        
        return frame
    
    def _create_results_section(self) -> QWidget:
        """Create optimization results section."""
        self.results_widget = OptimizationResultsWidget(self)
        self.results_widget.export_pdf_clicked.connect(self._export_pdf)
        self.results_widget.export_excel_clicked.connect(self._export_excel)
        return self.results_widget
    
    def _create_recent_projects_section(self) -> QWidget:
        """Create recent projects section."""
        self.projects_group = QGroupBox("Progetti Recenti")
        self.projects_layout = QVBoxLayout(self.projects_group)
        
        self._refresh_recent_projects()
        
        return self.projects_group
    
    def _refresh_recent_projects(self):
        """Refresh recent projects list."""
        # Clear existing
        while self.projects_layout.count():
            item = self.projects_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Load recent projects
        projects = self.project_manager.list_recent_projects(limit=5)
        
        if not projects:
            label = QLabel("Nessun progetto salvato")
            label.setStyleSheet("font-style: italic; color: #666;")
            self.projects_layout.addWidget(label)
            return
        
        for project in projects:
            project_frame = self._create_project_item(project)
            self.projects_layout.addWidget(project_frame)
    
    def _create_project_item(self, project: Dict[str, Any]) -> QWidget:
        """Create a project list item."""
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QHBoxLayout(frame)
        
        # Project info
        info_layout = QVBoxLayout()
        
        name_label = QLabel(f"📁 {project['name']}")
        name_label.setStyleSheet("font-weight: bold;")
        info_layout.addWidget(name_label)
        
        details = f"{project['total_pieces']} pezzi | {project['total_length_m']:.2f}m"
        if project.get('modified_at'):
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(project['modified_at'])
                details += f" | {dt.strftime('%d/%m/%Y %H:%M')}"
            except:
                pass
        
        details_label = QLabel(details)
        details_label.setStyleSheet("font-size: 10px; color: #666;")
        info_layout.addWidget(details_label)
        
        layout.addLayout(info_layout, 1)
        
        # Load button
        btn_load = QPushButton("📂 Carica")
        btn_load.clicked.connect(lambda: self._load_project_by_filename(project['filename']))
        layout.addWidget(btn_load)
        
        # Delete button
        btn_delete = QPushButton("🗑️")
        btn_delete.clicked.connect(lambda: self._delete_project(project['filename']))
        layout.addWidget(btn_delete)
        
        return frame
    
    # --- Event handlers ---
    
    def _import_file(self, file_type: str = None):
        """Import cutlist from file."""
        try:
            result = ImportExportDialog.import_file(self)
            if not result:
                return
            
            filepath, detected_type = result
            if file_type is None:
                file_type = detected_type
            
            # Import based on type
            if file_type == 'csv':
                pieces = self.importer.from_csv(filepath)
                self.table_widget.load_cutlist(pieces)
                self.current_project_name = ""
                
            elif file_type == 'excel':
                pieces = self.importer.from_excel(filepath)
                self.table_widget.load_cutlist(pieces)
                self.current_project_name = ""
                
            elif file_type == 'txt':
                pieces = self.importer.from_txt(filepath)
                self.table_widget.load_cutlist(pieces)
                self.current_project_name = ""
                
            elif file_type == 'json':
                project = self.importer.from_json(filepath)
                self._load_project_data(project)
            
            ImportExportDialog.show_success(self, "Successo", "File importato con successo")
            
        except Exception as e:
            ImportExportDialog.show_error(self, "Errore Import", str(e))
    
    def _add_row(self):
        """Add a new row to the table."""
        self.table_widget.add_piece()
    
    def _remove_rows(self):
        """Remove selected rows."""
        self.table_widget.remove_selected_rows()
    
    def _duplicate_row(self):
        """Duplicate selected row."""
        self.table_widget.duplicate_selected_row()
    
    def _clear_all(self):
        """Clear all rows after confirmation."""
        if ImportExportDialog.confirm_action(
            self, 
            "Conferma", 
            "Sei sicuro di voler cancellare tutti i dati?"
        ):
            self.table_widget.clear_all()
            self.results_widget.clear_results()
            self.current_project_name = ""
    
    def _update_totals(self):
        """Update totals display."""
        totals = self.table_widget.get_totals()
        self.label_totals.setText(
            f"Totale: {totals['total_pieces']} pezzi | "
            f"{totals['total_length_m']:.2f} metri lineari"
        )
    
    def _on_stock_length_changed(self, value):
        """Handle stock length change."""
        self.table_widget.set_stock_length(value)
    
    def _optimize(self):
        """Run optimization on current cutlist."""
        try:
            # Validate cutlist
            is_valid, errors = self.table_widget.validate()
            if not is_valid:
                error_msg = "Errori di validazione:\n\n" + "\n".join(errors)
                ImportExportDialog.show_error(self, "Validazione Fallita", error_msg)
                return
            
            # Get cutlist
            pieces = self.table_widget.get_cutlist()
            if not pieces:
                ImportExportDialog.show_error(self, "Errore", "Lista vuota - aggiungi almeno un pezzo")
                return
            
            # Get parameters
            stock_length = self.spin_stock_length.value()
            kerf = self.spin_kerf.value()
            
            # Run optimization
            results = self._run_optimization(pieces, stock_length, kerf)
            
            # Display results
            self.results_widget.display_results(results)
            self.optimization_results = results
            
        except Exception as e:
            ImportExportDialog.show_error(self, "Errore Ottimizzazione", str(e))
    
    def _run_optimization(self, pieces: List[Dict[str, Any]], stock_length: float, kerf: float) -> Dict[str, Any]:
        """
        Run ILP optimization using existing logic.
        
        Returns:
            Dictionary with optimization results
        """
        try:
            from ui_qt.logic.refiner import pack_bars_knapsack_ilp
            
            # Convert pieces to expected format
            ilp_pieces = []
            for piece in pieces:
                for _ in range(piece['quantity']):
                    ilp_pieces.append({
                        'len': piece['length'],
                        'ax': 0.0,
                        'ad': 0.0,
                        'label': piece.get('label', '')
                    })
            
            # Run optimization
            bars, residuals = pack_bars_knapsack_ilp(
                pieces=ilp_pieces,
                stock=stock_length,
                kerf_base=kerf,
                ripasso_mm=0.0,
                conservative_angle_deg=45.0,
                max_angle=45.0,
                max_factor=1.5,
                reversible=False,
                thickness_mm=0.0,
                angle_tol=0.1,
                per_bar_time_s=15
            )
            
            # Format results
            total_waste = sum(residuals)
            total_used = len(bars) * stock_length - total_waste
            efficiency = (total_used / (len(bars) * stock_length) * 100) if bars else 0
            
            formatted_bars = []
            for bar, waste in zip(bars, residuals):
                formatted_bars.append({
                    'pieces': [{'length': p['len'], 'label': p.get('label', '')} for p in bar],
                    'waste': waste
                })
            
            return {
                'bars_used': len(bars),
                'total_waste': total_waste,
                'efficiency': efficiency,
                'stock_length': stock_length,
                'bars': formatted_bars
            }
            
        except Exception as e:
            raise Exception(f"Optimization failed: {e}")
    
    def _save_project(self):
        """Save current cutlist as project."""
        try:
            # Get project name
            default_name = self.current_project_name or "progetto"
            name, ok = QInputDialog.getText(
                self,
                "Nome Progetto",
                "Inserisci nome progetto:",
                text=default_name
            )
            
            if not ok or not name.strip():
                return
            
            # Create project data
            project = {
                'project_name': name.strip(),
                'stock_length': self.spin_stock_length.value(),
                'kerf': self.spin_kerf.value(),
                'pieces': self.table_widget.get_cutlist(),
                'notes': ''
            }
            
            # Save
            filename = name.strip().replace(' ', '_')
            success = self.project_manager.save_project(project, filename)
            
            if success:
                self.current_project_name = name.strip()
                ImportExportDialog.show_success(self, "Successo", "Progetto salvato con successo")
                self._refresh_recent_projects()
            else:
                ImportExportDialog.show_error(self, "Errore", "Impossibile salvare il progetto")
                
        except Exception as e:
            ImportExportDialog.show_error(self, "Errore Salvataggio", str(e))
    
    def _load_project_by_filename(self, filename: str):
        """Load project from filename."""
        try:
            project = self.project_manager.load_project(filename)
            self._load_project_data(project)
            ImportExportDialog.show_success(self, "Successo", "Progetto caricato con successo")
            
        except Exception as e:
            ImportExportDialog.show_error(self, "Errore Caricamento", str(e))
    
    def _load_project_data(self, project: Dict[str, Any]):
        """Load project data into UI."""
        self.current_project_name = project.get('project_name', '')
        
        # Load parameters
        if 'stock_length' in project:
            self.spin_stock_length.setValue(project['stock_length'])
        if 'kerf' in project:
            self.spin_kerf.setValue(project['kerf'])
        
        # Load pieces
        pieces = project.get('pieces', [])
        self.table_widget.load_cutlist(pieces)
        
        # Clear results
        self.results_widget.clear_results()
        self.optimization_results = None
    
    def _delete_project(self, filename: str):
        """Delete a project."""
        if not ImportExportDialog.confirm_action(
            self,
            "Conferma Eliminazione",
            f"Sei sicuro di voler eliminare il progetto '{filename}'?"
        ):
            return
        
        try:
            success = self.project_manager.delete_project(filename)
            if success:
                ImportExportDialog.show_success(self, "Successo", "Progetto eliminato")
                self._refresh_recent_projects()
            else:
                ImportExportDialog.show_error(self, "Errore", "Impossibile eliminare il progetto")
                
        except Exception as e:
            ImportExportDialog.show_error(self, "Errore", str(e))
    
    def _export_pdf(self):
        """Export results to PDF."""
        if not self.optimization_results:
            ImportExportDialog.show_error(self, "Errore", "Nessun risultato da esportare")
            return
        
        try:
            filepath = ImportExportDialog.export_pdf(self)
            if filepath:
                self.exporter.to_pdf(self.optimization_results, filepath)
                ImportExportDialog.show_success(self, "Successo", "PDF esportato con successo")
                
        except Exception as e:
            ImportExportDialog.show_error(self, "Errore Export PDF", str(e))
    
    def _export_excel(self):
        """Export results to Excel."""
        if not self.optimization_results:
            ImportExportDialog.show_error(self, "Errore", "Nessun risultato da esportare")
            return
        
        try:
            filepath = ImportExportDialog.export_excel(self)
            if filepath:
                pieces = self.table_widget.get_cutlist()
                self.exporter.to_excel(pieces, self.optimization_results, filepath)
                ImportExportDialog.show_success(self, "Successo", "Excel esportato con successo")
                
        except Exception as e:
            ImportExportDialog.show_error(self, "Errore Export Excel", str(e))
