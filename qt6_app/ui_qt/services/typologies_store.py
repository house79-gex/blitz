from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import time
import contextlib

DEFAULT_DB_CANDIDATES = [
    Path(__file__).resolve().parents[2] / "data" / "typologies.db",
    Path.cwd() / "data" / "typologies.db",
    Path.home() / "blitz" / "typologies.db",
]

SCHEMA = """
PRAGMA foreign_keys=ON;

-- Tipologie (legacy)
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

-- Opzioni/feature per tipologia (k/v)
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

-- Catalogo ferramenta (marca/serie/maniglia/bracci/formule astina)
CREATE TABLE IF NOT EXISTS hw_brand (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS hw_series (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id  INTEGER NOT NULL REFERENCES hw_brand(id) ON DELETE CASCADE,
    name      TEXT NOT NULL,
    UNIQUE(brand_id, name)
);

CREATE TABLE IF NOT EXISTS hw_handle_type (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id          INTEGER NOT NULL REFERENCES hw_brand(id) ON DELETE CASCADE,
    series_id         INTEGER NOT NULL REFERENCES hw_series(id) ON DELETE CASCADE,
    code              TEXT NOT NULL,
    name              TEXT NOT NULL,
    handle_offset_mm  REAL NOT NULL DEFAULT 0.0,
    UNIQUE(brand_id, series_id, code)
);

CREATE TABLE IF NOT EXISTS hw_arm_rule (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id     INTEGER NOT NULL REFERENCES hw_brand(id) ON DELETE CASCADE,
    series_id    INTEGER NOT NULL REFERENCES hw_series(id) ON DELETE CASCADE,
    sash_subcat  TEXT NOT NULL,   -- es. "battente_standard"
    w_min        REAL NOT NULL,
    w_max        REAL NOT NULL,
    arm_code     TEXT NOT NULL,
    arm_name     TEXT,
    UNIQUE(brand_id, series_id, sash_subcat, w_min, w_max)
);

CREATE TABLE IF NOT EXISTS hw_astina_formula (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id     INTEGER NOT NULL REFERENCES hw_brand(id) ON DELETE CASCADE,
    series_id    INTEGER NOT NULL REFERENCES hw_series(id) ON DELETE CASCADE,
    sash_subcat  TEXT NOT NULL,
    arm_code     TEXT,            -- NULL = formula generica sottocategoria
    formula      TEXT NOT NULL,
    note         TEXT,
    UNIQUE(brand_id, series_id, sash_subcat, arm_code)
);

-- Opzioni di ferramenta specifiche della tipologia (preset selezionabili in commessa)
CREATE TABLE IF NOT EXISTS typology_hw_option (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    typology_id  INTEGER NOT NULL REFERENCES typology(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,      -- etichetta visibile (es. "Roto TT-100 standard")
    brand_id     INTEGER NOT NULL REFERENCES hw_brand(id),
    series_id    INTEGER NOT NULL REFERENCES hw_series(id),
    subcat       TEXT NOT NULL,      -- es. "battente_standard"
    handle_id    INTEGER,            -- opzionale, REFERENCES hw_handle_type(id)
    UNIQUE(typology_id, name)
);

-- Mapping formula per componente in base all'opzione ferramenta
CREATE TABLE IF NOT EXISTS comp_hw_formula (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    typology_id   INTEGER NOT NULL REFERENCES typology(id) ON DELETE CASCADE,
    row_id        TEXT NOT NULL,     -- "R1"
    hw_option_id  INTEGER NOT NULL REFERENCES typology_hw_option(id) ON DELETE CASCADE,
    formula       TEXT NOT NULL,
    UNIQUE(typology_id, row_id, hw_option_id)
);

CREATE INDEX IF NOT EXISTS idx_typology_comp_typ ON typology_component(typology_id, ord);
CREATE INDEX IF NOT EXISTS idx_typology_var_typ  ON typology_var(typology_id);
CREATE INDEX IF NOT EXISTS idx_lamella_name_cat  ON lamella_rule(name, category);

CREATE INDEX IF NOT EXISTS idx_typhwopt_typ ON typology_hw_option(typology_id);
CREATE INDEX IF NOT EXISTS idx_cmphw_typ_row ON comp_hw_formula(typology_id, row_id);
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
        self._maybe_seed()

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

    # ----------------- Tipologie (CRUD) -----------------
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
        cur = self._conn.execute(
            "SELECT name, value FROM typology_var WHERE typology_id = ? ORDER BY id ASC", (typology_id,)
        )
        vars_map = {r[0]: float(r[1]) for r in cur.fetchall()}
        cur = self._conn.execute(
            "SELECT opt_key, opt_value FROM typology_option WHERE typology_id = ?", (typology_id,)
        )
        opts = {r[0]: r[1] for r in cur.fetchall()}
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
        typ_id = int(cur.lastrowid)
        for k, v in (data.get("variabili_locali") or {}).items():
            try: vv = float(v)
            except Exception: vv = 0.0
            self._conn.execute(
                "INSERT INTO typology_var(typology_id, name, value) VALUES(?,?,?)",
                (typ_id, k, vv)
            )
        for ok, ov in (data.get("options") or {}).items():
            self._conn.execute(
                "INSERT INTO typology_option(typology_id, opt_key, opt_value) VALUES(?,?,?)",
                (typ_id, ok, str(ov) if ov is not None else "")
            )
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
        return typ_id

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

    # -------- Catalogo ferramenta --------
    def list_hw_brands(self) -> List[Dict[str, Any]]:
        cur = self._conn.execute("SELECT id, name FROM hw_brand ORDER BY name ASC")
        return [{"id": r[0], "name": r[1]} for r in cur.fetchall()]

    def list_hw_series(self, brand_id: int) -> List[Dict[str, Any]]:
        cur = self._conn.execute("SELECT id, name FROM hw_series WHERE brand_id=? ORDER BY name ASC", (brand_id,))
        return [{"id": r[0], "name": r[1]} for r in cur.fetchall()]

    def list_hw_handle_types(self, brand_id: int, series_id: int) -> List[Dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT id, code, name, handle_offset_mm FROM hw_handle_type WHERE brand_id=? AND series_id=? ORDER BY name ASC",
            (brand_id, series_id)
        )
        return [{"id": r[0], "code": r[1], "name": r[2], "handle_offset_mm": float(r[3] or 0.0)} for r in cur.fetchall()]

    def list_hw_sash_subcats(self, brand_id: int, series_id: int) -> List[str]:
        cur = self._conn.execute(
            "SELECT DISTINCT sash_subcat FROM hw_arm_rule WHERE brand_id=? AND series_id=? ORDER BY sash_subcat ASC",
            (brand_id, series_id)
        )
        return [r[0] for r in cur.fetchall()]

    def pick_arm_for_width(self, brand_id: int, series_id: int, sash_subcat: str, width_L: float) -> Optional[Dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT arm_code, arm_name FROM hw_arm_rule WHERE brand_id=? AND series_id=? AND sash_subcat=? AND ? BETWEEN w_min AND w_max",
            (brand_id, series_id, sash_subcat, float(width_L))
        )
        r = cur.fetchone()
        if not r:
            return None
        return {"arm_code": r[0], "arm_name": r[1]}

    def get_astina_formula(self, brand_id: int, series_id: int, sash_subcat: str, arm_code: Optional[str]) -> Optional[str]:
        if arm_code:
            r = self._conn.execute(
                "SELECT formula FROM hw_astina_formula WHERE brand_id=? AND series_id=? AND sash_subcat=? AND arm_code=?",
                (brand_id, series_id, sash_subcat, arm_code)
            ).fetchone()
            if r: return r[0]
        r = self._conn.execute(
            "SELECT formula FROM hw_astina_formula WHERE brand_id=? AND series_id=? AND sash_subcat=? AND arm_code IS NULL",
            (brand_id, series_id, sash_subcat)
        ).fetchone()
        return r[0] if r else None

    def get_handle_offset(self, handle_id: int) -> Optional[float]:
        r = self._conn.execute("SELECT handle_offset_mm FROM hw_handle_type WHERE id=?", (handle_id,)).fetchone()
        return float(r[0]) if r else None

    # -------- Opzioni ferramenta della tipologia --------
    def list_typology_hw_options(self, typology_id: int) -> List[Dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT id, name, brand_id, series_id, subcat, handle_id FROM typology_hw_option WHERE typology_id=? ORDER BY name ASC",
            (typology_id,)
        )
        out = []
        for r in cur.fetchall():
            out.append({
                "id": int(r[0]),
                "name": r[1],
                "brand_id": int(r[2]),
                "series_id": int(r[3]),
                "subcat": r[4],
                "handle_id": (int(r[5]) if r[5] is not None else None)
            })
        return out

    def create_typology_hw_option(self, typology_id: int, name: str, brand_id: int, series_id: int, subcat: str, handle_id: Optional[int]) -> int:
        cur = self._conn.execute(
            "INSERT INTO typology_hw_option(typology_id, name, brand_id, series_id, subcat, handle_id) VALUES(?,?,?,?,?,?)",
            (typology_id, name, int(brand_id), int(series_id), str(subcat), (int(handle_id) if handle_id is not None else None))
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def update_typology_hw_option(self, opt_id: int, name: str, brand_id: int, series_id: int, subcat: str, handle_id: Optional[int]) -> None:
        self._conn.execute(
            "UPDATE typology_hw_option SET name=?, brand_id=?, series_id=?, subcat=?, handle_id=? WHERE id=?",
            (name, int(brand_id), int(series_id), str(subcat), (int(handle_id) if handle_id is not None else None), int(opt_id))
        )
        self._conn.commit()

    def delete_typology_hw_option(self, opt_id: int) -> None:
        self._conn.execute("DELETE FROM typology_hw_option WHERE id=?", (int(opt_id),))
        self._conn.commit()

    def get_typology_hw_option(self, opt_id: int) -> Optional[Dict[str, Any]]:
        r = self._conn.execute(
            "SELECT id, typology_id, name, brand_id, series_id, subcat, handle_id FROM typology_hw_option WHERE id=?",
            (int(opt_id),)
        ).fetchone()
        if not r: return None
        return {
            "id": int(r[0]),
            "typology_id": int(r[1]),
            "name": r[2],
            "brand_id": int(r[3]),
            "series_id": int(r[4]),
            "subcat": r[5],
            "handle_id": (int(r[6]) if r[6] is not None else None)
        }

    # -------- Formula per componente in base all'opzione --------
    def set_comp_hw_formula(self, typology_id: int, row_id: str, hw_option_id: int, formula: str) -> None:
        self._conn.execute(
            "INSERT INTO comp_hw_formula(typology_id, row_id, hw_option_id, formula) VALUES(?,?,?,?) "
            "ON CONFLICT(typology_id, row_id, hw_option_id) DO UPDATE SET formula=excluded.formula",
            (int(typology_id), str(row_id), int(hw_option_id), str(formula))
        )
        self._conn.commit()

    def delete_comp_hw_formula(self, typology_id: int, row_id: str, hw_option_id: int) -> None:
        self._conn.execute(
            "DELETE FROM comp_hw_formula WHERE typology_id=? AND row_id=? AND hw_option_id=?",
            (int(typology_id), str(row_id), int(hw_option_id))
        )
        self._conn.commit()

    def get_comp_hw_formula(self, typology_id: int, row_id: str, hw_option_id: int) -> Optional[str]:
        r = self._conn.execute(
            "SELECT formula FROM comp_hw_formula WHERE typology_id=? AND row_id=? AND hw_option_id=?",
            (int(typology_id), str(row_id), int(hw_option_id))
        ).fetchone()
        return r[0] if r else None

    def list_comp_hw_formulas_for_row(self, typology_id: int, row_id: str) -> List[Dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT hw_option_id, formula FROM comp_hw_formula WHERE typology_id=? AND row_id=?",
            (int(typology_id), str(row_id))
        )
        return [{"hw_option_id": int(r[0]), "formula": r[1]} for r in cur.fetchall()]

    # -------- Seed demo minimale --------
    def _maybe_seed(self):
        # lamelle
        n = int(self._conn.execute("SELECT COUNT(*) FROM lamella_rule").fetchone()[0])
        if n == 0:
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

        # hardware
        nb = int(self._conn.execute("SELECT COUNT(*) FROM hw_brand").fetchone()[0])
        if nb == 0:
            self._conn.execute("INSERT INTO hw_brand(name) VALUES(?)", ("DemoHW",))
            brand_id = int(self._conn.execute("SELECT id FROM hw_brand WHERE name=?", ("DemoHW",)).fetchone()[0])
            self._conn.execute("INSERT INTO hw_series(brand_id,name) VALUES(?,?)", (brand_id, "TT-100"))
            series_id = int(self._conn.execute("SELECT id FROM hw_series WHERE brand_id=? AND name=?", (brand_id, "TT-100")).fetchone()[0])
            self._conn.executemany(
                "INSERT INTO hw_handle_type(brand_id,series_id,code,name,handle_offset_mm) VALUES(?,?,?,?,?)",
                [
                    (brand_id, series_id, "H-A", "Maniglia A", 102.0),
                    (brand_id, series_id, "H-B", "Maniglia B", 125.0),
                ]
            )
            self._conn.executemany(
                "INSERT INTO hw_arm_rule(brand_id,series_id,sash_subcat,w_min,w_max,arm_code,arm_name) VALUES(?,?,?,?,?,?,?)",
                [
                    (brand_id, series_id, "battente_standard", 350.0, 600.0,  "ARM-1", "Braccio 1"),
                    (brand_id, series_id, "battente_standard", 600.01, 900.0, "ARM-2", "Braccio 2"),
                    (brand_id, series_id, "battente_standard", 900.01, 1200.0,"ARM-3", "Braccio 3"),
                ]
            )
            self._conn.execute(
                "INSERT INTO hw_astina_formula(brand_id,series_id,sash_subcat,arm_code,formula,note) VALUES(?,?,?,?,?,?)",
                (brand_id, series_id, "battente_standard", None, "max(200, min(H - handle_offset - 70, 1200))", "Formula base")
            )
            self._conn.commit()
