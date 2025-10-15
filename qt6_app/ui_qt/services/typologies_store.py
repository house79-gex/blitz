from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
import time
import contextlib

DEFAULT_DB_CANDIDATES = [
    Path(__file__).resolve().parents[2] / "data" / "typologies.db",
    Path.cwd() / "data" / "typologies.db",
    Path.home() / "blitz" / "typologies.db",
]

SCHEMA = """
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS typology (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    category        TEXT,
    material        TEXT,
    ref_quota       TEXT CHECK (ref_quota IN ('esterna','interna')) DEFAULT 'esterna',
    extra_detrazione REAL DEFAULT 0.0,
    pezzi_totali    INTEGER DEFAULT 1,
    note            TEXT,
    created_at      INTEGER,
    updated_at      INTEGER
);

CREATE TABLE IF NOT EXISTS typology_var (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    typology_id  INTEGER NOT NULL REFERENCES typology(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    value        REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS typology_component (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    typology_id  INTEGER NOT NULL REFERENCES typology(id) ON DELETE CASCADE,
    ord          INTEGER NOT NULL DEFAULT 0,
    row_id       TEXT,
    name         TEXT,
    profile_name TEXT,
    quantity     INTEGER DEFAULT 0,
    ang_sx       REAL DEFAULT 0.0,
    ang_dx       REAL DEFAULT 0.0,
    formula      TEXT,
    offset       REAL DEFAULT 0.0,
    note         TEXT
);

CREATE INDEX IF NOT EXISTS idx_typology_comp_typ ON typology_component(typology_id, ord);
CREATE INDEX IF NOT EXISTS idx_typology_var_typ ON typology_var(typology_id);
"""

def _now_ts() -> int:
    return int(time.time())

def default_db_path() -> Path:
    for p in DEFAULT_DB_CANDIDATES:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            continue
    p = Path.cwd() / "typologies.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

