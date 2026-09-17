"""
Cutlist Importer - Import cutlist data from various formats
File: qt6_app/ui_qt/utils/cutlist_importer.py
"""

from typing import List, Dict, Any
import csv
import json


class CutlistImporter:
    """Handle import from various formats."""
    
    @staticmethod
    def from_csv(filepath: str) -> List[Dict[str, Any]]:
        """
        Import from CSV file.
        Expected format: length,quantity,label
        """
        pieces = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        parsed = CutlistImporter._parse_row_dict(row)
                        if parsed:
                            pieces.append(parsed)
                    except (ValueError, KeyError):
                        continue
        except Exception as e:
            raise Exception(f"Error importing CSV: {e}")
        
        return pieces
    
    @staticmethod
    def _has_header_row(worksheet) -> bool:
        """
        Check if Excel worksheet has a header row.
        Returns True if first cell looks like 'length' or similar header text.
        """
        first_cell = worksheet['A1'].value
        if not first_cell or not isinstance(first_cell, str):
            return False
        return 'length' in first_cell.lower()
    
    @staticmethod
    def from_excel(filepath: str) -> List[Dict[str, Any]]:
        """
        Import from Excel file.
        Expected format:
        - Column A: Length (mm)
        - Column B: Quantity
        - Column C: Label (optional)
        """
        pieces = []
        try:
            import openpyxl
            wb = openpyxl.load_workbook(filepath, read_only=True)
            ws = wb.active
            
            # Skip header row if it exists
            start_row = 2 if CutlistImporter._has_header_row(ws) else 1
            
            for row in ws.iter_rows(min_row=start_row, values_only=True):
                if not row or len(row) < 2:
                    continue
                
                try:
                    length = float(row[0]) if row[0] else 0
                    quantity = int(row[1]) if row[1] else 1
                    label = str(row[2]).strip() if len(row) > 2 and row[2] else ''
                    
                    if length > 0 and quantity > 0:
                        pieces.append({
                            'length': length,
                            'quantity': quantity,
                            'label': label
                        })
                except (ValueError, TypeError):
                    continue
            
            wb.close()
        except ImportError:
            raise Exception("openpyxl not installed. Install with: pip install openpyxl")
        except Exception as e:
            raise Exception(f"Error importing Excel: {e}")
        
        return pieces
    
    @staticmethod
    def from_txt(filepath: str) -> List[Dict[str, Any]]:
        """
        Import from plain text file (one length per line).
        Each line should contain a single number representing length in mm.
        """
        pieces = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    try:
                        length = float(line)
                        if length > 0:
                            pieces.append({
                                'length': length,
                                'quantity': 1,
                                'label': ''
                            })
                    except ValueError:
                        continue
        except Exception as e:
            raise Exception(f"Error importing TXT: {e}")
        
        return pieces
    
    @staticmethod
    def from_json(filepath: str) -> Dict[str, Any]:
        """
        Import from JSON project file.
        Returns complete project dict with pieces and settings.
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                project = json.load(f)
            
            # Validate project structure
            if 'pieces' not in project:
                raise ValueError("Invalid project file: missing 'pieces' field")
            
            # Ensure pieces have required fields
            validated_pieces = []
            for piece in project.get('pieces', []):
                if 'length' in piece and 'quantity' in piece:
                    validated_pieces.append({
                        'length': float(piece['length']),
                        'quantity': int(piece['quantity']),
                        'label': piece.get('label', '')
                    })
            
            project['pieces'] = validated_pieces
            return project
            
        except Exception as e:
            raise Exception(f"Error importing JSON: {e}")

    @staticmethod
    def _first_present(row: Dict[str, Any], *keys, default=None):
        lower = {str(k).strip().lower(): v for k, v in row.items()}
        for key in keys:
            if key.lower() in lower and lower[key.lower()] not in (None, ""):
                return lower[key.lower()]
        return default

    @staticmethod
    def _parse_row_dict(row: Dict[str, Any]) -> Dict[str, Any]:
        """Normalizza una riga CSV/dict in pezzo cutlist."""
        length = CutlistImporter._first_present(row, "length", "length_mm", "lunghezza", default=0)
        quantity = CutlistImporter._first_present(row, "quantity", "qty", "qta", "quantita", default=1)
        label = CutlistImporter._first_present(row, "label", "element", "elemento", default="") or ""
        try:
            length_f = float(length)
            qty_i = int(float(quantity))
        except (TypeError, ValueError):
            return {}
        if length_f <= 0 or qty_i <= 0:
            return {}
        piece = {
            "length": length_f,
            "quantity": qty_i,
            "label": str(label).strip(),
        }
        ang_sx = CutlistImporter._first_present(row, "ang_sx", "ax", "angolo_sx")
        ang_dx = CutlistImporter._first_present(row, "ang_dx", "ad", "angolo_dx")
        profile = CutlistImporter._first_present(row, "profile", "profilo")
        note = CutlistImporter._first_present(row, "note")
        if ang_sx is not None:
            try:
                piece["ang_sx"] = float(ang_sx)
            except (TypeError, ValueError):
                pass
        if ang_dx is not None:
            try:
                piece["ang_dx"] = float(ang_dx)
            except (TypeError, ValueError):
                pass
        if profile:
            piece["profile"] = str(profile).strip()
        if note:
            piece["note"] = str(note).strip()
        return piece

    @staticmethod
    def to_automatico_cuts(source, default_profile: str = "IMPORT") -> list:
        """
        Converte pezzi importati o un progetto JSON nel formato cutlist di Automatico:
        {profile, element, length_mm, ang_sx, ang_dx, qty, note}
        """
        pieces = []
        if isinstance(source, dict):
            if isinstance(source.get("cuts"), list):
                pieces = source["cuts"]
            elif isinstance(source.get("pieces"), list):
                pieces = source["pieces"]
            else:
                pieces = []
        elif isinstance(source, list):
            pieces = source
        cuts = []
        for p in pieces or []:
            if not isinstance(p, dict):
                continue
            length = p.get("length_mm", p.get("length", 0))
            qty = p.get("qty", p.get("quantity", 1))
            try:
                length_f = float(length)
                qty_i = int(qty)
            except (TypeError, ValueError):
                continue
            if length_f <= 0 or qty_i <= 0:
                continue
            cuts.append({
                "profile": str(p.get("profile") or default_profile).strip() or default_profile,
                "element": str(p.get("element") or p.get("label") or "").strip(),
                "length_mm": length_f,
                "ang_sx": float(p.get("ang_sx", p.get("ax", 0.0)) or 0.0),
                "ang_dx": float(p.get("ang_dx", p.get("ad", 0.0)) or 0.0),
                "qty": qty_i,
                "note": str(p.get("note") or ""),
            })
        return cuts
