from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple

def compute_lamelle(H: float, rules: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calcolo lamelle persiane in base a una tabella 'rules':
    rules: [{h_min, h_max, count, pitch_mm?}]
    Ritorna: {"count": N, "pitch": passo_opzionale}
    """
    for r in rules:
        if float(r["h_min"]) <= H <= float(r["h_max"]):
            return {"count": int(r.get("count") or 0), "pitch": (r.get("pitch_mm") if r.get("pitch_mm") is not None else None)}
    # fallback: interpola o default
    return {"count": 0, "pitch": None}

def compute_astine_anta_ribalta(H: float, L: float, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Calcolo 'astine' ferramenta anta-ribalta (semplificato/parametrico).
    params può contenere soglie/offset, es:
      {"min_len": 200, "max_len": 1200, "count_per_sash": 2, "note": "..."}
    Ritorna lista parti: [{id, nome, qty, length_mm, note}]
    """
    p = params or {}
    min_len = float(p.get("min_len", 200))
    max_len = float(p.get("max_len", 1200))
    count_per_sash = int(p.get("count_per_sash", 2))
    # esempio: lunghezza astina ~ H - 2*35 (cerniere/clearance)
    length = max(min_len, min(H - 70.0, max_len))
    return [{
        "id": "AST-AR",
        "nome": "Astina anta-ribalta",
        "qty": count_per_sash,
        "length_mm": float(length),
        "note": str(p.get("note", "")),
    }]
