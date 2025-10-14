from __future__ import annotations
from typing import Optional, Tuple, Dict, Any
from pathlib import Path
import json
import os
import subprocess
import sys

def suggest_qcad_paths() -> list[str]:
    candidates: list[str] = []
    for p in (
        "/usr/bin/qcad",
        "/usr/local/bin/qcad",
        "/usr/bin/qcad-bin",
        "/opt/qcad/qcad",
        str(Path.home() / "qcad" / "qcad"),
        str(Path.home() / "qcad" / "qcad.sh"),
    ):
        candidates.append(p)
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    for base in (program_files, pf_x86):
        if base:
            candidates.append(str(Path(base) / "QCAD" / "qcad.exe"))
    return candidates

def launch_qcad(qcad_executable: str, dxf_path: Optional[str] = None, workspace_dir: Optional[str] = None) -> subprocess.Popen:
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
    return Path(workspace_dir) / "export.blitz.json"

def parse_export_json(json_path: str) -> Tuple[Optional[float], Dict[str, Any]]:
    p = Path(json_path)
    if not p.exists():
        return None, {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None, {}
    last_dim: Optional[float] = None
    v = data.get("lastDimension")
    try:
        if isinstance(v, (int, float)):
            last_dim = float(v)
    except Exception:
        pass
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
        # usa bounding box veloce; fallback a childrenBoundingRect-approx se serve
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