class TypologiesStore:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path) if db_path else default_db_path()
        self._conn: Optional[sqlite3.Connection] = None
        self._open()
        self._ensure_schema()

    def _open(self):
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA foreign_keys=ON")

    def _ensure_schema(self):
        assert self._conn is not None
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self):
        if self._conn:
            with contextlib.suppress(Exception):
                self._conn.close()
        self._conn = None

    # --- CRUD ---
    def list_typologies(self) -> List[Dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT id, name, category, material, pezzi_totali, updated_at FROM typology ORDER BY name ASC"
        )
        out = []
        for row in cur.fetchall():
            out.append({
                "id": row[0],
                "name": row[1],
                "category": row[2],
                "material": row[3],
                "pezzi_totali": row[4],
                "updated_at": row[5],
            })
        return out

    def get_typology_full(self, typology_id: int) -> Optional[Dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT id, name, category, material, ref_quota, extra_detrazione, pezzi_totali, note, created_at, updated_at "
            "FROM typology WHERE id = ?", (typology_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        # vars
        cur = self._conn.execute(
            "SELECT name, value FROM typology_var WHERE typology_id = ? ORDER BY id ASC", (typology_id,)
        )
        vars_map = {r[0]: float(r[1]) for r in cur.fetchall()}
        # comps
        cur = self._conn.execute(
            "SELECT row_id, name, profile_name, quantity, ang_sx, ang_dx, formula, offset, note "
            "FROM typology_component WHERE typology_id = ? ORDER BY ord ASC, id ASC",
            (typology_id,)
        )
        comps = []
        for r in cur.fetchall():
            comps.append({
                "id_riga": r[0] or "",
                "nome": r[1] or "",
                "profilo_nome": r[2] or "",
                "quantita": int(r[3] or 0),
                "ang_sx": float(r[4] or 0.0),
                "ang_dx": float(r[5] or 0.0),
                "formula_lunghezza": r[6] or "",
                "offset_mm": float(r[7] or 0.0),
                "note": r[8] or "",
            })
        return {
            "id": row[0],
            "nome": row[1],
            "categoria": row[2] or "",
            "materiale": row[3] or "",
            "riferimento_quota": row[4] or "esterna",
            "extra_detrazione_mm": float(row[5] or 0.0),
            "pezzi_totali": int(row[6] or 1),
            "note": row[7] or "",
            "variabili_locali": vars_map,
            "componenti": comps,
            "created_at": row[8],
            "updated_at": row[9],
        }

    def create_typology(self, data: Dict[str, Any]) -> int:
        ts = _now_ts()
        cur = self._conn.execute(
            "INSERT INTO typology(name, category, material, ref_quota, extra_detrazione, pezzi_totali, note, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?, ?, ?)",
            (
                data.get("nome",""),
                data.get("categoria",""),
                data.get("materiale",""),
                (data.get("riferimento_quota") or "esterna"),
                float(data.get("extra_detrazione_mm") or 0.0),
                int(data.get("pezzi_totali") or 1),
                data.get("note",""),
                ts, ts
            )
        )
        typ_id = cur.lastrowid
        # vars
        for k, v in (data.get("variabili_locali") or {}).items():
            try: vv = float(v)
            except Exception: vv = 0.0
            self._conn.execute(
                "INSERT INTO typology_var(typology_id, name, value) VALUES(?,?,?)",
                (typ_id, k, vv)
            )
        # comps
        for idx, c in enumerate(data.get("componenti") or []):
            self._conn.execute(
                "INSERT INTO typology_component(typology_id, ord, row_id, name, profile_name, quantity, ang_sx, ang_dx, formula, offset, note) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    typ_id, idx,
                    c.get("id_riga",""),
                    c.get("nome",""),
                    c.get("profilo_nome",""),
                    int(c.get("quantita",0) or 0),
                    float(c.get("ang_sx",0.0) or 0.0),
                    float(c.get("ang_dx",0.0) or 0.0),
                    c.get("formula_lunghezza",""),
                    float(c.get("offset_mm",0.0) or 0.0),
                    c.get("note",""),
                )
            )
        self._conn.commit()
        return int(typ_id)

    def update_typology(self, typology_id: int, data: Dict[str, Any]) -> None:
        ts = _now_ts()
        self._conn.execute(
            "UPDATE typology SET name=?, category=?, material=?, ref_quota=?, extra_detrazione=?, pezzi_totali=?, note=?, updated_at=? "
            "WHERE id=?",
            (
                data.get("nome",""),
                data.get("categoria",""),
                data.get("materiale",""),
                (data.get("riferimento_quota") or "esterna"),
                float(data.get("extra_detrazione_mm") or 0.0),
                int(data.get("pezzi_totali") or 1),
                data.get("note",""),
                ts,
                typology_id
            )
        )
        self._conn.execute("DELETE FROM typology_var WHERE typology_id=?", (typology_id,))
        self._conn.execute("DELETE FROM typology_component WHERE typology_id=?", (typology_id,))
        for k, v in (data.get("variabili_locali") or {}).items():
            try: vv = float(v)
            except Exception: vv = 0.0
            self._conn.execute(
                "INSERT INTO typology_var(typology_id, name, value) VALUES(?,?,?)",
                (typology_id, k, vv)
            )
        for idx, c in enumerate(data.get("componenti") or []):
            self._conn.execute(
                "INSERT INTO typology_component(typology_id, ord, row_id, name, profile_name, quantity, ang_sx, ang_dx, formula, offset, note) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    typology_id, idx,
                    c.get("id_riga",""),
                    c.get("nome",""),
                    c.get("profilo_nome",""),
                    int(c.get("quantita",0) or 0),
                    float(c.get("ang_sx",0.0) or 0.0),
                    float(c.get("ang_dx",0.0) or 0.0),
                    c.get("formula_lunghezza",""),
                    float(c.get("offset_mm",0.0) or 0.0),
                    c.get("note",""),
                )
            )
        self._conn.commit()

    def delete_typology(self, typology_id: int) -> None:
        self._conn.execute("DELETE FROM typology WHERE id=?", (typology_id,))
        self._conn.commit()

    def duplicate_typology(self, typology_id: int, new_name: str) -> Optional[int]:
        src = self.get_typology_full(typology_id)
        if not src:
            return None
        src["nome"] = new_name
        return self.create_typology(src)
