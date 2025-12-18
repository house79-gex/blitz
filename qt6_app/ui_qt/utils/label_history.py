"""
Undo/Redo history system for label editor.
"""
from __future__ import annotations
from typing import List, Dict, Any, Optional


class EditorHistory:
    """Manages undo/redo history for the label editor."""
    
    def __init__(self, max_history: int = 50):
        self.history: List[List[Dict[str, Any]]] = []
        self.current_index: int = -1
        self.max_history = max_history
        
    def save_state(self, elements: List[Any]):
        """
        Save current state to history.
        
        Args:
            elements: List of label elements to save
        """
        # Remove all future states (redo stack)
        self.history = self.history[:self.current_index + 1]
        
        # Serialize and save state
        state = [elem.serialize() for elem in elements]
        self.history.append(state)
        self.current_index += 1
        
        # Limit history size
        if len(self.history) > self.max_history:
            self.history.pop(0)
            self.current_index -= 1
    
    def undo(self) -> Optional[List[Dict[str, Any]]]:
        """
        Undo to previous state.
        
        Returns:
            Previous state if available, None otherwise
        """
        if self.current_index > 0:
            self.current_index -= 1
            return self.history[self.current_index]
        return None
    
    def redo(self) -> Optional[List[Dict[str, Any]]]:
        """
        Redo to next state.
        
        Returns:
            Next state if available, None otherwise
        """
        if self.current_index < len(self.history) - 1:
            self.current_index += 1
            return self.history[self.current_index]
        return None
    
    def can_undo(self) -> bool:
        """Check if undo is available."""
        return self.current_index > 0
    
    def can_redo(self) -> bool:
        """Check if redo is available."""
        return self.current_index < len(self.history) - 1
    
    def clear(self):
        """Clear all history."""
        self.history = []
        self.current_index = -1
