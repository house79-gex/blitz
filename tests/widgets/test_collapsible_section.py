"""Unit tests for CollapsibleSection widget."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel
from qt6_app.ui_qt.widgets.collapsible_section import CollapsibleSection


def test_collapsible_section_initialization(qapp):
    """Test collapsible section creates."""
    section = CollapsibleSection("Test Section")
    assert section is not None
    assert "Test Section" in section.header.text()


def test_collapsible_section_add_content(qapp):
    """Test adding content to section."""
    section = CollapsibleSection("Test")
    content = QLabel("Test Content")
    section.add_content(content)
    
    # Content should be in the layout
    assert section.content_layout.count() > 0


def test_collapsible_section_toggle(qapp):
    """Test expand/collapse toggle."""
    section = CollapsibleSection("Test")
    content = QLabel("Test Content")
    section.add_content(content)
    
    # Initially expanded
    initial_collapsed = section.is_collapsed()
    
    # Toggle
    section._toggle()
    
    # State should change
    assert section.is_collapsed() != initial_collapsed


def test_collapsible_section_collapse(qapp):
    """Test explicit collapse."""
    section = CollapsibleSection("Test")
    content = QLabel("Test Content")
    section.add_content(content)
    
    section.collapse()
    assert section.is_collapsed()


def test_collapsible_section_expand(qapp):
    """Test explicit expand."""
    section = CollapsibleSection("Test", start_collapsed=True)
    content = QLabel("Test Content")
    section.add_content(content)
    
    assert section.is_collapsed()
    
    section.expand()
    assert not section.is_collapsed()


def test_collapsible_section_start_collapsed(qapp):
    """Test section starting collapsed."""
    section = CollapsibleSection("Test", start_collapsed=True)
    assert section.is_collapsed()
    assert not section.content_container.isVisible()


def test_collapsible_section_start_expanded(qapp):
    """Test section starting expanded."""
    section = CollapsibleSection("Test", start_collapsed=False)
    # Note: Widget visibility requires showing the widget in headless mode
    # We check the collapsed state instead
    assert not section.is_collapsed()


def test_collapsible_section_set_collapsed(qapp):
    """Test set_collapsed method."""
    section = CollapsibleSection("Test")
    content = QLabel("Test Content")
    section.add_content(content)
    
    # Set collapsed without animation
    section.set_collapsed(True)
    assert section.is_collapsed()
    
    # Set expanded without animation
    section.set_collapsed(False)
    assert not section.is_collapsed()


def test_collapsible_section_arrow_indicator(qapp):
    """Test arrow indicator changes with state."""
    section = CollapsibleSection("Test")
    
    # Expanded should show ▼
    assert "▼" in section.header.text()
    
    section.collapse()
    # Collapsed should show ▶
    assert "▶" in section.header.text()
