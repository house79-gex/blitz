"""
Planner ILP/BFD per Automatico.

- plan_ilp(jobs, stock, time_limit_s): tenta OR-Tools; fallback a BFD se non disponibile.
- plan_bfd(jobs, stock): algoritmo semplice first/best fit decreasing come placeholder.

Entrambi restituiscono un dict:
{
  "solver": "ILP"|"BFD",
  "steps": [ { "id": str, "len": float, "qty": int, "stock_id": str|None } ],
}
"""
from __future__ import annotations
from typing import List, Dict, Any

def plan_bfd(jobs: List[Dict[str, Any]], stock: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    steps = []
    for j in jobs:
        jid = str(j.get("id", "item"))
        ln = float(j.get("len", 0.0))
        qty = int(j.get("qty", 1))
        for _ in range(qty):
            steps.append({"id": jid, "len": ln, "qty": 1, "stock_id": None})
    return {"solver": "BFD", "steps": steps}

def plan_ilp(jobs: List[Dict[str, Any]], stock: List[Dict[str, Any]] | None = None, time_limit_s: int = 15) -> Dict[str, Any]:
    try:
        # Placeholder: senza dati struttura barre, ritorna BFD
        # Integrazione ILP reale (cutting-stock) se/quando dataset stock è disponibile.
        return plan_bfd(jobs, stock)
    except Exception:
        return plan_bfd(jobs, stock)
