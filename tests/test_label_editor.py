#!/usr/bin/env python3
"""
Simple test script for Label Editor functionality (non-GUI parts).
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'qt6_app'))


def test_history():
    """Test undo/redo history."""
    from ui_qt.utils.label_history import EditorHistory
    
    print("Testing history system...")
    
    history = EditorHistory(max_history=5)
    
    # Create some mock element states
    state1 = [{"type": "text", "text": "First", "x": 0, "y": 0}]
    state2 = [{"type": "text", "text": "First", "x": 0, "y": 0}, {"type": "text", "text": "Second", "x": 10, "y": 10}]
    state3 = [{"type": "text", "text": "First", "x": 0, "y": 0}, {"type": "text", "text": "Second", "x": 10, "y": 10}, {"type": "text", "text": "Third", "x": 20, "y": 20}]
    
    # Mock elements with serialize method
    class MockElement:
        def __init__(self, data):
            self.data = data
        def serialize(self):
            return self.data
    
    history.save_state([MockElement(state1[0])])
    history.save_state([MockElement(s) for s in state2])
    history.save_state([MockElement(s) for s in state3])
    
    # Test undo
    assert history.can_undo()
    state = history.undo()
    assert state is not None
    assert len(state) == 2
    print("✓ Undo works")
    
    # Test redo
    assert history.can_redo()
    state = history.redo()
    assert state is not None
    assert len(state) == 3
    print("✓ Redo works")
    
    print("✅ History tests passed!\n")


def test_template_manager():
    """Test template management."""
    from ui_qt.services.label_template_manager import LabelTemplateManager
    import tempfile
    import shutil
    
    print("Testing template manager...")
    
    # Create temp directory
    temp_dir = tempfile.mkdtemp()
    
    try:
        manager = LabelTemplateManager(temp_dir)
        
        # Test saving template
        template_data = {
            "name": "Test",
            "description": "Test template",
            "label_width": 62,
            "label_height": 100,
            "elements": [
                {"type": "text", "text": "Hello", "x": 10, "y": 10}
            ]
        }
        
        result = manager.save_template("Test", template_data)
        assert result, "Failed to save template"
        print("✓ Save template works")
        
        # Test loading template
        loaded = manager.load_template("Test")
        assert loaded is not None, "Failed to load template"
        assert loaded["name"] == "Test"
        print("✓ Load template works")
        
        # Test list templates
        templates = manager.list_templates()
        assert len(templates) > 0, "No templates listed"
        print(f"✓ List templates works (found {len(templates)} templates)")
        
        # Test duplicate
        result = manager.duplicate_template("Test", "Test_Copy")
        assert result, "Failed to duplicate template"
        loaded = manager.load_template("Test_Copy")
        assert loaded is not None
        print("✓ Duplicate template works")
        
        # Test delete
        result = manager.delete_template("Test_Copy")
        assert result, "Failed to delete template"
        loaded = manager.load_template("Test_Copy")
        assert loaded is None
        print("✓ Delete template works")
        
        # Verify default templates exist
        default_templates = ["Standard", "Minimal", "Barcode_Focus", "Empty"]
        for name in default_templates:
            template = manager.load_template(name)
            assert template is not None, f"Default template {name} not found"
        print(f"✓ All {len(default_templates)} default templates exist")
        
        print("✅ Template manager tests passed!\n")
    finally:
        # Cleanup
        shutil.rmtree(temp_dir)


def main():
    """Run all tests."""
    print("=" * 60)
    print("Label Editor Component Tests (Non-GUI)")
    print("=" * 60 + "\n")
    
    try:
        test_history()
        test_template_manager()
        
        print("=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
