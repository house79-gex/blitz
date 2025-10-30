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

CREATE TABLE IF NOT EXISTS typology_option (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    typology_id  INTEGER NOT NULL REFERENCES typology(id) ON DELETE CASCADE,
    opt_key      TEXT NOT NULL,
    opt_value    TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_typology_option_uk ON typology_option(typology_id, opt_key);

CREATE TABLE IF NOT EXISTS lamella_rule (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL,
    category  TEXT,
    h_min     REAL NOT NULL,
    h_max     REAL NOT NULL,
    count     INTEGER,
    pitch_mm  REAL
);

-- Catalogo ferramenta
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
    sash_subcat  TEXT NOT NULL,
    w_min        REAL NOT NULL,
    w_max        REAL NOT NULL,
    arm_code     TEXT NOT NULL,
    arm_name     TEXT,
    arm_class    TEXT,
    astina_len   REAL,
    UNIQUE(brand_id, series_id, sash_subcat, w_min, w_max, arm_code)
);
CREATE TABLE IF NOT EXISTS hw_astina_formula (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id     INTEGER NOT NULL REFERENCES hw_brand(id) ON DELETE CASCADE,
    series_id    INTEGER NOT NULL REFERENCES hw_series(id) ON DELETE CASCADE,
    sash_subcat  TEXT NOT NULL,
    arm_code     TEXT,
    formula      TEXT NOT NULL,
    note         TEXT,
    UNIQUE(brand_id, series_id, sash_subcat, arm_code)
);

-- Libreria formule ferramenta (nuova)
CREATE TABLE IF NOT EXISTS hw_formula_preset (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,         -- es. "Montante anta (normale)"
    brand_id       INTEGER REFERENCES hw_brand(id) ON DELETE SET NULL,
    series_id      INTEGER REFERENCES hw_series(id) ON DELETE SET NULL,
    subcat         TEXT,                  -- es. "battente_standard"
    mechanism_code TEXT,                  -- es. "normale", "ribalta_dk"
    scope          TEXT,                  -- "component" | "part" | libero (etichetta)
    target         TEXT,                  -- es. "montante_anta", "traverso", "AST_SUP_MONT"...
    formula        TEXT NOT NULL,
    note           TEXT
);
CREATE INDEX IF NOT EXISTS idx_hw_formula_preset_filt ON hw_formula_preset(brand_id, series_id, subcat, mechanism_code, scope, target);

-- Meccanismi
CREATE TABLE IF NOT EXISTS hw_mechanism (
    code        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT
);
CREATE TABLE IF NOT EXISTS hw_mech_part (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    mechanism_code TEXT NOT NULL REFERENCES hw_mechanism(code) ON DELETE CASCADE,
    part_key      TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    profile_name  TEXT NOT NULL,
    qty           INTEGER NOT NULL DEFAULT 1,
    ang_sx        REAL NOT NULL DEFAULT 0.0,
    ang_dx        REAL NOT NULL DEFAULT 0.0,
    formula       TEXT NOT NULL,
    UNIQUE(mechanism_code, part_key)
);

