from __future__ import annotations
from pathlib import Path

def analyze_dxf(path: str) -> dict:
    """
    Analizza un file DXF per profili:
    - Calcola bbox 2D (min/max X,Y) considerando entità geometriche comuni.
    - Restituisce metadata per salvataggio.
    Richiede 'ezdxf'. Se mancante, solleva ImportError con messaggio chiaro.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File non trovato: {path}")
    try:
        import ezdxf  # type: ignore
    except Exception as e:
        raise ImportError("Modulo 'ezdxf' non installato. Installa con: pip install ezdxf") from e

    doc = ezdxf.readfile(str(p))
    msp = doc.modelspace()

    xmin = ymin = float("inf")
    xmax = ymax = float("-inf")
    count = 0

    def upd(x, y):
        nonlocal xmin, ymin, xmax, ymax
        xmin = min(xmin, float(x))
        ymin = min(ymin, float(y))
        xmax = max(xmax, float(x))
        ymax = max(ymax, float(y))

    # Considera entità più comuni
    for e in msp:
        try:
            dxftype = e.dxftype()
        except Exception:
            continue
        try:
            if dxftype in ("LINE",):
                upd(e.dxf.start.x, e.dxf.start.y); upd(e.dxf.end.x, e.dxf.end.y); count += 1
            elif dxftype in ("LWPOLYLINE", "POLYLINE"):
                pts = list(e.get_points()) if hasattr(e, "get_points") else []
                for pt in pts:
                    x, y = pt[0], pt[1]
                    upd(x, y)
                count += 1
            elif dxftype in ("CIRCLE",):
                c = e.dxf.center; r = float(e.dxf.radius)
                upd(c.x - r, c.y - r); upd(c.x + r, c.y + r); count += 1
            elif dxftype in ("ARC",):
                # bbox approssimata arco
                c = e.dxf.center; r = float(e.dxf.radius)
                upd(c.x - r, c.y - r); upd(c.x + r, c.y + r); count += 1
            elif dxftype in ("SPLINE",):
                # approssima sui punti di controllo
                for pnt in e.control_points:
                    upd(pnt[0], pnt[1])
                count += 1
        except Exception:
            pass

    if count == 0 or xmin == float("inf"):
        raise ValueError("Nessuna geometria analizzabile trovata nel DXF.")

    bbox_w = xmax - xmin
    bbox_h = ymax - ymin

    # Nome suggerito dal file
    name_suggestion = p.stem

    return {
        "name_suggestion": name_suggestion,
        "bbox_w": float(bbox_w),
        "bbox_h": float(bbox_h),
        "entities": int(count),
        "path": str(p.resolve()),
        "bounds": {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax},
    }
