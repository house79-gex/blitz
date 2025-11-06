from __future__ import annotations
from typing import List, Dict, Tuple

def _bar_used_length(bar: List[Dict[str, float]], kerf: float) -> float:
    if not bar:
        return 0.0
    total_len = sum(float(p.get("len", 0.0)) for p in bar)
    joints = max(len(bar) - 1, 0)
    return total_len + joints * float(kerf)

def _residuals(bars: List[List[Dict[str, float]]], stock: float, kerf: float) -> List[float]:
    return [max(float(stock) - _bar_used_length(b, kerf), 0.0) for b in bars]

def _order_with_max_residual_last(bars: List[List[Dict[str, float]]], stock: float, kerf: float) -> Tuple[List[List[Dict[str, float]]], List[float]]:
    if not bars:
        return bars, []
    res = _residuals(bars, stock, kerf)
    if not res:
        return bars, []
    max_idx = max(range(len(res)), key=lambda i: res[i])
    if max_idx != len(bars) - 1:
        last_bar = bars.pop(max_idx); bars.append(last_bar)
    res = _residuals(bars, stock, kerf)
    return bars, res

def refine_tail_ilp(bars: List[List[Dict[str, float]]],
                    stock: float,
                    kerf: float,
                    tail_bars: int = 6,
                    time_limit_s: int = 25) -> Tuple[List[List[Dict[str, float]]], List[float]]:
    """
    Refine pass locale sulle ultime 'tail_bars' barre con una MILP:
    - Minimizza #barre usate, massimizza materiale usato nelle barre attive
    - Rispetta il kerf: sum(L) + kerf*(n_pezzi - z_barra) <= stock
    Requisiti: PuLP. Se non disponibile, ritorna barre/residui originali.
    """
    try:
        import pulp  # type: ignore
    except Exception:
        return _order_with_max_residual_last(list(bars), stock, kerf)

    if not bars or tail_bars <= 0:
        return _order_with_max_residual_last(list(bars), stock, kerf)

    n = len(bars)
    start = max(0, n - int(tail_bars))
    head = [list(b) for b in bars[:start]]
    tail = [list(b) for b in bars[start:]]

    items: List[Dict[str, float]] = []
    for b in tail:
        for p in b:
            items.append(dict(p))
    if not items:
        return _order_with_max_residual_last(list(bars), stock, kerf)

    K = len(tail)
    J = len(items)
    lengths = [float(p.get("len", 0.0)) for p in items]
    kerf = float(kerf)
    stock = float(stock)

    prob = pulp.LpProblem("tail_refine", pulp.LpMinimize)

    x = pulp.LpVariable.dicts("x", (range(J), range(K)), lowBound=0, upBound=1, cat=pulp.LpBinary)
    y = pulp.LpVariable.dicts("y", range(K), lowBound=0, cat=pulp.LpInteger)
    z = pulp.LpVariable.dicts("z", range(K), lowBound=0, upBound=1, cat=pulp.LpBinary)

    for j in range(J):
        prob += pulp.lpSum(x[j][k] for k in range(K)) == 1, f"assign_{j}"

    BIGM = J
    for k in range(K):
        prob += y[k] == pulp.lpSum(x[j][k] for j in range(J)), f"y_def_{k}"
        prob += y[k] <= BIGM * z[k], f"use_link_{k}"
        prob += (
            pulp.lpSum(lengths[j] * x[j][k] for j in range(J)) + kerf * (y[k] - z[k]) <= stock
        ), f"cap_{k}"

    W = 1_000_000
    objective = W * pulp.lpSum(z[k] for k in range(K)) - pulp.lpSum(lengths[j] * x[j][k] for j in range(J) for k in range(K))
    prob += objective

    try:
        solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=int(time_limit_s))
    except Exception:
        solver = None

    try:
        prob.solve(solver) if solver else prob.solve()
    except Exception:
        return _order_with_max_residual_last(list(bars), stock, kerf)

    new_tail: List[List[Dict[str, float]]] = [[] for _ in range(K)]
    for j in range(J):
        k_ass = None
        for k in range(K):
            v = x[j][k].value()
            if v is not None and v > 0.5:
                k_ass = k
                break
        if k_ass is None:
            k_ass = 0
        new_tail[k_ass].append(items[j])

    refined_tail = []
    for k in range(K):
        zk = z[k].value() or 0.0
        if zk > 0.5 and new_tail[k]:
            refined_tail.append(new_tail[k])

    out = head + refined_tail
    return _order_with_max_residual_last(out, stock, kerf)

def pack_bars_knapsack_ilp(pieces: List[Dict[str, float]],
                           stock: float,
                           kerf: float,
                           per_bar_time_s: int = 3) -> Tuple[List[List[Dict[str, float]]], List[float]]:
    """
    Costruisce le barre iterativamente risolvendo un knapsack ILP per OGNI barra:
    - Variabili x_j in {0,1} per selezionare i pezzi di questa barra
    - y = somma x_j, z binaria: se y>=1 allora z=1
    - Capacità: sum(L_j x_j) + kerf*(y - z) <= stock (kerf sui giunti: y-1 se y>=1)
    - Obiettivo: massimizzare sum(L_j x_j)
    Se PuLP non è disponibile: ritorna ([], []) così il chiamante può fallback a BFD.
    """
    try:
        import pulp  # type: ignore
    except Exception:
        return [], []

    remaining = [dict(p) for p in pieces]
    bars: List[List[Dict[str, float]]] = []

    while remaining:
        J = len(remaining)
        lengths = [float(p.get("len", 0.0)) for p in remaining]
        prob = pulp.LpProblem("bar_knapsack", pulp.LpMaximize)

        x = pulp.LpVariable.dicts("x", range(J), lowBound=0, upBound=1, cat=pulp.LpBinary)
        y = pulp.LpVariable("y", lowBound=0, cat=pulp.LpInteger)
        z = pulp.LpVariable("z", lowBound=0, upBound=1, cat=pulp.LpBinary)

        prob += y == pulp.lpSum(x[j] for j in range(J)), "y_def"
        prob += y <= J * z, "use_link_le"
        prob += y >= z, "use_link_ge"
        prob += pulp.lpSum(lengths[j] * x[j] for j in range(J)) + float(kerf) * (y - z) <= float(stock), "capacity"

        prob += pulp.lpSum(lengths[j] * x[j] for j in range(J)), "objective"

        try:
            solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=int(per_bar_time_s))
        except Exception:
            solver = None

        try:
            prob.solve(solver) if solver else prob.solve()
        except Exception:
            # In caso di problemi, interrompi la costruzione e restituisci quanto fatto
            break

        # Estrai i pezzi selezionati per questa barra
        chosen_idx = [j for j in range(J) if (x[j].value() or 0.0) > 0.5]
        if not chosen_idx:
            # Nessun pezzo selezionato (può succedere per limiti solver) -> inserisci 1 pezzo max
            best_j = max(range(J), key=lambda j: lengths[j])
            chosen_idx = [best_j]

        bar = [remaining[j] for j in chosen_idx]
        bars.append(bar)

        # Rimuovi i selezionati
        mask = set(chosen_idx)
        remaining = [remaining[j] for j in range(J) if j not in mask]

    # Calcola residui e ordina l'ultima barra come quella con residuo massimo
    return _order_with_max_residual_last(bars, float(stock), float(kerf))
