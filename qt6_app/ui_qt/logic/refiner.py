from __future__ import annotations
from typing import List, Dict, Tuple
import math

# ============================================================
# Calcoli kerf angolare + ripasso + recupero reversibile (automatico)
# ============================================================

def _cosd(a: float) -> float:
    try:
        return math.cos(math.radians(float(a)))
    except Exception:
        return 1.0

def kerf_projected(kerf_base: float,
                   ang_deg: float,
                   max_angle: float,
                   max_factor: float) -> float:
    """
    Kerf proiettato lungo l'asse barra per un taglio inclinato.
    kerf_eff = kerf_base / cos(|ang|) con clamp di angolo e fattore.
    """
    try:
        a = abs(float(ang_deg))
    except Exception:
        a = 0.0
    a = min(a, max_angle)
    c = _cosd(a)
    if c <= 1e-6:
        return kerf_base * max_factor
    val = kerf_base / c
    return min(val, kerf_base * max_factor)

def auto_recovery(thickness_mm: float,
                  ax: float,
                  ad: float,
                  angle_tol: float) -> float:
    """
    Recupero automatico per profilo reversibile:
    Se almeno uno dei due angoli (ax o ad) è a 45° (entro tolleranza) → recupero = thickness_mm.
    Altrimenti 0.
    """
    if thickness_mm <= 0:
        return 0.0
    try:
        ax_v = abs(float(ax)); ad_v = abs(float(ad))
    except Exception:
        ax_v = ad_v = 0.0
    if (abs(ax_v - 45.0) <= angle_tol) or (abs(ad_v - 45.0) <= angle_tol):
        return thickness_mm
    return 0.0

def joint_consumption(piece_left: Dict[str, float],
                      kerf_base: float,
                      ripasso_mm: float,
                      reversible: bool,
                      thickness_mm: float,
                      angle_tol: float,
                      max_angle: float,
                      max_factor: float) -> Tuple[float, float, float, float]:
    """
    Consumo materiale per un GIUNTO (fra piece_left e il successivo).
    Ritorna tuple: (consumo_totale, kerf_proiettato_effettivo_dopo_recupero, ripasso_usato, recupero_usato)
      - kerf proiettato (scegli orientazione con kerf destro minore)
      - ripasso (aggiunto sempre)
      - recupero automatico (solo si sottrae dalla componente kerf, non dal ripasso)
    """
    ax = float(piece_left.get("ax", 0.0))
    ad = float(piece_left.get("ad", 0.0))
    k_norm = kerf_projected(kerf_base, ad, max_angle, max_factor)
    k_flip = kerf_projected(kerf_base, ax, max_angle, max_factor)
    k_raw = min(k_norm, k_flip)
    recovery = 0.0
    if reversible:
        recovery = auto_recovery(thickness_mm, ax, ad, angle_tol)
    k_after = max(0.0, k_raw - recovery)
    rip = max(0.0, ripasso_mm)
    total = k_after + rip
    return total, k_after, rip, recovery

def bar_used_length(bar: List[Dict[str, float]],
                    kerf_base: float,
                    ripasso_mm: float,
                    reversible: bool,
                    thickness_mm: float,
                    angle_tol: float,
                    max_angle: float,
                    max_factor: float) -> float:
    if not bar:
        return 0.0
    total = sum(float(p.get("len", 0.0)) for p in bar)
    if len(bar) <= 1:
        return total
    for i in range(len(bar) - 1):
        total += joint_consumption(bar[i], kerf_base, ripasso_mm,
                                   reversible, thickness_mm,
                                   angle_tol, max_angle, max_factor)[0]
    return total

