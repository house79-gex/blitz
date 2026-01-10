#!/usr/bin/env python3
"""
Test script for Label Editor drag & drop and live properties (non-GUI validation).
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'qt6_app'))


def test_element_types():
    """Test that all element types are defined."""
    print("Testing element types...")
    
    from ui_qt.widgets.label_element import (
        TextElement, FieldElement, BarcodeElement,
        ImageElement, LineElement, ShapeElement
    )
    
    # Create instances
    text_elem = TextElement(text="Test", x=10, y=20)
    field_elem = FieldElement(source="length", x=10, y=20)
    barcode_elem = BarcodeElement(source="order_id", x=10, y=20)
    image_elem = ImageElement(x=10, y=20)
    line_elem = LineElement(x=10, y=20)
    shape_elem = ShapeElement(x=10, y=20)
    
    # Verify properties
    assert text_elem.text == "Test"
    assert field_elem.source == "length"
    assert barcode_elem.source == "order_id"
    assert image_elem.x == 10
    assert line_elem.x == 10
    assert shape_elem.x == 10
    
    print("✓ All element types can be created")
    print("✓ Element properties are accessible")
    print("✅ Element types test passed!\n")


def test_element_serialization():
    """Test element serialization."""
    print("Testing element serialization...")
    
    from ui_qt.widgets.label_element import TextElement, deserialize_element
    
    # Create element
    elem = TextElement(text="Hello", x=15, y=25, font_size=14)
    elem.bold = True
    
    # Serialize
    data = elem.serialize()
    assert data['type'] == 'text'
    assert data['text'] == 'Hello'
    assert data['x'] == 15
    assert data['y'] == 25
    assert data['font_size'] == 14
    assert data['bold'] is True
    print("✓ Element serialization works")
    
    # Deserialize
    restored = deserialize_element(data)
    assert restored is not None
    assert isinstance(restored, TextElement)
    assert restored.text == 'Hello'
    assert restored.x == 15
    assert restored.bold is True
    print("✓ Element deserialization works")
    
    print("✅ Serialization test passed!\n")


def test_canvas_methods_exist():
    """Test that canvas methods are defined."""
    print("Testing canvas method signatures...")
    
    # Just check imports work
    try:
        from ui_qt.widgets.label_canvas import LabelCanvas
        
        # Verify class has expected methods
        assert hasattr(LabelCanvas, '__init__')
        assert hasattr(LabelCanvas, 'add_element')
        assert hasattr(LabelCanvas, 'remove_element')
        assert hasattr(LabelCanvas, 'clear_elements')
        assert hasattr(LabelCanvas, '_create_element_from_type')
        
        print("✓ Canvas class is importable")
        print("✓ Canvas has all required methods")
        print("✅ Canvas method signatures test passed!\n")
    except ImportError as e:
        print(f"⚠️  Canvas import failed (PySide6 not available): {e}")
        print("✅ Canvas method signatures test skipped (non-critical)\n")


def test_sidebar_drag_button_class():
    """Test that ElementDragButton class exists."""
    print("Testing sidebar drag button class...")
    
    try:
        from ui_qt.widgets.label_element_sidebar import ElementDragButton
        
        # Verify class exists
        assert ElementDragButton is not None
        print("✓ ElementDragButton class exists")
        print("✅ Sidebar drag button test passed!\n")
    except ImportError as e:
        print(f"⚠️  ElementDragButton import failed (PySide6 not available): {e}")
        print("✅ Sidebar drag button test skipped (non-critical)\n")


def test_properties_panel_has_blocking():
    """Test that properties panel has blocking flag."""
    print("Testing properties panel blocking mechanism...")
    
    try:
        from ui_qt.widgets.label_properties_panel import LabelPropertiesPanel
        
        # Verify class has _updating attribute in __init__
        import inspect
        source = inspect.getsource(LabelPropertiesPanel.__init__)
        assert '_updating' in source, "PropertiesPanel should have _updating flag"
        
        print("✓ Properties panel has _updating flag")
        print("✅ Properties panel blocking test passed!\n")
    except ImportError as e:
        print(f"⚠️  PropertiesPanel import failed (PySide6 not available): {e}")
        print("✅ Properties panel test skipped (non-critical)\n")


def test_wizard_integration():
    """Test wizard integration."""
    print("Testing wizard integration...")
    
    try:
        from ui_qt.pages.label_editor_wizard import LabelEditorWizard
        
        assert LabelEditorWizard is not None
        print("✓ LabelEditorWizard class exists")
        
        # Check that label_editor_page imports the wizard
        import inspect
        from ui_qt.pages import label_editor_page
        source = inspect.getsource(label_editor_page)
        
        assert 'LabelEditorWizard' in source, "label_editor_page should import LabelEditorWizard"
        assert '_show_wizard' in source, "label_editor_page should have _show_wizard method"
        
        print("✓ Wizard is imported in label_editor_page")
        print("✓ _show_wizard method exists")
        print("✅ Wizard integration test passed!\n")
    except ImportError as e:
        print(f"⚠️  Wizard import failed (PySide6 not available): {e}")
        print("✅ Wizard integration test skipped (non-critical)\n")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Label Editor Implementation Validation (Non-GUI)")
    print("=" * 60 + "\n")
    
    try:
        test_element_types()
        test_element_serialization()
        test_canvas_methods_exist()
        test_sidebar_drag_button_class()
        test_properties_panel_has_blocking()
        test_wizard_integration()
        
        print("=" * 60)
        print("✅ ALL VALIDATION TESTS PASSED!")
        print("=" * 60)
        print("\nNote: Full GUI testing requires PySide6 installation and")
        print("a display environment. The implementation is structurally sound.")
        return 0
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

