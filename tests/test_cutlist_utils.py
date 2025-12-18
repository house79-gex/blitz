"""
Unit tests for Cutlist utility modules
File: tests/test_cutlist_utils.py
"""

import pytest
import os
import tempfile
import json
from pathlib import Path

# Setup path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'qt6_app'))

from ui_qt.utils.cutlist_importer import CutlistImporter
from ui_qt.utils.cutlist_exporter import CutlistExporter
from ui_qt.utils.project_manager import ProjectManager


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_pieces():
    """Sample cutlist pieces for testing."""
    return [
        {'length': 1250, 'quantity': 5, 'label': 'Fermavetro A'},
        {'length': 800, 'quantity': 3, 'label': 'Vetro Standard'},
        {'length': 1420, 'quantity': 2, 'label': 'Astina Lunga'}
    ]


@pytest.fixture
def sample_project(sample_pieces):
    """Sample project for testing."""
    return {
        'project_name': 'Test Project',
        'stock_length': 6500,
        'kerf': 3,
        'pieces': sample_pieces
    }


class TestCutlistImporter:
    """Tests for CutlistImporter."""
    
    def test_csv_import(self, temp_dir, sample_pieces):
        """Test CSV import functionality."""
        # Create test CSV
        csv_file = os.path.join(temp_dir, 'test.csv')
        with open(csv_file, 'w') as f:
            f.write('length,quantity,label\n')
            for piece in sample_pieces:
                f.write(f"{piece['length']},{piece['quantity']},{piece['label']}\n")
        
        # Import
        importer = CutlistImporter()
        imported = importer.from_csv(csv_file)
        
        assert len(imported) == len(sample_pieces)
        assert imported[0]['length'] == sample_pieces[0]['length']
        assert imported[0]['quantity'] == sample_pieces[0]['quantity']
        assert imported[0]['label'] == sample_pieces[0]['label']
    
    def test_txt_import(self, temp_dir):
        """Test TXT import functionality."""
        # Create test TXT
        txt_file = os.path.join(temp_dir, 'test.txt')
        with open(txt_file, 'w') as f:
            f.write('1250\n800\n1420\n')
        
        # Import
        importer = CutlistImporter()
        imported = importer.from_txt(txt_file)
        
        assert len(imported) == 3
        assert imported[0]['length'] == 1250
        assert imported[0]['quantity'] == 1
        assert imported[0]['label'] == ''
    
    def test_json_import(self, temp_dir, sample_project):
        """Test JSON import functionality."""
        # Create test JSON
        json_file = os.path.join(temp_dir, 'test.json')
        with open(json_file, 'w') as f:
            json.dump(sample_project, f)
        
        # Import
        importer = CutlistImporter()
        imported = importer.from_json(json_file)
        
        assert imported['project_name'] == sample_project['project_name']
        assert len(imported['pieces']) == len(sample_project['pieces'])
        assert imported['stock_length'] == sample_project['stock_length']


class TestCutlistExporter:
    """Tests for CutlistExporter."""
    
    def test_csv_export(self, temp_dir, sample_pieces):
        """Test CSV export functionality."""
        csv_file = os.path.join(temp_dir, 'export.csv')
        
        exporter = CutlistExporter()
        exporter.to_csv(sample_pieces, csv_file)
        
        assert os.path.exists(csv_file)
        
        # Verify content
        with open(csv_file, 'r') as f:
            lines = f.readlines()
            assert len(lines) == len(sample_pieces) + 1  # +1 for header
            assert 'length,quantity,label' in lines[0]
    
    def test_json_export(self, temp_dir, sample_project):
        """Test JSON export functionality."""
        json_file = os.path.join(temp_dir, 'export.json')
        
        exporter = CutlistExporter()
        exporter.to_json(sample_project, json_file)
        
        assert os.path.exists(json_file)
        
        # Verify content
        with open(json_file, 'r') as f:
            exported = json.load(f)
            assert exported['project_name'] == sample_project['project_name']
            assert 'modified_at' in exported
    
    def test_excel_export(self, temp_dir, sample_pieces):
        """Test Excel export functionality."""
        xlsx_file = os.path.join(temp_dir, 'export.xlsx')
        
        results = {
            'bars_used': 2,
            'total_waste': 1486.0,
            'efficiency': 88.6,
            'stock_length': 6500,
            'bars': []
        }
        
        exporter = CutlistExporter()
        exporter.to_excel(sample_pieces, results, xlsx_file)
        
        assert os.path.exists(xlsx_file)
    
    def test_pdf_export(self, temp_dir):
        """Test PDF export functionality."""
        pdf_file = os.path.join(temp_dir, 'export.pdf')
        
        results = {
            'bars_used': 2,
            'total_waste': 1486.0,
            'efficiency': 88.6,
            'stock_length': 6500,
            'bars': [
                {
                    'pieces': [
                        {'length': 1250, 'label': 'Test'},
                        {'length': 800, 'label': 'Test2'}
                    ],
                    'waste': 348.0
                }
            ]
        }
        
        exporter = CutlistExporter()
        exporter.to_pdf(results, pdf_file)
        
        assert os.path.exists(pdf_file)
        assert os.path.getsize(pdf_file) > 0


class TestProjectManager:
    """Tests for ProjectManager."""
    
    def test_save_and_load_project(self, temp_dir, sample_project):
        """Test project save and load functionality."""
        pm = ProjectManager(temp_dir)
        
        # Save
        success = pm.save_project(sample_project, 'test_project')
        assert success
        
        # Load
        loaded = pm.load_project('test_project')
        assert loaded['project_name'] == sample_project['project_name']
        assert len(loaded['pieces']) == len(sample_project['pieces'])
    
    def test_list_recent_projects(self, temp_dir, sample_project):
        """Test listing recent projects."""
        pm = ProjectManager(temp_dir)
        
        # Save multiple projects
        pm.save_project(sample_project, 'project1')
        
        project2 = sample_project.copy()
        project2['project_name'] = 'Project 2'
        pm.save_project(project2, 'project2')
        
        # List
        recent = pm.list_recent_projects()
        assert len(recent) == 2
        assert all('filename' in p for p in recent)
        assert all('total_pieces' in p for p in recent)
    
    def test_delete_project(self, temp_dir, sample_project):
        """Test project deletion."""
        pm = ProjectManager(temp_dir)
        
        # Save
        pm.save_project(sample_project, 'test_delete')
        
        # Delete
        success = pm.delete_project('test_delete')
        assert success
        
        # Verify deleted
        recent = pm.list_recent_projects()
        assert len(recent) == 0
    
    def test_project_metadata(self, temp_dir, sample_project):
        """Test project metadata is correctly stored."""
        pm = ProjectManager(temp_dir)
        
        pm.save_project(sample_project, 'test_meta')
        loaded = pm.load_project('test_meta')
        
        assert 'created_at' in loaded
        assert 'modified_at' in loaded
        assert loaded['project_name'] == sample_project['project_name']
