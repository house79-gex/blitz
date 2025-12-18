"""
Project Manager - Manage cutlist projects (save/load)
File: qt6_app/ui_qt/utils/project_manager.py
"""

from typing import List, Dict, Any
import json
import os
from pathlib import Path
from datetime import datetime


class ProjectManager:
    """Manage cutlist projects (save/load)."""
    
    def __init__(self, projects_dir: str = None):
        """
        Initialize project manager.
        
        Args:
            projects_dir: Directory to store projects. 
                         Defaults to ~/blitz/projects/
        """
        if projects_dir is None:
            projects_dir = str(Path.home() / "blitz" / "projects")
        
        self.projects_dir = projects_dir
        self._ensure_directory()
    
    def _ensure_directory(self):
        """Ensure projects directory exists."""
        try:
            os.makedirs(self.projects_dir, exist_ok=True)
        except Exception:
            pass
    
    def save_project(self, project: Dict[str, Any], filename: str) -> bool:
        """
        Save project to .blz file.
        
        Args:
            project: Project dictionary with pieces and settings
            filename: Filename (without .blz extension)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure .blz extension
            if not filename.endswith('.blz'):
                filename += '.blz'
            
            filepath = os.path.join(self.projects_dir, filename)
            
            # Add timestamps
            if 'created_at' not in project:
                project['created_at'] = datetime.now().isoformat()
            project['modified_at'] = datetime.now().isoformat()
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(project, f, indent=2, ensure_ascii=False)
            
            return True
            
        except Exception:
            return False
    
    def load_project(self, filename: str) -> Dict[str, Any]:
        """
        Load project from .blz file.
        
        Args:
            filename: Filename (with or without .blz extension)
        
        Returns:
            Project dictionary
        
        Raises:
            Exception if file not found or invalid
        """
        try:
            # Ensure .blz extension
            if not filename.endswith('.blz'):
                filename += '.blz'
            
            filepath = os.path.join(self.projects_dir, filename)
            
            if not os.path.exists(filepath):
                raise FileNotFoundError(f"Project file not found: {filename}")
            
            with open(filepath, 'r', encoding='utf-8') as f:
                project = json.load(f)
            
            return project
            
        except Exception as e:
            raise Exception(f"Error loading project: {e}")
    
    def list_recent_projects(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent projects sorted by modification date.
        
        Args:
            limit: Maximum number of projects to return
        
        Returns:
            List of project info dictionaries
        """
        projects = []
        
        try:
            self._ensure_directory()
            
            # Get all .blz files
            for filename in os.listdir(self.projects_dir):
                if not filename.endswith('.blz'):
                    continue
                
                filepath = os.path.join(self.projects_dir, filename)
                
                try:
                    # Get file stats
                    stat = os.stat(filepath)
                    modified_time = datetime.fromtimestamp(stat.st_mtime)
                    
                    # Try to read project metadata
                    with open(filepath, 'r', encoding='utf-8') as f:
                        project = json.load(f)
                    
                    # Calculate total pieces
                    total_pieces = sum(p.get('quantity', 1) for p in project.get('pieces', []))
                    
                    # Calculate total length
                    total_length = sum(
                        p.get('length', 0) * p.get('quantity', 1) 
                        for p in project.get('pieces', [])
                    ) / 1000.0  # Convert to meters
                    
                    projects.append({
                        'filename': filename,
                        'name': project.get('project_name', filename.replace('.blz', '')),
                        'created_at': project.get('created_at', ''),
                        'modified_at': project.get('modified_at', modified_time.isoformat()),
                        'stock_length': project.get('stock_length', 0),
                        'total_pieces': total_pieces,
                        'total_length_m': total_length,
                        'notes': project.get('notes', '')
                    })
                    
                except Exception:
                    continue
            
            # Sort by modification date (most recent first)
            projects.sort(key=lambda p: p['modified_at'], reverse=True)
            
            return projects[:limit]
            
        except Exception:
            return []
    
    def delete_project(self, filename: str) -> bool:
        """
        Delete a project file.
        
        Args:
            filename: Filename (with or without .blz extension)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure .blz extension
            if not filename.endswith('.blz'):
                filename += '.blz'
            
            filepath = os.path.join(self.projects_dir, filename)
            
            if os.path.exists(filepath):
                os.remove(filepath)
                return True
            
            return False
            
        except Exception:
            return False
    
    def get_projects_directory(self) -> str:
        """Get the projects directory path."""
        return self.projects_dir
