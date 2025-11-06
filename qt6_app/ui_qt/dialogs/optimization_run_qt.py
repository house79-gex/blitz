# ... intestazioni invariate ...
from ui_qt.widgets.plan_visualizer import PlanVisualizerWidget
from ui_qt.logic.refiner import refine_tail_ilp  # NEW

class OptimizationRunDialog(QDialog):
    # ... class invariate ...
    def _compute_plan_once(self):
        pieces = self._expand_rows_to_unit_pieces()
        bars, rem = self._pack_bars_bfd(pieces)

        # Ordina barre lasciando per ultima quella con residuo massimo
        if rem:
            max_idx = max(range(len(rem)), key=lambda i: rem[i])
            if 0 <= max_idx < len(bars) and max_idx != len(bars) - 1:
                last_bar = bars.pop(max_idx); bars.append(last_bar)
                last_res = rem.pop(max_idx); rem.append(last_res)

        # Refine pass locale (MILP) sulle ultime N barre
        try:
            cfg = read_settings()
            tail_n = int(cfg.get("opt_refine_tail_bars", 6))
            tl = int(cfg.get("opt_refine_time_s", 25))
        except Exception:
            tail_n = 6; tl = 25
        try:
            bars, rem = refine_tail_ilp(bars, stock=float(self._stock), kerf=float(self._kerf),
                                        tail_bars=tail_n, time_limit_s=tl)
        except Exception:
            # sicurezza: mai interrompere la dialog
            pass

        self._bars, self._bars_residuals = bars, rem
