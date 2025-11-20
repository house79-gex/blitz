"""
Modulo di ottimizzazione / raffinamento piano di taglio
File: qt6_app/ui_qt/logic/refiner.py
Date: 2025-11-20
Author: house79-gex

Contiene:
- pack_bars_knapsack_ilp: packing di pezzi in barre (usa ILP se disponibile, fallback greedy).
- refine_tail_ilp: raffinamento delle ultime barre (ri-ottimizzazione locale).
- joint_consumption: consumo tra due pezzi consecutivi (kerf, ripasso).
- bar_used_length / residuals: calcolo lunghezze utilizzate e sfridi.
- compute_bar_breakdown: breakdown dettagliato consumi per una barra.
- Funzioni di utilità già presenti in versione semplificata (refine_plan, ecc.).

Tutte le funzioni sono pensate per essere “side-effect free”.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Dict, List, Tuple, Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Parametri di default (possono essere sovrascritti dai settings esterni)
# ---------------------------------------------------------------------------
DEFAULT_KERF_MM = 3.0
DEFAULT_RIPASSO_MM = 0.0

# ---------------------------------------------------------------------------
# Utility di base per pezzi
# Ogni pezzo è un dict atteso con chiavi: len, ax, ad, (opzionali profile, element, meta)
# ---------------------------------------------------------------------------

def _effective_piece_length(piece: Dict[str, Any],
                            thickness_mm: float = 0.0) -> float:
    """
    Calcola la lunghezza efficace di posizionamento tenendo conto degli angoli e dello spessore (taglio obliquo).
    Se thickness_mm <= 0, ritorna semplicemente piece['len'].
    """
    L = float(piece.get("len", 0.0))
    if thickness_mm <= 0.0:
        return max(0.0, L)
    ax = abs(float(piece.get("ax", 0.0)))
    ad = abs(float(piece.get("ad", 0.0)))
    try:
        c_sx = thickness_mm * math.tan(math.radians(ax))
    except Exception:
        c_sx = 0.0
    try:
        c_dx = thickness_mm * math.tan(math.radians(ad))
    except Exception:
        c_dx = 0.0
    return max(0.0, L - max(0.0, c_sx) - max(0.0, c_dx))

def _angles_signature(piece: Dict[str, Any]) -> Tuple[float, float]:
    return (float(piece.get("ax", 0.0)), float(piece.get("ad", 0.0)))


# ---------------------------------------------------------------------------
# joint_consumption
# ---------------------------------------------------------------------------
def joint_consumption(prev_piece: Dict[str, Any],
                      kerf_base: float,
                      ripasso_mm: float,
                      reversible: bool,
                      thickness_mm: float,
                      angle_tol: float,
                      max_angle: float,
                      max_factor: float) -> Tuple[float, Dict[str, Any]]:
    """
    Calcola il consumo aggiuntivo tra il precedente pezzo e il successivo:
    - kerf “di separazione” (base o aumentato se angoli >= soglia).
    - ripasso (se >0).
    Ritorna (consumo_mm, dettagli).
    """
    if not prev_piece:
        return 0.0, {"kerf": 0.0, "ripasso": 0.0, "factor": 1.0}

    ax, ad = _angles_signature(prev_piece)
    # Fattore di aumento kerf se l'angolo supera max_angle (semplificato)
    factor = 1.0
    if abs(ax) > max_angle or abs(ad) > max_angle:
        factor = min(max_factor, 1.0 + (abs(ax) + abs(ad) - 2.0 * max_angle) / 180.0)

    kerf_here = kerf_base * factor
    consumo = kerf_here + max(0.0, ripasso_mm)
    return consumo, {"kerf": kerf_here, "ripasso": ripasso_mm, "factor": factor}


# ---------------------------------------------------------------------------
# bar_used_length
# ---------------------------------------------------------------------------
def bar_used_length(bar: List[Dict[str, Any]],
                    kerf_base: float,
                    ripasso_mm: float,
                    reversible: bool,
                    thickness_mm: float,
                    angle_tol: float,
                    max_angle: float,
                    max_factor: float) -> float:
    """
    Lunghezza usata (somma lunghezze efficaci + consumi di giunzione).
    """
    if not bar:
        return 0.0
    total = 0.0
    prev = None
    for piece in bar:
        eff_len = _effective_piece_length(piece, thickness_mm)
        total += eff_len
        if prev is not None:
            add, _ = joint_consumption(prev, kerf_base, ripasso_mm,
                                       reversible, thickness_mm,
                                       angle_tol, max_angle, max_factor)
            total += add
        prev = piece
    return total


# ---------------------------------------------------------------------------
# residuals
# ---------------------------------------------------------------------------
def residuals(bars: List[List[Dict[str, Any]]],
              stock: float,
              kerf_base: float,
              ripasso_mm: float,
              reversible: bool,
              thickness_mm: float,
              angle_tol: float,
              max_angle: float,
              max_factor: float) -> List[float]:
    """
    Calcola gli sfridi (residual) per ciascuna barra.
    """
    res = []
    for bar in bars:
        used = bar_used_length(bar, kerf_base, ripasso_mm,
                               reversible, thickness_mm,
                               angle_tol, max_angle, max_factor)
        res.append(max(0.0, stock - used))
    return res


# ---------------------------------------------------------------------------
# compute_bar_breakdown
# ---------------------------------------------------------------------------
def compute_bar_breakdown(bar: List[Dict[str, Any]],
                          kerf_base: float,
                          ripasso_mm: float,
                          reversible: bool,
                          thickness_mm: float,
                          angle_tol: float,
                          max_angle: float,
                          max_factor: float) -> Dict[str, Any]:
    """
    Ritorna breakdown dettagliato consumi:
    - used_total
    - kerf_proj_sum (somma solo kerf "giunzione")
    - ripasso_sum (somma ripassi)
    - recovery_sum (semplice: differenza da sum(len) - used? qui non praticato -> 0)
    """
    used_total = 0.0
    kerf_proj_sum = 0.0
    ripasso_sum = 0.0
    recovery_sum = 0.0

    prev = None
    for piece in bar:
        eff_len = _effective_piece_length(piece, thickness_mm)
        used_total += eff_len
        if prev is not None:
            add, detail = joint_consumption(prev, kerf_base, ripasso_mm,
                                            reversible, thickness_mm,
                                            angle_tol, max_angle, max_factor)
            used_total += add
            kerf_proj_sum += detail.get("kerf", 0.0)
            ripasso_sum += detail.get("ripasso", 0.0)
        prev = piece

    return {
        "used_total": used_total,
        "kerf_proj_sum": kerf_proj_sum,
        "ripasso_sum": ripasso_sum,
        "recovery_sum": recovery_sum,
    }


# ---------------------------------------------------------------------------
# pack_bars_knapsack_ilp
# ---------------------------------------------------------------------------
def pack_bars_knapsack_ilp(pieces: List[Dict[str, Any]],
                           stock: float,
                           kerf_base: float,
                           ripasso_mm: float,
                           conservative_angle_deg: float,
                           max_angle: float,
                           max_factor: float,
                           reversible: bool,
                           thickness_mm: float,
                           angle_tol: float,
                           per_bar_time_s: int = 15) -> Tuple[List[List[Dict[str, Any]]], List[float]]:
    """
    Packing di pezzi in barre:
    - Prova un modello knapsack iterativo (riempie una barra, poi rimuove i pezzi usati).
    - Fallback greedy se pulp non disponibile o errori.

    Ogni iterazione:
    - variabile x_i (0/1) se il pezzo i entra nella barra
    - constraint: somma(eff_len_i + kerf_incrementi) <= stock
      (approssimiamo kerf: kerf_base * (n_selected - 1) + ripasso_mm * (n_selected - 1))
    - obiettivo: massimizzare somma(eff_len_i)

    L’approssimazione è sufficiente per scenario base.
    """

    if not pieces:
        return [], []

    try:
        import pulp
        use_ilp = True
    except Exception:
        use_ilp = False

    # Precalcolo lunghezze efficaci
    eff_lengths = [ _effective_piece_length(p, thickness_mm) for p in pieces ]

    remaining_indices = list(range(len(pieces)))
    bars: List[List[Dict[str, Any]]] = []
    start_time_global = time.time()

    while remaining_indices:
        if use_ilp:
            try:
                # Tempo limite grezzo
                timeout = max(5, per_bar_time_s)
                model = pulp.LpProblem("BAR_PACK", pulp.LpMaximize)
                x_vars = {
                    i: pulp.LpVariable(f"x_{i}", lowBound=0, upBound=1, cat=pulp.LpBinary)
                    for i in remaining_indices
                }
                # Approccio: sum(eff_len_i * x_i) + (kerf_base + ripasso_mm)*(sum(x_i)-1) <= stock
                # => sum(eff_len_i * x_i) + (kerf_base + ripasso_mm)*sum(x_i) - (kerf_base + ripasso_mm) <= stock
                M = kerf_base + max(0.0, ripasso_mm)

                model += pulp.lpSum([eff_lengths[i] * x_vars[i] for i in remaining_indices]), "MaxEffLen"

                model += (pulp.lpSum([eff_lengths[i] * x_vars[i] for i in remaining_indices])
                          + M * pulp.lpSum([x_vars[i] for i in remaining_indices])
                          - M) <= stock, "StockConstraintApprox"

                # Risoluzione
                solver = pulp.PULP_CBC_CMD(timeLimit=timeout, msg=False)
                model.solve(solver)

                selected = [i for i in remaining_indices if pulp.value(x_vars[i]) >= 0.9]

                if not selected:
                    # Nessun pezzo entrato -> prendi il più lungo come fallback
                    sel_longest = max(remaining_indices, key=lambda idx: eff_lengths[idx])
                    selected = [sel_longest]

                bar_pieces = [pieces[i] for i in selected]
                bars.append(bar_pieces)
                # Rimuovi selected
                remaining_indices = [i for i in remaining_indices if i not in selected]
                continue
            except Exception as e:
                logger.warning(f"ILP packing error, fallback greedy: {e}")
                use_ilp = False  # ripiega al greedy

        # Greedy fallback: ordina per lunghezza effettiva desc
        remaining_indices.sort(key=lambda i: eff_lengths[i], reverse=True)
        current_bar = []
        used_len = 0.0
        prev_piece = None
        to_drop = []
        for i in remaining_indices:
            eff = eff_lengths[i]
            extra = 0.0
            if prev_piece is not None:
                add, _ = joint_consumption(prev_piece, kerf_base, ripasso_mm,
                                           reversible, thickness_mm, angle_tol,
                                           max_angle, max_factor)
                extra = add
            if used_len + eff + (extra if prev_piece else 0.0) <= stock + 1e-6:
                if prev_piece is not None:
                    used_len += extra
                used_len += eff
                current_bar.append(pieces[i])
                prev_piece = pieces[i]
                to_drop.append(i)
        if not current_bar:
            # Prendi almeno il primo pezzo rimanente
            first = remaining_indices[0]
            current_bar = [pieces[first]]
            to_drop = [first]
        bars.append(current_bar)
        remaining_indices = [i for i in remaining_indices if i not in to_drop]

        # Safety break
        if time.time() - start_time_global > 60:
            logger.warning("Packing interrotto per timeout globale (60s).")
            break

    res = residuals(bars, stock, kerf_base, ripasso_mm, reversible, thickness_mm, angle_tol, max_angle, max_factor)
    return bars, res


# ---------------------------------------------------------------------------
# refine_tail_ilp
# ---------------------------------------------------------------------------
def refine_tail_ilp(bars: List[List[Dict[str, Any]]],
                    stock: float,
                    kerf_base: float,
                    ripasso_mm: float,
                    reversible: bool,
                    thickness_mm: float,
                    angle_tol: float,
                    tail_bars: int,
                    time_limit_s: int,
                    max_angle: float,
                    max_factor: float) -> Tuple[List[List[Dict[str, Any]]], List[float]]:
    """
    Raffina soltanto le ultime 'tail_bars' barre:
    - Prende i pezzi dalle ultime barre
    - Li rimette in un pool
    - Fa un repacking (uso pack_bars_knapsack_ilp in mini)
    - Sostituisce le ultime barre con il nuovo risultato se migliore.
    """
    if tail_bars <= 0 or not bars:
        return bars, residuals(bars, stock, kerf_base, ripasso_mm, reversible, thickness_mm, angle_tol, max_angle, max_factor)

    n = len(bars)
    start_tail = max(0, n - tail_bars)
    tail_segment = bars[start_tail:]
    flat_pieces = []
    for b in tail_segment:
        flat_pieces.extend(b)

    if not flat_pieces:
        return bars, residuals(bars, stock, kerf_base, ripasso_mm, reversible, thickness_mm, angle_tol, max_angle, max_factor)

    # Repack solo quei pezzi (limitando tempo)
    new_bars, _ = pack_bars_knapsack_ilp(
        pieces=flat_pieces,
        stock=stock,
        kerf_base=kerf_base,
        ripasso_mm=ripasso_mm,
        conservative_angle_deg=45.0,
        max_angle=max_angle,
        max_factor=max_factor,
        reversible=reversible,
        thickness_mm=thickness_mm,
        angle_tol=angle_tol,
        per_bar_time_s=min(time_limit_s, 10)  # riduco tempo per singolo pass
    )

    # Valuta se migliorano (somma sfridi totale)
    old_res = sum(residuals(tail_segment, stock, kerf_base, ripasso_mm,
                            reversible, thickness_mm, angle_tol, max_angle, max_factor))
    new_res = sum(residuals(new_bars, stock, kerf_base, ripasso_mm,
                            reversible, thickness_mm, angle_tol, max_angle, max_factor))

    if new_res <= old_res + 1e-6:
        # Miglioramento (o uguale) → sostituisci
        bars = bars[:start_tail] + new_bars
        logger.info(f"Raffinamento tail: sfrido tail da {old_res:.2f} a {new_res:.2f} mm.")
    else:
        logger.info(f"Raffinamento tail scartato (nuovo sfrido {new_res:.2f} > {old_res:.2f}).")

    final_res = residuals(bars, stock, kerf_base, ripasso_mm,
                          reversible, thickness_mm, angle_tol, max_angle, max_factor)
    return bars, final_res


# ---------------------------------------------------------------------------
# Funzioni di raffinamento “descrittivo” (compatibilità con versione semplificata)
# ---------------------------------------------------------------------------
def refine_plan(plan: Dict, kerf: float = DEFAULT_KERF_MM, ripasso: float = DEFAULT_RIPASSO_MM, recupero: bool = True) -> Dict:
    """
    Raffina un piano “strutturato” (schema: {bars:[{length:int, jobs:[{length, angle_sx, angle_dx}]}]} )
    Aggiunge attributi: waste, efficiency, recoverable_pieces ecc.
    """
    if not plan or 'bars' not in plan:
        return plan

    out = plan.copy()
    refined_bars = []
    total_waste = 0.0
    recoverable = []

    for b in plan.get("bars", []):
        # copia
        rb = b.copy()
        jobs_ref = []
        for job in b.get("jobs", []):
            rj = job.copy()
            original = rj.get("length", 0.0)
            rj["original_length"] = original
            rj["actual_length"] = original + ripasso
            rj["kerf"] = kerf
            jobs_ref.append(rj)
        rb["jobs"] = jobs_ref

        used = calculate_used_length(rb, kerf)
        Lbar = float(rb.get("length", 0.0))
        waste = max(0.0, Lbar - used)
        rb["used_length"] = used
        rb["waste"] = waste
        rb["efficiency"] = (used / Lbar * 100.0) if Lbar > 0 else 0.0
        if recupero and waste >= 100.0:
            recoverable.append({
                "bar_id": rb.get("id"),
                "length": waste - kerf,
                "type": "scrap"
            })

        total_waste += waste
        refined_bars.append(rb)

    out["bars"] = refined_bars
    out["total_waste"] = total_waste
    out["recoverable_pieces"] = recoverable
    out["refinement_params"] = {
        "kerf": kerf,
        "ripasso": ripasso,
        "recupero": recupero
    }
    return out


def refine_bar(bar: Dict, kerf: float, ripasso: float) -> Dict:
    """
    Raffina una singola barra (compatibilità).
    """
    rb = bar.copy()
    new_jobs = []
    for job in bar.get("jobs", []):
        rj = job.copy()
        orig = rj.get("length", 0.0)
        rj["original_length"] = orig
        rj["actual_length"] = orig + ripasso
        rj["kerf"] = kerf
        rj["ripasso"] = ripasso
        rj["cut_compensation"] = calculate_cut_compensation(
            rj.get("angle_sx", 90), rj.get("angle_dx", 90), kerf
        )
        new_jobs.append(rj)
    rb["jobs"] = new_jobs
    return rb


def calculate_used_length(bar: Dict, kerf: float) -> float:
    """
    Calcolo semplificato (compatibilità).
    """
    jobs = bar.get("jobs", [])
    total = 0.0
    for i, job in enumerate(jobs):
        total += job.get("actual_length", job.get("length", 0.0))
        if i < len(jobs) - 1:
            total += kerf
    return total


def calculate_cut_compensation(angle_sx: float, angle_dx: float, kerf: float) -> Dict[str, float]:
    """
    Compensazione semplificata per tagli obliqui.
    """
    comp = {"sx": 0.0, "dx": 0.0}
    try:
        if angle_sx != 90:
            comp["sx"] = kerf / (2 * math.sin(math.radians(angle_sx))) if math.sin(math.radians(angle_sx)) != 0 else 0.0
    except Exception:
        comp["sx"] = 0.0
    try:
        if angle_dx != 90:
            comp["dx"] = kerf / (2 * math.sin(math.radians(angle_dx))) if math.sin(math.radians(angle_dx)) != 0 else 0.0
    except Exception:
        comp["dx"] = 0.0
    return comp


def optimize_for_material(plan: Dict, material_type: str = 'aluminum') -> Dict:
    """
    Ottimizzazione base per parametri di materiale.
    """
    material_params = {
        'aluminum': dict(cutting_speed=100, feed_rate=50, coolant=True, blade_type='carbide'),
        'steel': dict(cutting_speed=50, feed_rate=25, coolant=True, blade_type='hss'),
        'wood': dict(cutting_speed=150, feed_rate=75, coolant=False, blade_type='wood'),
    }
    params = material_params.get(material_type, material_params['aluminum'])
    out = plan.copy()
    out['material'] = material_type
    out['cutting_params'] = params
    total_time = 0.0
    for bar in out.get("bars", []):
        for job in bar.get("jobs", []):
            L = float(job.get("length", 0.0))
            feed = float(params['feed_rate'])
            t = (L / feed) * 60.0 if feed > 0 else 0.0
            job['estimated_time'] = t
            total_time += t
    out['total_estimated_time'] = total_time
    return out


def group_by_angle(plan: Dict) -> Dict:
    """
    Raggruppa i tagli di ogni barra per tuple di angoli (sx, dx).
    """
    out = plan.copy()
    for bar in out.get("bars", []):
        jobs = list(bar.get("jobs", []))
        groups: Dict[Tuple[float, float], List[Dict[str, Any]]] = {}
        for job in jobs:
            k = (float(job.get("angle_sx", 90)), float(job.get("angle_dx", 90)))
            groups.setdefault(k, []).append(job)
        ordered = []
        for k in sorted(groups.keys()):
            ordered.extend(groups[k])
        bar["jobs"] = ordered
        bar["angle_changes"] = max(0, len(groups) - 1)
    return out


def add_setup_operations(plan: Dict) -> Dict:
    """
    Aggiunge operazioni di setup (cambio angolo) tra jobs.
    """
    out = plan.copy()
    for bar in out.get("bars", []):
        new_list = []
        last_angles = (90.0, 90.0)
        for job in bar.get("jobs", []):
            angles = (float(job.get("angle_sx", 90)), float(job.get("angle_dx", 90)))
            if angles != last_angles:
                setup = {
                    "type": "setup",
                    "operation": "angle_change",
                    "from_angles": last_angles,
                    "to_angles": angles,
                    "estimated_time": 30
                }
                new_list.append(setup)
            new_list.append(job)
            last_angles = angles
        bar["jobs_with_setup"] = new_list
    return out


def validate_plan(plan: Dict) -> Tuple[bool, List[str]]:
    """
    Validazione base del piano (presenza barre, lunghezze > 0, ecc.).
    """
    errors: List[str] = []
    if not plan:
        return False, ["Piano vuoto"]
    bars = plan.get("bars")
    if bars is None:
        return False, ["Piano senza barre"]
    if not bars:
        return False, ["Nessuna barra nel piano"]
    for i, bar in enumerate(bars):
        if float(bar.get("length", 0.0)) <= 0.0:
            errors.append(f"Barra {i+1}: lunghezza non valida")
        jobs = bar.get("jobs", [])
        if not jobs:
            errors.append(f"Barra {i+1}: nessun taglio definito")
        tot_len = 0.0
        for j, job in enumerate(jobs):
            L = float(job.get("length", 0.0))
            if L <= 0.0:
                errors.append(f"Barra {i+1} Taglio {j+1}: lunghezza non valida")
            tot_len += L
            ax = float(job.get("angle_sx", 90))
            ad = float(job.get("angle_dx", 90))
            if not (0.0 < ax <= 180.0):
                errors.append(f"Barra {i+1} Taglio {j+1}: angolo SX non valido")
            if not (0.0 < ad <= 180.0):
                errors.append(f"Barra {i+1} Taglio {j+1}: angolo DX non valido")
        if tot_len > float(bar.get("length", 0.0)) + 1e-6:
            errors.append(f"Barra {i+1}: somma tagli ({tot_len}) > lunghezza barra ({bar.get('length', 0.0)})")
    return len(errors) == 0, errors


def merge_small_scraps(plan: Dict, min_length: float = 100.0) -> Dict:
    """
    Unisce sfridi piccoli in gruppi recuperabili.
    """
    out = plan.copy()
    scraps = []
    for bar in out.get("bars", []):
        waste = float(bar.get("waste", 0.0))
        if waste > 0:
            scraps.append({"bar_id": bar.get("id"), "length": waste})
    scraps.sort(key=lambda x: x["length"], reverse=True)
    merged = []
    group = []
    total = 0.0
    for sc in scraps:
        if sc["length"] >= min_length:
            merged.append(sc)
        else:
            group.append(sc)
            total += sc["length"]
            if total >= min_length:
                merged.append({
                    "bar_ids": [g["bar_id"] for g in group],
                    "length": total,
                    "type": "merged_scrap"
                })
                group = []
                total = 0.0
    out["optimized_scraps"] = merged
    return out


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------
__all__ = [
    # Packing / raffinamento avanzato
    "pack_bars_knapsack_ilp",
    "refine_tail_ilp",
    "joint_consumption",
    "bar_used_length",
    "residuals",
    "compute_bar_breakdown",
    # Compatibilità funzioni semplificate
    "refine_plan",
    "refine_bar",
    "calculate_used_length",
    "calculate_cut_compensation",
    "optimize_for_material",
    "group_by_angle",
    "add_setup_operations",
    "validate_plan",
    "merge_small_scraps",
]
