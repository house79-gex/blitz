from __future__ import annotations
from typing import Dict, Any, List, Optional

from ui_qt.services.legacy_formula import eval_formula

def compute_lamelle(H: float, rules: List[Dict[str, Any]]) -> Dict[str, Any]:
    for r in rules:
        if float(r["h_min"]) <= H <= float(r["h_max"]):
            return {"count": int(r.get("count") or 0), "pitch": (r.get("pitch_mm") if r.get("pitch_mm") is not None else None)}
    return {"count": 0, "pitch": None}

def compute_astina_for_hw(H: float, L: float, handle_offset: float, formula: str) -> float:
    env = {"H": float(H), "L": float(L), "handle_offset": float(handle_offset)}
    return float(eval_formula(formula, env))
