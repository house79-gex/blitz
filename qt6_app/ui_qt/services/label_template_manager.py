"""
Template manager for saving, loading, and managing label templates.
"""
from __future__ import annotations
import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime


class LabelTemplateManager:
    """Manages label templates with new WYSIWYG format."""
    
    def __init__(self, templates_dir: Optional[str] = None):
        if templates_dir is None:
            # Default to data directory
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            templates_dir = os.path.join(base_dir, "data", "wysiwyg_templates")
        
        self.templates_dir = templates_dir
        self._ensure_dir()
        self._ensure_default_templates()
    
    def _ensure_dir(self):
        """Ensure templates directory exists."""
        os.makedirs(self.templates_dir, exist_ok=True)
    
    def _ensure_default_templates(self):
        """Ensure default templates exist."""
        default_templates = self._get_default_templates()
        
        for name, template in default_templates.items():
            template_file = os.path.join(self.templates_dir, f"{name}.json")
            if not os.path.exists(template_file):
                self.save_template(name, template)
    
    def _get_default_templates(self) -> Dict[str, Dict[str, Any]]:
        """Get default template definitions."""
        return {
            "Standard": {
                "name": "Standard",
                "description": "Etichetta completa con profilo, lunghezza e barcode",
                "label_width": 62,
                "label_height": 100,
                "elements": [
                    {
                        "type": "text",
                        "text": "BLITZ",
                        "x": 5, "y": 5,
                        "width": 50, "height": 15,
                        "font_family": "Arial",
                        "font_size": 14,
                        "bold": True,
                        "italic": False,
                        "color": "#000000"
                    },
                    {
                        "type": "field",
                        "source": "profile_name",
                        "format_string": "{}",
                        "x": 5, "y": 25,
                        "width": 52, "height": 12,
                        "font_family": "Arial",
                        "font_size": 12,
                        "bold": False,
                        "italic": False,
                        "color": "#000000"
                    },
                    {
                        "type": "field",
                        "source": "length",
                        "format_string": "{} mm",
                        "x": 5, "y": 42,
                        "width": 52, "height": 25,
                        "font_family": "Arial",
                        "font_size": 24,
                        "bold": True,
                        "italic": False,
                        "color": "#000000"
                    },
                    {
                        "type": "barcode",
                        "source": "order_id",
                        "barcode_type": "code128",
                        "x": 5, "y": 72,
                        "width": 52, "height": 22
                    }
                ]
            },
            "Minimal": {
                "name": "Minimal",
                "description": "Solo lunghezza in grande",
                "label_width": 62,
                "label_height": 100,
                "elements": [
                    {
                        "type": "field",
                        "source": "length",
                        "format_string": "{} mm",
                        "x": 5, "y": 30,
                        "width": 52, "height": 40,
                        "font_family": "Arial",
                        "font_size": 36,
                        "bold": True,
                        "italic": False,
                        "color": "#000000"
                    }
                ]
            },
            "Barcode_Focus": {
                "name": "Barcode Focus",
                "description": "Enfasi sul barcode per tracking",
                "label_width": 62,
                "label_height": 100,
                "elements": [
                    {
                        "type": "field",
                        "source": "profile_name",
                        "format_string": "{}",
                        "x": 5, "y": 5,
                        "width": 52, "height": 10,
                        "font_family": "Arial",
                        "font_size": 10,
                        "bold": True,
                        "italic": False,
                        "color": "#000000"
                    },
                    {
                        "type": "barcode",
                        "source": "piece_id",
                        "barcode_type": "code128",
                        "x": 5, "y": 20,
                        "width": 52, "height": 35
                    },
                    {
                        "type": "field",
                        "source": "length",
                        "format_string": "{} mm",
                        "x": 5, "y": 60,
                        "width": 52, "height": 15,
                        "font_family": "Arial",
                        "font_size": 14,
                        "bold": False,
                        "italic": False,
                        "color": "#000000"
                    }
                ]
            },
            "Empty": {
                "name": "Empty",
                "description": "Template vuoto",
                "label_width": 62,
                "label_height": 100,
                "elements": []
            }
        }
    
    def save_template(self, name: str, template_data: Dict[str, Any]) -> bool:
        """
        Save template to file.
        
        Args:
            name: Template name
            template_data: Template dictionary
            
        Returns:
            True if saved successfully
        """
        try:
            # Add metadata
            template_data["name"] = name
            template_data["updated_at"] = datetime.now().isoformat()
            
            # Save to file
            filename = f"{self._sanitize_filename(name)}.json"
            filepath = os.path.join(self.templates_dir, filename)
            
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(template_data, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            print(f"Error saving template: {e}")
            return False
    
    def load_template(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Load template from file.
        
        Args:
            name: Template name
            
        Returns:
            Template dictionary or None if not found
        """
        try:
            filename = f"{self._sanitize_filename(name)}.json"
            filepath = os.path.join(self.templates_dir, filename)
            
            if not os.path.exists(filepath):
                return None
            
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading template: {e}")
            return None
    
    def list_templates(self) -> List[Dict[str, Any]]:
        """
        List all available templates.
        
        Returns:
            List of template metadata dictionaries
        """
        templates = []
        
        try:
            if not os.path.exists(self.templates_dir):
                return templates
            
            for filename in os.listdir(self.templates_dir):
                if filename.endswith(".json"):
                    filepath = os.path.join(self.templates_dir, filename)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            template = json.load(f)
                            templates.append({
                                "name": template.get("name", filename[:-5]),
                                "description": template.get("description", ""),
                                "updated_at": template.get("updated_at", ""),
                                "label_width": template.get("label_width", 62),
                                "label_height": template.get("label_height", 100),
                                "element_count": len(template.get("elements", []))
                            })
                    except Exception as e:
                        print(f"Error reading template {filename}: {e}")
        except Exception as e:
            print(f"Error listing templates: {e}")
        
        return sorted(templates, key=lambda t: t.get("name", ""))
    
    def delete_template(self, name: str) -> bool:
        """
        Delete template.
        
        Args:
            name: Template name
            
        Returns:
            True if deleted successfully
        """
        try:
            filename = f"{self._sanitize_filename(name)}.json"
            filepath = os.path.join(self.templates_dir, filename)
            
            if os.path.exists(filepath):
                os.remove(filepath)
                return True
            return False
        except Exception as e:
            print(f"Error deleting template: {e}")
            return False
    
    def duplicate_template(self, src_name: str, new_name: str) -> bool:
        """
        Duplicate template with new name.
        
        Args:
            src_name: Source template name
            new_name: New template name
            
        Returns:
            True if duplicated successfully
        """
        template = self.load_template(src_name)
        if template:
            template["name"] = new_name
            template["description"] = f"Copia di {src_name}"
            return self.save_template(new_name, template)
        return False
    
    def export_template(self, name: str, export_path: str) -> bool:
        """
        Export template to external file.
        
        Args:
            name: Template name
            export_path: Path to export file
            
        Returns:
            True if exported successfully
        """
        template = self.load_template(name)
        if template:
            try:
                with open(export_path, "w", encoding="utf-8") as f:
                    json.dump(template, f, ensure_ascii=False, indent=2)
                return True
            except Exception as e:
                print(f"Error exporting template: {e}")
        return False
    
    def import_template(self, import_path: str, name: Optional[str] = None) -> bool:
        """
        Import template from external file.
        
        Args:
            import_path: Path to import file
            name: Optional new name for template
            
        Returns:
            True if imported successfully
        """
        try:
            with open(import_path, "r", encoding="utf-8") as f:
                template = json.load(f)
            
            if name:
                template["name"] = name
            
            template_name = template.get("name", "Imported")
            return self.save_template(template_name, template)
        except Exception as e:
            print(f"Error importing template: {e}")
            return False
    
    def _sanitize_filename(self, name: str) -> str:
        """Sanitize filename by removing invalid characters."""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, "_")
        return name
