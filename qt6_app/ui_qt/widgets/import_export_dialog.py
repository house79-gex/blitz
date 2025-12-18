"""
Import/Export Dialog - File import/export dialogs
File: qt6_app/ui_qt/widgets/import_export_dialog.py
"""

from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget
from typing import Optional, List, Dict, Any


class ImportExportDialog:
    """Helper class for file import/export dialogs."""
    
    @staticmethod
    def import_file(parent: Optional[QWidget] = None) -> Optional[tuple]:
        """
        Show import file dialog.
        
        Returns:
            (filepath, file_type) tuple or None if cancelled
        """
        file_filter = (
            "All Supported (*.csv *.xlsx *.txt *.json *.blz);;"
            "CSV Files (*.csv);;"
            "Excel Files (*.xlsx);;"
            "Text Files (*.txt);;"
            "JSON/Project Files (*.json *.blz)"
        )
        
        filepath, selected_filter = QFileDialog.getOpenFileName(
            parent,
            "Importa Cutlist",
            "",
            file_filter
        )
        
        if not filepath:
            return None
        
        # Determine file type from extension
        if filepath.endswith('.csv'):
            file_type = 'csv'
        elif filepath.endswith('.xlsx'):
            file_type = 'excel'
        elif filepath.endswith('.txt'):
            file_type = 'txt'
        elif filepath.endswith('.json') or filepath.endswith('.blz'):
            file_type = 'json'
        else:
            file_type = 'unknown'
        
        return filepath, file_type
    
    @staticmethod
    def export_csv(parent: Optional[QWidget] = None) -> Optional[str]:
        """Show export CSV dialog."""
        filepath, _ = QFileDialog.getSaveFileName(
            parent,
            "Esporta CSV",
            "cutlist.csv",
            "CSV Files (*.csv)"
        )
        return filepath if filepath else None
    
    @staticmethod
    def export_excel(parent: Optional[QWidget] = None) -> Optional[str]:
        """Show export Excel dialog."""
        filepath, _ = QFileDialog.getSaveFileName(
            parent,
            "Esporta Excel",
            "cutlist.xlsx",
            "Excel Files (*.xlsx)"
        )
        return filepath if filepath else None
    
    @staticmethod
    def export_pdf(parent: Optional[QWidget] = None) -> Optional[str]:
        """Show export PDF dialog."""
        filepath, _ = QFileDialog.getSaveFileName(
            parent,
            "Esporta PDF",
            "cut_plan.pdf",
            "PDF Files (*.pdf)"
        )
        return filepath if filepath else None
    
    @staticmethod
    def save_project(parent: Optional[QWidget] = None, default_name: str = "project") -> Optional[str]:
        """Show save project dialog."""
        filepath, _ = QFileDialog.getSaveFileName(
            parent,
            "Salva Progetto",
            f"{default_name}.blz",
            "Blitz Project Files (*.blz)"
        )
        return filepath if filepath else None
    
    @staticmethod
    def load_project(parent: Optional[QWidget] = None) -> Optional[str]:
        """Show load project dialog."""
        filepath, _ = QFileDialog.getOpenFileName(
            parent,
            "Carica Progetto",
            "",
            "Blitz Project Files (*.blz);;JSON Files (*.json)"
        )
        return filepath if filepath else None
    
    @staticmethod
    def show_error(parent: Optional[QWidget], title: str, message: str):
        """Show error message box."""
        QMessageBox.critical(parent, title, message)
    
    @staticmethod
    def show_success(parent: Optional[QWidget], title: str, message: str):
        """Show success message box."""
        QMessageBox.information(parent, title, message)
    
    @staticmethod
    def confirm_action(parent: Optional[QWidget], title: str, message: str) -> bool:
        """
        Show confirmation dialog.
        
        Returns:
            True if user confirmed, False otherwise
        """
        reply = QMessageBox.question(
            parent,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        return reply == QMessageBox.StandardButton.Yes