-- Opzioni ferramenta tipologia
CREATE TABLE IF NOT EXISTS typology_hw_option (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    typology_id  INTEGER NOT NULL REFERENCES typology(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    brand_id     INTEGER NOT NULL REFERENCES hw_brand(id),
    series_id    INTEGER NOT NULL REFERENCES hw_series(id),
    subcat       TEXT NOT NULL,
    handle_id    INTEGER,
    mechanism_code TEXT,
    UNIQUE(typology_id, name)
);

-- Override formula per elemento in base all'opzione
CREATE TABLE IF NOT EXISTS comp_hw_formula (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    typology_id   INTEGER NOT NULL REFERENCES typology(id) ON DELETE CASCADE,
    row_id        TEXT NOT NULL,
    hw_option_id  INTEGER NOT NULL REFERENCES typology_hw_option(id) ON DELETE CASCADE,
    formula       TEXT NOT NULL,
    UNIQUE(typology_id, row_id, hw_option_id)
);

-- Override formula per parti meccanismo specifiche per opzione
CREATE TABLE IF NOT EXISTS typology_mech_part_formula (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    typology_id   INTEGER NOT NULL REFERENCES typology(id) ON DELETE CASCADE,
    hw_option_id  INTEGER NOT NULL REFERENCES typology_hw_option(id) ON DELETE CASCADE,
    part_key      TEXT NOT NULL,
    formula       TEXT NOT NULL,
    UNIQUE(typology_id, hw_option_id, part_key)
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
        self._migrate_schema()
        self._maybe_seed()

    def _open(self):
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA foreign_keys=ON")

    def _ensure_schema(self):
        assert self._conn is not None
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def _migrate_schema(self):
        with contextlib.suppress(Exception):
            self._conn.execute("ALTER TABLE hw_arm_rule ADD COLUMN arm_class TEXT")
        with contextlib.suppress(Exception):
            self._conn.execute("ALTER TABLE hw_arm_rule ADD COLUMN astina_len REAL")
        with contextlib.suppress(Exception):
            self._conn.execute("ALTER TABLE typology_hw_option ADD COLUMN mechanism_code TEXT")
        # hw_formula_preset table is created in SCHEMA
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
        vars_map = {r[0]: float(r[1]) for r in self._conn.execute(
            "SELECT name, value FROM typology_var WHERE typology_id=? ORDER BY id", (typology_id,)).fetchall()}
        opts = {r[0]: r[1] for r in self._conn.execute(
            "SELECT opt_key, opt_value FROM typology_option WHERE typology_id=?", (typology_id,)).fetchall()}
        comps = []
        for r in self._conn.execute(
            "SELECT row_id, name, profile_name, quantity, ang_sx, ang_dx, formula, offset, note "
            "FROM typology_component WHERE typology_id=? ORDER BY ord, id", (typology_id,)).fetchall():
            comps.append({
                "id_riga": r[0] or "", "nome": r[1] or "", "profilo_nome": r[2] or "",
                "quantita": int(r[3] or 0), "ang_sx": float(r[4] or 0.0), "ang_dx": float(r[5] or 0.0),
                "formula_lunghezza": r[6] or "", "offset_mm": float(r[7] or 0.0), "note": r[8] or ""
            })
        return {
            "id": row[0], "nome": row[1], "categoria": row[2] or "", "materiale": row[3] or "",
            "riferimento_quota": row[4] or "esterna", "extra_detrazione_mm": float(row[5] or 0.0),
            "pezzi_totali": int(row[6] or 1), "note": row[7] or "",
            "variabili_locali": vars_map, "options": opts, "componenti": comps,
            "created_at": row[8], "updated_at": row[9]
        }

    def create_typology(self, data: Dict[str, Any]) -> int:
        ts = _now_ts()
        cur = self._conn.execute(
            "INSERT INTO typology(name, category, material, ref_quota, extra_detrazione, pezzi_totali, note, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?, ?, ?)",
            (data.get("nome",""), data.get("categoria",""), data.get("materiale",""),
             (data.get("riferimento_quota") or "esterna"), float(data.get("extra_detrazione_mm") or 0.0),
             int(data.get("pezzi_totali") or 1), data.get("note",""), ts, ts)
        )
        typ_id = int(cur.lastrowid)
        for k, v in (data.get("variabili_locali") or {}).items():
            try: vv = float(v)
            except Exception: vv = 0.0
            self._conn.execute("INSERT INTO typology_var(typology_id,name,value) VALUES(?,?,?)", (typ_id, k, vv))
        for ok, ov in (data.get("options") or {}).items():
            self._conn.execute("INSERT INTO typology_option(typology_id,opt_key,opt_value) VALUES(?,?,?)", (typ_id, ok, str(ov) if ov is not None else ""))
        for idx, c in enumerate(data.get("componenti") or []):
            self._conn.execute(
                "INSERT INTO typology_component(typology_id,ord,row_id,name,profile_name,quantity,ang_sx,ang_dx,formula,offset,note) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (typ_id, idx, c.get("id_riga",""), c.get("nome",""), c.get("profilo_nome",""),
                 int(c.get("quantita",0) or 0), float(c.get("ang_sx",0.0) or 0.0), float(c.get("ang_dx",0.0) or 0.0),
                 c.get("formula_lunghezza",""), float(c.get("offset_mm",0.0) or 0.0), c.get("note","")))
        self._conn.commit()
        return typ_id

    def update_typology(self, typology_id: int, data: Dict[str, Any]) -> None:
        ts = _now_ts()
        self._conn.execute(
            "UPDATE typology SET name=?, category=?, material=?, ref_quota=?, extra_detrazione=?, pezzi_totali=?, note=?, updated_at=? WHERE id=?",
            (data.get("nome",""), data.get("categoria",""), data.get("materiale",""),
             (data.get("riferimento_quota") or "esterna"), float(data.get("extra_detrazione_mm") or 0.0),
             int(data.get("pezzi_totali") or 1), data.get("note",""), ts, int(typology_id)))
        self._conn.execute("DELETE FROM typology_var WHERE typology_id=?", (typology_id,))
        self._conn.execute("DELETE FROM typology_option WHERE typology_id=?", (typology_id,))
        self._conn.execute("DELETE FROM typology_component WHERE typology_id=?", (typology_id,))
        for k, v in (data.get("variabili_locali") or {}).items():
            try: vv = float(v)
            except Exception: vv = 0.0
            self._conn.execute("INSERT INTO typology_var(typology_id,name,value) VALUES(?,?,?)", (typology_id, k, vv))
        for ok, ov in (data.get("options") or {}).items():
            self._conn.execute("INSERT INTO typology_option(typology_id,opt_key,opt_value) VALUES(?,?,?)", (typology_id, ok, str(ov) if ov is not None else ""))
        for idx, c in enumerate(data.get("componenti") or []):
            self._conn.execute(
                "INSERT INTO typology_component(typology_id,ord,row_id,name,profile_name,quantity,ang_sx,ang_dx,formula,offset,note) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (typology_id, idx, c.get("id_riga",""), c.get("nome",""), c.get("profilo_nome",""),
                 int(c.get("quantita",0) or 0), float(c.get("ang_sx",0.0) or 0.0), float(c.get("ang_dx",0.0) or 0.0),
                 c.get("formula_lunghezza",""), float(c.get("offset_mm",0.0) or 0.0), c.get("note","")))
        self._conn.commit()

    def delete_typology(self, typology_id: int) -> None:
        self._conn.execute("DELETE FROM typology WHERE id=?", (int(typology_id),))
        self._conn.commit()

    # ---- Lamelle ----
    def list_lamella_rulesets(self, category: str = "persiana") -> List[str]:
        return [r[0] for r in self._conn.execute("SELECT DISTINCT name FROM lamella_rule WHERE category=? ORDER BY name", (category,)).fetchall()]
    def list_lamella_rules(self, name: str, category: str = "persiana") -> List[Dict[str, Any]]:
        return [{"h_min": r[0], "h_max": r[1], "count": r[2], "pitch_mm": r[3]} for r in self._conn.execute(
            "SELECT h_min,h_max,count,pitch_mm FROM lamella_rule WHERE name=? AND category=? ORDER BY h_min", (name, category)).fetchall()]

    # ---- Catalogo ferramenta base ----
    def list_hw_brands(self) -> List[Dict[str, Any]]:
        return [{"id": r[0], "name": r[1]} for r in self._conn.execute("SELECT id,name FROM hw_brand ORDER BY name").fetchall()]
    def list_hw_series(self, brand_id: int) -> List[Dict[str, Any]]:
        return [{"id": r[0], "name": r[1]} for r in self._conn.execute("SELECT id,name FROM hw_series WHERE brand_id=? ORDER BY name", (brand_id,)).fetchall()]
    def list_hw_handle_types(self, brand_id: int, series_id: int) -> List[Dict[str, Any]]:
        return [{"id": r[0], "code": r[1], "name": r[2], "handle_offset_mm": float(r[3] or 0.0)} for r in self._conn.execute(
            "SELECT id,code,name,handle_offset_mm FROM hw_handle_type WHERE brand_id=? AND series_id=? ORDER BY name", (brand_id, series_id)).fetchall()]
    def list_hw_sash_subcats(self, brand_id: int, series_id: int) -> List[str]:
        return [r[0] for r in self._conn.execute(
            "SELECT DISTINCT sash_subcat FROM hw_arm_rule WHERE brand_id=? AND series_id=? ORDER BY sash_subcat", (brand_id, series_id)).fetchall()]

    def pick_arm_for_width(self, brand_id: int, series_id: int, sash_subcat: str, width_L: float) -> Optional[Dict[str, Any]]:
        r = self._conn.execute(
            "SELECT arm_code, arm_name, arm_class, astina_len FROM hw_arm_rule WHERE brand_id=? AND series_id=? AND sash_subcat=? AND ? BETWEEN w_min AND w_max",
            (brand_id, series_id, sash_subcat, float(width_L))
        ).fetchone()
        if not r: return None
        return {"arm_code": r[0], "arm_name": r[1], "arm_class": (r[2] or ""), "arm_len": (float(r[3]) if r[3] is not None else None)}

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

    # ---- Meccanismi e parti ----
    def list_mechanisms(self) -> List[Dict[str, Any]]:
        return [{"code": r[0], "name": r[1], "description": r[2] or ""} for r in self._conn.execute("SELECT code,name,description FROM hw_mechanism ORDER BY name").fetchall()]
    def create_mechanism(self, code: str, name: str, description: str = "") -> None:
        self._conn.execute("INSERT INTO hw_mechanism(code,name,description) VALUES(?,?,?)", (code, name, description)); self._conn.commit()
    def update_mechanism(self, code: str, name: str, description: str = "") -> None:
        self._conn.execute("UPDATE hw_mechanism SET name=?, description=? WHERE code=?", (name, description, code)); self._conn.commit()
    def delete_mechanism(self, code: str) -> None:
        self._conn.execute("DELETE FROM hw_mechanism WHERE code=?", (code,)); self._conn.commit()

    def list_mech_parts(self, mechanism_code: str) -> List[Dict[str, Any]]:
        return [{
            "id": r[0], "mechanism_code": r[1], "part_key": r[2], "display_name": r[3],
            "profile_name": r[4], "qty": int(r[5] or 1), "ang_sx": float(r[6] or 0.0), "ang_dx": float(r[7] or 0.0), "formula": r[8]
        } for r in self._conn.execute(
            "SELECT id,mechanism_code,part_key,display_name,profile_name,qty,ang_sx,ang_dx,formula FROM hw_mech_part WHERE mechanism_code=? ORDER BY part_key",
            (mechanism_code,)).fetchall()]

    def upsert_mech_part(self, mechanism_code: str, part_key: str, display_name: str, profile_name: str,
                         qty: int, ang_sx: float, ang_dx: float, formula: str) -> None:
        self._conn.execute(
            "INSERT INTO hw_mech_part(mechanism_code,part_key,display_name,profile_name,qty,ang_sx,ang_dx,formula) "
            "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(mechanism_code,part_key) DO UPDATE SET "
            "display_name=excluded.display_name, profile_name=excluded.profile_name, qty=excluded.qty, "
            "ang_sx=excluded.ang_sx, ang_dx=excluded.ang_dx, formula=excluded.formula",
            (mechanism_code, part_key, display_name, profile_name, int(qty), float(ang_sx), float(ang_dx), formula)
        ); self._conn.commit()

    def delete_mech_part(self, mechanism_code: str, part_key: str) -> None:
        self._conn.execute("DELETE FROM hw_mech_part WHERE mechanism_code=? AND part_key=?", (mechanism_code, part_key)); self._conn.commit()

    # ---- Opzioni ferramenta tipologia ----
    def list_typology_hw_options(self, typology_id: int) -> List[Dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT id,name,brand_id,series_id,subcat,handle_id,mechanism_code FROM typology_hw_option WHERE typology_id=? ORDER BY name",
            (typology_id,))
        out = []
        for r in cur.fetchall():
            out.append({"id": int(r[0]), "name": r[1], "brand_id": int(r[2]), "series_id": int(r[3]),
                        "subcat": r[4], "handle_id": (int(r[5]) if r[5] is not None else None), "mechanism_code": r[6] or ""})
        return out

    def create_typology_hw_option(self, typology_id: int, name: str, brand_id: int, series_id: int,
                                  subcat: str, handle_id: Optional[int], mechanism_code: Optional[str]) -> int:
        cur = self._conn.execute(
            "INSERT INTO typology_hw_option(typology_id,name,brand_id,series_id,subcat,handle_id,mechanism_code) VALUES(?,?,?,?,?,?,?)",
            (int(typology_id), name, int(brand_id), int(series_id), str(subcat),
             (int(handle_id) if handle_id is not None else None), (mechanism_code or None))
        ); self._conn.commit()
        return int(cur.lastrowid)

    def update_typology_hw_option(self, opt_id: int, name: str, brand_id: int, series_id: int,
                                  subcat: str, handle_id: Optional[int], mechanism_code: Optional[str]) -> None:
        self._conn.execute(
            "UPDATE typology_hw_option SET name=?, brand_id=?, series_id=?, subcat=?, handle_id=?, mechanism_code=? WHERE id=?",
            (name, int(brand_id), int(series_id), str(subcat), (int(handle_id) if handle_id is not None else None),
             (mechanism_code or None), int(opt_id))
        ); self._conn.commit()

    def delete_typology_hw_option(self, opt_id: int) -> None:
        self._conn.execute("DELETE FROM typology_hw_option WHERE id=?", (int(opt_id),)); self._conn.commit()

    def get_typology_hw_option(self, opt_id: int) -> Optional[Dict[str, Any]]:
        r = self._conn.execute(
            "SELECT id,typology_id,name,brand_id,series_id,subcat,handle_id,mechanism_code FROM typology_hw_option WHERE id=?", (int(opt_id),)
        ).fetchone()
        if not r: return None
        return {"id": int(r[0]), "typology_id": int(r[1]), "name": r[2], "brand_id": int(r[3]),
                "series_id": int(r[4]), "subcat": r[5], "handle_id": (int(r[6]) if r[6] is not None else None),
                "mechanism_code": (r[7] or "")}

    # ---- Mapping per elemento (override per opzione) ----
    def set_comp_hw_formula(self, typology_id: int, row_id: str, hw_option_id: int, formula: str) -> None:
        self._conn.execute(
            "INSERT INTO comp_hw_formula(typology_id,row_id,hw_option_id,formula) VALUES(?,?,?,?) "
            "ON CONFLICT(typology_id,row_id,hw_option_id) DO UPDATE SET formula=excluded.formula",
            (int(typology_id), str(row_id), int(hw_option_id), str(formula))
        ); self._conn.commit()

    def delete_comp_hw_formula(self, typology_id: int, row_id: str, hw_option_id: int) -> None:
        self._conn.execute("DELETE FROM comp_hw_formula WHERE typology_id=? AND row_id=? AND hw_option_id=?",
                           (int(typology_id), str(row_id), int(hw_option_id))); self._conn.commit()

    def get_comp_hw_formula(self, typology_id: int, row_id: str, hw_option_id: int) -> Optional[str]:
        r = self._conn.execute("SELECT formula FROM comp_hw_formula WHERE typology_id=? AND row_id=? AND hw_option_id=?",
                               (int(typology_id), str(row_id), int(hw_option_id))).fetchone()
        return r[0] if r else None

    def list_comp_hw_formulas_for_row(self, typology_id: int, row_id: str) -> List[Dict[str, Any]]:
        return [{"hw_option_id": int(r[0]), "formula": r[1]} for r in self._conn.execute(
            "SELECT hw_option_id,formula FROM comp_hw_formula WHERE typology_id=? AND row_id=?",
            (int(typology_id), str(row_id))).fetchall()]

    # ---- Override per parti meccanismo (per opzione) ----
    def list_typology_mech_part_formulas(self, typology_id: int, hw_option_id: int) -> List[Dict[str, Any]]:
        return [{"part_key": r[0], "formula": r[1]} for r in self._conn.execute(
            "SELECT part_key, formula FROM typology_mech_part_formula WHERE typology_id=? AND hw_option_id=?",
            (int(typology_id), int(hw_option_id))).fetchall()]

    def get_typology_mech_part_formula(self, typology_id: int, hw_option_id: int, part_key: str) -> Optional[str]:
        r = self._conn.execute(
            "SELECT formula FROM typology_mech_part_formula WHERE typology_id=? AND hw_option_id=? AND part_key=?",
            (int(typology_id), int(hw_option_id), str(part_key))
        ).fetchone()
        return r[0] if r else None

    def set_typology_mech_part_formula(self, typology_id: int, hw_option_id: int, part_key: str, formula: str) -> None:
        with contextlib.suppress(Exception):
            self._conn.execute(
                "DELETE FROM typology_mech_part_formula WHERE typology_id=? AND hw_option_id=? AND part_key=?",
                (int(typology_id), int(hw_option_id), str(part_key))
            )
        self._conn.execute(
            "INSERT INTO typology_mech_part_formula(typology_id, hw_option_id, part_key, formula) VALUES(?,?,?,?)",
            (int(typology_id), int(hw_option_id), str(part_key), str(formula))
        ); self._conn.commit()

    def delete_typology_mech_part_formula(self, typology_id: int, hw_option_id: int, part_key: str) -> None:
        self._conn.execute(
            "DELETE FROM typology_mech_part_formula WHERE typology_id=? AND hw_option_id=? AND part_key=?",
            (int(typology_id), int(hw_option_id), str(part_key))
        ); self._conn.commit()

    # ---- Libreria formule ferramenta (nuovo CRUD) ----
    def list_hw_formula_presets(self, brand_id: Optional[int] = None, series_id: Optional[int] = None,
                                subcat: Optional[str] = None, mechanism_code: Optional[str] = None,
                                scope: Optional[str] = None, target: Optional[str] = None) -> List[Dict[str, Any]]:
        q = "SELECT id,name,brand_id,series_id,subcat,mechanism_code,scope,target,formula,note FROM hw_formula_preset WHERE 1=1"
        args: List[Any] = []
        if brand_id is not None: q += " AND (brand_id IS NULL OR brand_id=?)"; args.append(int(brand_id))
        if series_id is not None: q += " AND (series_id IS NULL OR series_id=?)"; args.append(int(series_id))
        if subcat: q += " AND (subcat IS NULL OR subcat=?)"; args.append(subcat)
        if mechanism_code: q += " AND (mechanism_code IS NULL OR mechanism_code=?)"; args.append(mechanism_code)
        if scope: q += " AND (scope IS NULL OR scope=?)"; args.append(scope)
        if target: q += " AND (target IS NULL OR target=?)"; args.append(target)
        q += " ORDER BY name"
        return [{
            "id": int(r[0]), "name": r[1], "brand_id": r[2], "series_id": r[3], "subcat": r[4],
            "mechanism_code": r[5], "scope": r[6] or "", "target": r[7] or "", "formula": r[8] or "", "note": r[9] or ""
        } for r in self._conn.execute(q, tuple(args)).fetchall()]

    def create_hw_formula_preset(self, name: str, formula: str, brand_id: Optional[int] = None, series_id: Optional[int] = None,
                                 subcat: Optional[str] = None, mechanism_code: Optional[str] = None,
                                 scope: Optional[str] = None, target: Optional[str] = None, note: str = "") -> int:
        cur = self._conn.execute(
            "INSERT INTO hw_formula_preset(name,brand_id,series_id,subcat,mechanism_code,scope,target,formula,note) VALUES(?,?,?,?,?,?,?,?,?)",
            (name, (int(brand_id) if brand_id is not None else None), (int(series_id) if series_id is not None else None),
             (subcat or None), (mechanism_code or None), (scope or None), (target or None), formula, note)
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def update_hw_formula_preset(self, preset_id: int, name: str, formula: str, brand_id: Optional[int] = None, series_id: Optional[int] = None,
                                 subcat: Optional[str] = None, mechanism_code: Optional[str] = None,
                                 scope: Optional[str] = None, target: Optional[str] = None, note: str = "") -> None:
        self._conn.execute(
            "UPDATE hw_formula_preset SET name=?, brand_id=?, series_id=?, subcat=?, mechanism_code=?, scope=?, target=?, formula=?, note=? WHERE id=?",
            (name, (int(brand_id) if brand_id is not None else None), (int(series_id) if series_id is not None else None),
             (subcat or None), (mechanism_code or None), (scope or None), (target or None), formula, note, int(preset_id))
        ); self._conn.commit()

    def delete_hw_formula_preset(self, preset_id: int) -> None:
        self._conn.execute("DELETE FROM hw_formula_preset WHERE id=?", (int(preset_id),)); self._conn.commit()

    # ---- Seed demo minima ----
    def _maybe_seed(self):
        if int(self._conn.execute("SELECT COUNT(*) FROM hw_brand").fetchone()[0]) == 0:
            self._conn.execute("INSERT INTO hw_brand(name) VALUES(?)", ("DemoHW",))
            brand_id = int(self._conn.execute("SELECT id FROM hw_brand WHERE name=?", ("DemoHW",)).fetchone()[0])
            self._conn.execute("INSERT INTO hw_series(brand_id,name) VALUES(?,?)", (brand_id, "TT-100"))
            series_id = int(self._conn.execute("SELECT id FROM hw_series WHERE brand_id=? AND name=?", (brand_id, "TT-100")).fetchone()[0])
            self._conn.executemany(
                "INSERT INTO hw_handle_type(brand_id,series_id,code,name,handle_offset_mm) VALUES(?,?,?,?,?)",
                [(brand_id, series_id, "H-A", "Maniglia A", 102.0), (brand_id, series_id, "H-B", "Maniglia B", 125.0)]
            )
            with contextlib.suppress(Exception):
                self._conn.execute("ALTER TABLE hw_arm_rule ADD COLUMN arm_class TEXT")
            with contextlib.suppress(Exception):
                self._conn.execute("ALTER TABLE hw_arm_rule ADD COLUMN astina_len REAL")
            self._conn.executemany(
                "INSERT INTO hw_arm_rule(brand_id,series_id,sash_subcat,w_min,w_max,arm_code,arm_name,arm_class,astina_len) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                [
                    (brand_id, series_id, "battente_standard", 350.0, 600.0,  "ARM-0", "Braccio 0", "tipo0", 180.0),
                    (brand_id, series_id, "battente_standard", 600.01, 900.0, "ARM-1", "Braccio 1", "tipo1", 220.0),
                    (brand_id, series_id, "battente_standard", 900.01, 1200.0,"ARM-2", "Braccio 2", "tipo2", 260.0),
                ]
            )
            # Preset demo
            self.create_hw_formula_preset("Montante anta (normale)", "H - handle_offset - 70",
                                          brand_id=brand_id, series_id=series_id, subcat="battente_standard",
                                          mechanism_code="normale", scope="component", target="montante_anta",
                                          note="Esempio formula per montante")
            self._conn.commit()
        if int(self._conn.execute("SELECT COUNT(*) FROM hw_mechanism").fetchone()[0]) == 0:
            self.create_mechanism("normale", "Anta normale", "Due astine montante")
            self.upsert_mech_part("normale", "AST_SUP_MONT", "Astina superiore (montante)", "ASTINA", 1, 0.0, 0.0, "H - handle_offset - 70")
            self.upsert_mech_part("normale", "AST_INF_MONT", "Astina inferiore (montante)", "ASTINA", 1, 0.0, 0.0, "H - 80")
            self.create_mechanism("ribalta_cremonese", "Ribalta cremonese", "Tre astine (montante+braccio)")
            self.upsert_mech_part("ribalta_cremonese", "AST_SUP_MONT", "Astina superiore (montante)", "ASTINA", 1, 0.0, 0.0, "H - handle_offset - 70")
            self.upsert_mech_part("ribalta_cremonese", "AST_INF_MONT", "Astina inferiore (montante)", "ASTINA", 1, 0.0, 0.0, "H - 90")
            self.upsert_mech_part("ribalta_cremonese", "AST_BRACCIO_TRAV", "Astina braccio (traverso)", "ASTINA", 1, 0.0, 0.0, "arm_len")
            self.create_mechanism("ribalta_dk", "Ribalta DK", "Tre astine; formule montante diverse")
            self.upsert_mech_part("ribalta_dk", "AST_SUP_MONT", "Astina superiore (montante)", "ASTINA", 1, 0.0, 0.0, "H - handle_offset - 55")
            self.upsert_mech_part("ribalta_dk", "AST_INF_MONT", "Astina inferiore (montante)", "ASTINA", 1, 0.0, 0.0, "H - 85")
            self.upsert_mech_part("ribalta_dk", "AST_BRACCIO_TRAV", "Astina braccio (traverso)", "ASTINA", 1, 0.0, 0.0, "arm_len")
            self._conn.commit()
