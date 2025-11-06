from __future__ import annotations
from typing import List, Dict, Tuple, Optional

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

    Requisiti: PuLP disponibile. In assenza, ritorna barre/residui originali.
    """
    try:
        import pulp  # type: ignore
    except Exception:
        # PuLP non disponibile → nessuna refine
        return _order_with_max_residual_last(list(bars), stock, kerf)

    if not bars or tail_bars <= 0:
        return _order_with_max_residual_last(list(bars), stock, kerf)

    n = len(bars)
    start = max(0, n - int(tail_bars))
    head = [list(b) for b in bars[:start]]
    tail = [list(b) for b in bars[start:]]

    # Colleziona item del tail (mantieni dict per intero, ma usi solo len nel modello)
    items: List[Dict[str, float]] = []
    for b in tail:
        for p in b:
            items.append(dict(p))
    if not items:
        return _order_with_max_residual_last(list(bars), stock, kerf)

    # Numero massimo di barre nel tail: tieni K uguale al numero di barre originali del tail
    K = len(tail)
    J = len(items)
    lengths = [float(p.get("len", 0.0)) for p in items]
    kerf = float(kerf)
    stock = float(stock)

    # Modello
    prob = pulp.LpProblem("tail_refine", pulp.LpMinimize)

    # Variabili
    x = pulp.LpVariable.dicts("x", (range(J), range(K)), lowBound=0, upBound=1, cat=pulp.LpBinary)
    y = pulp.LpVariable.dicts("y", range(K), lowBound=0, cat=pulp.LpInteger)  # numero pezzi sulla barra k
    z = pulp.LpVariable.dicts("z", range(K), lowBound=0, upBound=1, cat=pulp.LpBinary)  # barra usata

    # Vincoli: ogni item assegnato a una barra
    for j in range(J):
        prob += pulp.lpSum(x[j][k] for k in range(K)) == 1, f"assign_{j}"

    BIGM = J  # limite superiore per y
    for k in range(K):
        # y_k = somma pezzi sulla barra k
        prob += y[k] == pulp.lpSum(x[j][k] for j in range(J)), f"y_def_{k}"
        # y_k <= M * z_k
        prob += y[k] <= BIGM * z[k], f"use_link_{k}"
        # Capacità: sum(L) + kerf*(y_k - z_k) <= stock
        prob += (
            pulp.lpSum(lengths[j] * x[j][k] for j in range(J)) + kerf * (y[k] - z[k]) <= stock
        ), f"cap_{k}"

    # Obiettivo: minimizza W * sum(z_k) - sum(sum(L_j x_jk)) per favorire densità
    W = 1_000_000
    objective = W * pulp.lpSum(z[k] for k in range(K)) - pulp.lpSum(lengths[j] * x[j][k] for j in range(J) for k in range(K))
    prob += objective

    # Solver
    try:
        solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=int(time_limit_s))
    except Exception:
        solver = None

    try:
        prob.solve(solver) if solver else prob.solve()
    except Exception:
        # in caso di errori: ritorna originale
        return _order_with_max_residual_last(list(bars), stock, kerf)

    # Ricostruisci barre del tail dall'assegnamento
    new_tail: List[List[Dict[str, float]]] = [[] for _ in range(K)]
    for j in range(J):
        # trova la barra k assegnata
        k_ass = None
        for k in range(K):
            v = x[j][k].value()
            if v is not None and v > 0.5:
                k_ass = k
                break
        if k_ass is None:
            # fallback (non dovrebbe accadere)
            k_ass = 0
        new_tail[k_ass].append(items[j])

    # Filtra barre vuote (z_k ~ 0)
    refined_tail = []
    for k in range(K):
        zk = z[k].value() or 0.0
        if zk > 0.5 and new_tail[k]:
            refined_tail.append(new_tail[k])

    # Unisci head + refined_tail e rimetti la barra con residuo massimo per ultima
    out = head + refined_tail
    return _order_with_max_residual_last(out, stock, kerf)
