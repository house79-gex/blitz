from __future__ import annotations
from typing import Optional, Tuple, Dict, Any
from pathlib import Path
import json
import os
import subprocess

def suggest_qcad_paths() -> list[str]:
    """
    Restituisce una lista di percorsi possibili per QCAD su Raspberry/Linux o altre piattaforme.
    Non garantisce l'esistenza; serve solo come suggerimento.
    """
    candidates: list[str] = []
    # Raspberry Pi / Linux tipici
    for p in (
        "/usr/bin/qcad",
        "/usr/local/bin/qcad",
        "/usr/bin/qcad-bin",
        "/opt/qcad/qcad",
        str(Path.home() / "qcad" / "qcad"),
        str(Path.home() / "qcad" / "qcad.sh"),
    ):
        candidates.append(p)
    # Windows (se presente)
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    for base in (program_files, pf_x86):
        if base:
            candidates.append(str(Path(base) / "QCAD" / "qcad.exe"))
    return candidates

def launch_qcad(qcad_executable: str, dxf_path: Optional[str] = None, workspace_dir: Optional[str] = None) -> subprocess.Popen:
    """
    Avvia QCAD. Se dxf_path è fornito e valido, apre quel file; altrimenti apre vuoto.
    Se workspace_dir è fornito, imposta la cwd del processo (utile per l'export nella stessa cartella).
    """
    exe = Path(qcad_executable)
    if not exe.exists():
        raise FileNotFoundError(f"Eseguibile QCAD non trovato: {qcad_executable}")
    args = [str(exe)]
    if dxf_path:
        args.append(str(Path(dxf_path)))
    cwd = str(Path(workspace_dir)) if workspace_dir else None
    if exe.suffix == ".sh":
        return subprocess.Popen(["/bin/bash", str(exe)] + (args[1:] if len(args) > 1 else []), cwd=cwd)
    return subprocess.Popen(args, cwd=cwd)

def find_export_file(workspace_dir: str) -> Path:
    """
    Percorso canonico per l'export JSON della macro: export.blitz.json nella cartella di lavoro.
    """
    return Path(workspace_dir) / "export.blitz.json"

def parse_export_json(json_path: str) -> Tuple[Optional[float], Dict[str, Any]]:
    """
    Parsing robusto dell'export JSON.
    Restituisce (last_dimension_value, full_dict).
    """
    p = Path(json_path)
    if not p.exists():
        return None, {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None, {}
    last_dim: Optional[float] = None
    # 1) Chiave diretta
    v = data.get("lastDimension")
    try:
        if isinstance(v, (int, float)):
            last_dim = float(v)
    except Exception:
        pass
    # 2) Lista dimensions
    if last_dim is None:
        dims = data.get("dimensions")
        if isinstance(dims, list):
            for item in dims[::-1]:
                try:
                    vv = item.get("value")
                    if isinstance(vv, (int, float)):
                        last_dim = float(vv)
                        break
                except Exception:
                    continue
    # 3) Entità dimension in entities
    if last_dim is None:
        ents = data.get("entities")
        if isinstance(ents, list):
            for e in ents[::-1]:
                try:
                    t = (e.get("type") or "").lower()
                    if "dim" in t:
                        vv = e.get("value")
                        if isinstance(vv, (int, float)):
                            last_dim = float(vv)
                            break
                except Exception:
                    continue
    return last_dim, data

def compute_dxf_bbox(dxf_path: str) -> Optional[Tuple[float, float]]:
    """
    Restituisce (width, height) della bbox 2D del DXF in unità disegno.
    Richiede ezdxf; se non presente, restituisce None.
    """
    try:
        import ezdxf  # type: ignore
    except Exception:
        return None
    p = Path(dxf_path)
    if not p.exists():
        return None
    try:
        doc = ezdxf.readfile(str(p))
        msp = doc.modelspace()
        ext = msp.bbox()
        if ext is None:
            return None
        (minx, miny, _), (maxx, maxy, _) = ext.extmin, ext.extmax
        w = float(maxx - minx)
        h = float(maxy - miny)
        if w < 0 or h < 0:
            return None
        return (w, h)
    except Exception:
        return None