def compute_bar_breakdown(bar: List[Dict[str, float]],
                          kerf_base: float,
                          ripasso_mm: float,
                          reversible: bool,
                          thickness_mm: float,
                          angle_tol: float,
                          max_angle: float,
                          max_factor: float) -> Dict[str, float]:
    length_sum = sum(float(p.get("len", 0.0)) for p in bar)
    kerf_proj_sum = 0.0
    ripasso_sum = 0.0
    recovery_sum = 0.0
    if len(bar) > 1:
        for i in range(len(bar) - 1):
            tot, kerf_after, rip, rec = joint_consumption(
                bar[i], kerf_base, ripasso_mm, reversible,
                thickness_mm, angle_tol, max_angle, max_factor
            )
            kerf_proj_sum += kerf_after
            ripasso_sum += rip
            recovery_sum += rec
    used_total = length_sum + kerf_proj_sum + ripasso_sum
    return {
        "length_sum": length_sum,
        "kerf_proj_sum": kerf_proj_sum,
        "ripasso_sum": ripasso_sum,
        "recovery_sum": recovery_sum,
        "used_total": used_total
    }

def residuals(bars: List[List[Dict[str, float]]],
              stock: float,
              kerf_base: float,
              ripasso_mm: float,
              reversible: bool,
              thickness_mm: float,
              angle_tol: float,
              max_angle: float,
              max_factor: float) -> List[float]:
    return [max(stock - bar_used_length(b, kerf_base, ripasso_mm, reversible,
                                        thickness_mm, angle_tol, max_angle, max_factor), 0.0)
            for b in bars]

def order_with_max_residual_last(bars: List[List[Dict[str, float]]],
                                 stock: float,
                                 kerf_base: float,
                                 ripasso_mm: float,
                                 reversible: bool,
                                 thickness_mm: float,
                                 angle_tol: float,
                                 max_angle: float,
                                 max_factor: float) -> Tuple[List[List[Dict[str, float]]], List[float]]:
    if not bars:
        return bars, []
    res = residuals(bars, stock, kerf_base, ripasso_mm, reversible, thickness_mm,
                    angle_tol, max_angle, max_factor)
    if not res:
        return bars, []
    max_idx = max(range(len(res)), key=lambda i: res[i])
    if max_idx != len(bars) - 1:
        last = bars.pop(max_idx); bars.append(last)
    res = residuals(bars, stock, kerf_base, ripasso_mm, reversible, thickness_mm,
                    angle_tol, max_angle, max_factor)
    return bars, res

# ============================================================
# Refine MILP
# ============================================================

def refine_tail_ilp(bars: List[List[Dict[str, float]]],
                    stock: float,
                    kerf_base: float,
                    ripasso_mm: float,
                    reversible: bool,
                    thickness_mm: float,
                    angle_tol: float,
                    tail_bars: int,
                    time_limit_s: int,
                    max_angle: float,
                    max_factor: float) -> Tuple[List[List[Dict[str, float]]], List[float]]:
    try:
        import pulp  # type: ignore
    except Exception:
        return order_with_max_residual_last(list(bars), stock, kerf_base, ripasso_mm,
                                            reversible, thickness_mm, angle_tol, max_angle, max_factor)

    if not bars or tail_bars <= 0:
        return order_with_max_residual_last(list(bars), stock, kerf_base, ripasso_mm,
                                            reversible, thickness_mm, angle_tol, max_angle, max_factor)

    n = len(bars)
    start = max(0, n - int(tail_bars))
    head = [list(b) for b in bars[:start]]
    tail = [list(b) for b in bars[start:]]

    items: List[Dict[str, float]] = []
    for b in tail:
        for p in b:
            items.append(dict(p))
    if not items:
        return order_with_max_residual_last(list(bars), stock, kerf_base, ripasso_mm,
                                            reversible, thickness_mm, angle_tol, max_angle, max_factor)

    K = len(tail)
    J = len(items)
    lengths = [float(p.get("len", 0.0)) for p in items]
    joint_cons = kerf_base + max(0.0, ripasso_mm)

    prob = pulp.LpProblem("tail_refine", pulp.LpMinimize)

    x = pulp.LpVariable.dicts("x", (range(J), range(K)), 0, 1, cat=pulp.LpBinary)
    y = pulp.LpVariable.dicts("y", range(K), lowBound=0, cat=pulp.LpInteger)
    z = pulp.LpVariable.dicts("z", range(K), 0, 1, cat=pulp.LpBinary)

    for j in range(J):
        prob += pulp.lpSum(x[j][k] for k in range(K)) == 1

    BIGM = J
    for k in range(K):
        prob += y[k] == pulp.lpSum(x[j][k] for j in range(J))
        prob += y[k] <= BIGM * z[k]
        prob += (pulp.lpSum(lengths[j] * x[j][k] for j in range(J))
                 + joint_cons * (y[k] - z[k]) <= stock)

    W = 1_000_000
    prob += W * pulp.lpSum(z[k] for k in range(K)) - pulp.lpSum(lengths[j] * x[j][k] for j in range(J) for k in range(K))

    try:
        solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=int(time_limit_s))
    except Exception:
        solver = None

    try:
        prob.solve(solver) if solver else prob.solve()
    except Exception:
        return order_with_max_residual_last(list(bars), stock, kerf_base, ripasso_mm,
                                            reversible, thickness_mm, angle_tol, max_angle, max_factor)

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
        if (z[k].value() or 0.0) > 0.5 and new_tail[k]:
            refined_tail.append(new_tail[k])

    out = head + refined_tail
    return order_with_max_residual_last(out, stock, kerf_base, ripasso_mm,
                                        reversible, thickness_mm, angle_tol, max_angle, max_factor)

