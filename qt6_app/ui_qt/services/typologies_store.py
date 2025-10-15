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
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL UNIQUE,
    category         TEXT,
    material         TEXT,
    ref_quota        TEXT CHECK (ref_quota IN ('esterna','interna')) DEFAULT 'esterna',
    extra_detrazione REAL DEFAULT 0.0,
    pezzi_totali     INTEGER DEFAULT 1,
    note             TEXT,
    created_at       INTEGER,
    updated_at       INTEGER
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
    row_id       TEXT,          -- "R1", "R2", ...
    name         TEXT,
    profile_name TEXT,
    quantity     INTEGER DEFAULT 0,
    ang_sx       REAL DEFAULT 0.0,
    ang_dx       REAL DEFAULT 0.0,
    formula      TEXT,
    offset       REAL DEFAULT 0.0,
    note         TEXT
);

-- Opzioni/feature per tipologia: chiave/valore testuale (booleane: "0"/"1")
CREATE TABLE IF NOT EXISTS typology_option (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    typology_id  INTEGER NOT NULL REFERENCES typology(id) ON DELETE CASCADE,
    opt_key      TEXT NOT NULL,
    opt_value    TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_typology_option_uk ON typology_option(typology_id, opt_key);

-- Regole lamelle persiane (range su H, conteggio e/o passo)
CREATE TABLE IF NOT EXISTS lamella_rule (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL,   -- es. "Lamella45"
    category  TEXT,            -- es. "persiana"
    h_min     REAL NOT NULL,
    h_max     REAL NOT NULL,
    count     INTEGER,         -- numero lamelle
    pitch_mm  REAL             -- passo tra lamelle (se noto)
);

CREATE INDEX IF NOT EXISTS idx_typology_comp_typ ON typology_component(typology_id, ord);
CREATE INDEX IF NOT EXISTS idx_typology_var_typ  ON typology_var(typology_id);
CREATE INDEX IF NOT EXISTS idx_lamella_name_cat  ON lamella_rule(name, category);
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
        self._maybe_seed_lamelle()

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

    # -------- Tipologie (CRUD) --------
    def list_typologies(self) -> List[Dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT id, name, category, material, pezzi_totali, updated_at FROM typology ORDER BY name ASC"
        )
        return [
            {"id": row[0], "name": row[1], "category": row[2], "material": row[3],
             "pezzi_totali": row[4], "updated_at": row[5]}
            for row in cur.fetchall()
        ]

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
        # opts
        cur = self._conn.execute(
            "SELECT opt_key, opt_value FROM typology_option WHERE typology_id = ?", (typology_id,)
        )
        opts = {r[0]: r[1] for r in cur.fetchall()}
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
            "options": opts,
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
        # options
        for ok, ov in (data.get("options") or {}).items():
            self._conn.execute(
                "INSERT INTO typology_option(typology_id, opt_key, opt_value) VALUES(?,?,?)",
                (typ_id, ok, str(ov) if ov is not None else "")
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
        # replace vars/options/components (semplicità)
        self._conn.execute("DELETE FROM typology_var WHERE typology_id=?", (typology_id,))
        self._conn.execute("DELETE FROM typology_option WHERE typology_id=?", (typology_id,))
        self._conn.execute("DELETE FROM typology_component WHERE typology_id=?", (typology_id,))
        for k, v in (data.get("variabili_locali") or {}).items():
            try: vv = float(v)
            except Exception: vv = 0.0
            self._conn.execute(
                "INSERT INTO typology_var(typology_id, name, value) VALUES(?,?,?)",
                (typology_id, k, vv)
            )
        for ok, ov in (data.get("options") or {}).items():
            self._conn.execute(
                "INSERT INTO typology_option(typology_id, opt_key, opt_value) VALUES(?,?,?)",
                (typology_id, ok, str(ov) if ov is not None else "")
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

    # -------- Opzioni tipologia --------
    def set_option(self, typology_id: int, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO typology_option(typology_id, opt_key, opt_value) VALUES(?,?,?) "
            "ON CONFLICT(typology_id, opt_key) DO UPDATE SET opt_value=excluded.opt_value",
            (typology_id, key, value)
        )
        self._conn.commit()

    def get_options(self, typology_id: int) -> Dict[str, str]:
        cur = self._conn.execute(
            "SELECT opt_key, opt_value FROM typology_option WHERE typology_id=?", (typology_id,)
        )
        return {r[0]: r[1] for r in cur.fetchall()}

    # -------- Lamelle persiane --------
    def list_lamella_rulesets(self, category: str = "persiana") -> List[str]:
        cur = self._conn.execute(
            "SELECT DISTINCT name FROM lamella_rule WHERE category=? ORDER BY name ASC", (category,)
        )
        return [r[0] for r in cur.fetchall()]

    def list_lamella_rules(self, name: str, category: str = "persiana") -> List[Dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT h_min, h_max, count, pitch_mm FROM lamella_rule WHERE name=? AND category=? ORDER BY h_min ASC",
            (name, category)
        )
        return [{"h_min": r[0], "h_max": r[1], "count": r[2], "pitch_mm": r[3]} for r in cur.fetchall()]

    def _maybe_seed_lamelle(self):
        # Seed minimale solo se la tabella è vuota
        cur = self._conn.execute("SELECT COUNT(*) FROM lamella_rule")
        n = int(cur.fetchone()[0])
        if n > 0:
            return
        # Esempio: schema "Lamella45" per persiana
        demo = [
            ( "Lamella45", "persiana", 300, 600, 6,  None),
            ( "Lamella45", "persiana", 600, 900, 8,  None),
            ( "Lamella45", "persiana", 900, 1200, 10, None),
            ( "Lamella45", "persiana", 1200, 1500, 12, None),
        ]
        self._conn.executemany(
            "INSERT INTO lamella_rule(name, category, h_min, h_max, count, pitch_mm) VALUES(?,?,?,?,?,?)",
            demo
        )
        self._conn.commit()
