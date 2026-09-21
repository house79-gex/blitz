"""Decisioni di avanzamento e ordinamento barre nel piano Automatico."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

# Sotto questa soglia il pezzo non è tagliabile / non va in sequenza
MIN_CUT_LEN_MM = 0.5


def decide_plan_advance(
    cur: Optional[Dict[str, Any]],
    nxt: Optional[Dict[str, Any]],
    *,
    auto_across_bars: bool = False,
) -> str:
    """
    Decide il passo dopo un taglio nel piano ottimizzato.

    Restituisce:
    - ``done``: piano esaurito
    - ``wait_bar``: serve un nuovo blocco, attesa Start (F9)
    - ``skip_move``: stesso pezzo (quota/angoli), solo taglio successivo
    - ``move``: sblocca freno, riposiziona, blocca, taglia
    """
    if not nxt:
        return "done"
    same_bar = bool(cur) and cur.get("bar") == nxt.get("bar")
    if not same_bar and not auto_across_bars:
        return "wait_bar"
    if cur and (
        abs(float(cur.get("len", 0.0)) - float(nxt.get("len", 0.0))) <= 0.05
        and abs(float(cur.get("ax", 0.0)) - float(nxt.get("ax", 0.0))) <= 0.05
        and abs(float(cur.get("ad", 0.0)) - float(nxt.get("ad", 0.0))) <= 0.05
        and str(cur.get("profile", "")) == str(nxt.get("profile", ""))
    ):
        return "skip_move"
    return "move"


def piece_cut_length_mm(piece: Dict[str, Any]) -> float:
    """Quota di taglio nominale del pezzo (mm)."""
    try:
        return float(piece.get("len", piece.get("length_mm", piece.get("length", 0.0))) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def is_valid_cut_piece(piece: Dict[str, Any], min_len_mm: float = MIN_CUT_LEN_MM) -> bool:
    """True se il pezzo ha una quota tagliabile (> soglia)."""
    return piece_cut_length_mm(piece) > float(min_len_mm)


def filter_valid_pieces(
    pieces: Sequence[Dict[str, Any]],
    min_len_mm: float = MIN_CUT_LEN_MM,
) -> List[Dict[str, Any]]:
    """Esclude pezzi con quota zero/negativa (o sotto soglia)."""
    return [p for p in pieces if is_valid_cut_piece(p, min_len_mm)]


def sanitize_bars(
    bars: Sequence[Sequence[Dict[str, Any]]],
    min_len_mm: float = MIN_CUT_LEN_MM,
) -> List[List[Dict[str, Any]]]:
    """
    Rimuove da ogni barra i pezzi a quota ~0 e scarta barre vuote.
    Lo sfrido resta spazio vuoto (non un pezzo da tagliare).
    """
    out: List[List[Dict[str, Any]]] = []
    for bar in bars:
        cleaned = [dict(p) for p in bar if is_valid_cut_piece(p, min_len_mm)]
        if cleaned:
            out.append(cleaned)
    return out


def reorder_bars_for_cut(
    bars: Sequence[Sequence[Dict[str, Any]]],
    residuals_mm: Optional[Sequence[float]] = None,
) -> List[List[Dict[str, Any]]]:
    """
    Ordina le barre per l'esecuzione (solo misure, non sfrido):

    - pezzi dentro ogni barra: più lungo → più corto
    - barre: per pezzo più lungo a decrescere

    ``residuals_mm`` è ignorato (compatibilità firma); lo sfrido non
    influenza l'ordine di taglio.
    """
    del residuals_mm  # non usato: priorità solo alle misure
    if not bars:
        return []

    prepared: List[tuple] = []
    for bar in bars:
        # Esclude pezzi a quota ~0 anche se il chiamante non ha sanitizzato
        pieces = [dict(p) for p in bar if is_valid_cut_piece(p)]
        if not pieces:
            continue
        pieces.sort(
            key=lambda p: (
                -piece_cut_length_mm(p),
                float(p.get("ax", 0.0) or 0.0),
                float(p.get("ad", 0.0) or 0.0),
            )
        )
        max_len = max((piece_cut_length_mm(p) for p in pieces), default=0.0)
        total_len = sum(piece_cut_length_mm(p) for p in pieces)
        prepared.append((pieces, max_len, total_len))

    # Barre: prima quelle col pezzo più lungo; a parità più materiale usato
    prepared.sort(key=lambda t: (t[1], t[2]), reverse=True)
    return [t[0] for t in prepared]