# ============================================================
# Knapsack ILP per barra
# ============================================================

def pack_bars_knapsack_ilp(pieces: List[Dict[str, float]],
                           stock: float,
                           kerf_base: float,
                           ripasso_mm: float,
                           conservative_angle_deg: float,
                           max_angle: float,
                           max_factor: float,
                           reversible: bool,
                           thickness_mm: float,
                           angle_tol: float,
                           per_bar_time_s: int) -> Tuple[List[List[Dict[str, float]]], List[float]]:
    try:
        import pulp  # type: ignore
    except Exception:
        return [], []

    cons_angle = max(0.0, min(89.9, conservative_angle_deg))
    try:
        cons_factor = 1.0 / math.cos(math.radians(cons_angle)) if cons_angle > 0 else 1.0
    except Exception:
        cons_factor = 1.0
    joint_cons = (kerf_base * cons_factor) + max(0.0, ripasso_mm)

    remaining = [dict(p) for p in pieces]
    bars: List[List[Dict[str, float]]] = []

    while remaining:
        J = len(remaining)
        lengths = [float(p.get("len", 0.0)) for p in remaining]
        import pulp
        prob = pulp.LpProblem("bar_knapsack", pulp.LpMaximize)

        x = pulp.LpVariable.dicts("x", range(J), 0, 1, cat=pulp.LpBinary)
        y = pulp.LpVariable("y", lowBound=0, cat=pulp.LpInteger)
        z = pulp.LpVariable("z", 0, 1, cat=pulp.LpBinary)

        prob += y == pulp.lpSum(x[j] for j in range(J))
        prob += y <= J * z
        prob += y >= z
        prob += pulp.lpSum(lengths[j] * x[j] for j in range(J)) + joint_cons * (y - z) <= stock
        prob += pulp.lpSum(lengths[j] * x[j] for j in range(J))

        try:
            solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=int(per_bar_time_s))
        except Exception:
            solver = None
        try:
            prob.solve(solver) if solver else prob.solve()
        except Exception:
            break

        chosen = [j for j in range(J) if (x[j].value() or 0.0) > 0.5]
        if not chosen:
            best_j = max(range(J), key=lambda jj: lengths[jj])
            chosen = [best_j]

        bar = [remaining[j] for j in chosen]

        # Post-fix overflow (formula esatta)
        while bar and bar_used_length(bar, kerf_base, ripasso_mm, reversible,
                                      thickness_mm, angle_tol, max_angle, max_factor) > stock + 1e-6:
            bar.pop()

        bars.append(bar)
        mask = set(chosen)
        remaining = [remaining[j] for j in range(J) if j not in mask]

    rem = residuals(bars, stock, kerf_base, ripasso_mm, reversible,
                    thickness_mm, angle_tol, max_angle, max_factor)
    return order_with_max_residual_last(bars, stock, kerf_base, ripasso_mm,
                                        reversible, thickness_mm, angle_tol, max_angle, max_factor)
