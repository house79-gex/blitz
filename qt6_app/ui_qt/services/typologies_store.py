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

-- Formule multiple per gruppi (con metadati per costruire elementi extra)
CREATE TABLE IF NOT EXISTS typology_multi_formula (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    typology_id  INTEGER NOT NULL REFERENCES typology(id) ON DELETE CASCADE,
    group_name   TEXT NOT NULL,
    label        TEXT NOT NULL,
    formula      TEXT NOT NULL,
    profile_name TEXT,                 -- per elementi extra
    qty          INTEGER DEFAULT 1,
    ang_sx       REAL DEFAULT 0.0,
    ang_dx       REAL DEFAULT 0.0,
    offset       REAL DEFAULT 0.0,
    note         TEXT,
    UNIQUE(typology_id, group_name, label)
);

-- Regole variabili per gruppo: var_name vale 'value' quando L è nel range [l_min, l_max]
CREATE TABLE IF NOT EXISTS typology_multi_var_rule (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    typology_id  INTEGER NOT NULL REFERENCES typology(id) ON DELETE CASCADE,
    group_name   TEXT NOT NULL,
    var_name     TEXT NOT NULL,
    l_min        REAL NOT NULL,
    l_max        REAL NOT NULL,
    value        REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_typology_comp_typ ON typology_component(typology_id, ord);
CREATE INDEX IF NOT EXISTS idx_typology_var_typ  ON typology_var(typology_id);
CREATE INDEX IF NOT EXISTS idx_tmf_typ_group ON typology_multi_formula(typology_id, group_name);
CREATE INDEX IF NOT EXISTS idx_tmr_typ_group ON typology_multi_var_rule(typology_id, group_name);
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

    def _open(self):
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA foreign_keys=ON")

    def _ensure_schema(self):
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def _migrate_schema(self):
        # Aggiungi colonne ai multi_formula se mancanti
        with contextlib.suppress(Exception):
            self._conn.execute("ALTER TABLE typology_multi_formula ADD COLUMN profile_name TEXT")
        with contextlib.suppress(Exception):
            self._conn.execute("ALTER TABLE typology_multi_formula ADD COLUMN qty INTEGER DEFAULT 1")
        with contextlib.suppress(Exception):
            self._conn.execute("ALTER TABLE typology_multi_formula ADD COLUMN ang_sx REAL DEFAULT 0.0")
        with contextlib.suppress(Exception):
            self._conn.execute("ALTER TABLE typology_multi_formula ADD COLUMN ang_dx REAL DEFAULT 0.0")
        with contextlib.suppress(Exception):
            self._conn.execute("ALTER TABLE typology_multi_formula ADD COLUMN offset REAL DEFAULT 0.0")
        # Crea tabella var_rule se non esiste (è nella SCHEMA)
        self._conn.commit()

    def close(self):
        if self._conn:
            with contextlib.suppress(Exception):
                self._conn.close()
        self._conn = None

    # -------- Tipologie (CRUD base) --------
    def list_typologies(self) -> List[Dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT id, name, category, material, pezzi_totali, updated_at FROM typology ORDER BY name ASC"
        )
        return [{"id": r[0], "name": r[1], "category": r[2], "material": r[3], "pezzi_totali": r[4], "updated_at": r[5]} for r in cur.fetchall()]

    def get_typology_full(self, typology_id: int) -> Optional[Dict[str, Any]]:
        r = self._conn.execute(
            "SELECT id, name, category, material, ref_quota, extra_detrazione, pezzi_totali, note, created_at, updated_at "
            "FROM typology WHERE id=?", (int(typology_id),)
        ).fetchone()
        if not r: return None
        vars_map = {n: float(v) for (n, v) in self._conn.execute(
            "SELECT name,value FROM typology_var WHERE typology_id=? ORDER BY id", (int(typology_id),)).fetchall()}
        comps = []
        for c in self._conn.execute(
            "SELECT row_id, name, profile_name, quantity, ang_sx, ang_dx, formula, offset, note "
            "FROM typology_component WHERE typology_id=? ORDER BY ord, id", (int(typology_id),)).fetchall():
            comps.append({"id_riga": c[0] or "", "nome": c[1] or "", "profilo_nome": c[2] or "",
                          "quantita": int(c[3] or 0), "ang_sx": float(c[4] or 0.0), "ang_dx": float(c[5] or 0.0),
                          "formula_lunghezza": c[6] or "", "offset_mm": float(c[7] or 0.0), "note": c[8] or ""})
        return {
            "id": int(r[0]), "nome": r[1], "categoria": r[2] or "", "materiale": r[3] or "",
            "riferimento_quota": r[4] or "esterna", "extra_detrazione_mm": float(r[5] or 0.0),
            "pezzi_totali": int(r[6] or 1), "note": r[7] or "",
            "variabili_locali": vars_map, "componenti": comps,
            "created_at": r[8], "updated_at": r[9]
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
             int(data.get("pezzi_totali") or 1), data.get("note",""), ts, int(typology_id))
        )
        self._conn.execute("DELETE FROM typology_var WHERE typology_id=?", (int(typology_id),))
        self._conn.execute("DELETE FROM typology_component WHERE typology_id=?", (int(typology_id),))
        for k, v in (data.get("variabili_locali") or {}).items():
            try: vv = float(v)
            except Exception: vv = 0.0
            self._conn.execute("INSERT INTO typology_var(typology_id,name,value) VALUES(?,?,?)", (int(typology_id), k, vv))
        for idx, c in enumerate(data.get("componenti") or []):
            self._conn.execute(
                "INSERT INTO typology_component(typology_id,ord,row_id,name,profile_name,quantity,ang_sx,ang_dx,formula,offset,note) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (int(typology_id), idx, c.get("id_riga",""), c.get("nome",""), c.get("profilo_nome",""),
                 int(c.get("quantita",0) or 0), float(c.get("ang_sx",0.0) or 0.0), float(c.get("ang_dx",0.0) or 0.0),
                 c.get("formula_lunghezza",""), float(c.get("offset_mm",0.0) or 0.0), c.get("note","")))
        self._conn.commit()

    def delete_typology(self, typology_id: int) -> None:
        self._conn.execute("DELETE FROM typology WHERE id=?", (int(typology_id),))
        self._conn.commit()

    # -------- Formule multiple (gruppi) --------
    def list_multi_formula_groups(self, typology_id: int) -> List[str]:
        cur = self._conn.execute("SELECT DISTINCT group_name FROM typology_multi_formula WHERE typology_id=? ORDER BY group_name", (int(typology_id),))
        return [r[0] for r in cur.fetchall()]

    def list_multi_formulas(self, typology_id: int, group_name: str) -> List[Dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT label, formula, profile_name, qty, ang_sx, ang_dx, offset, note "
            "FROM typology_multi_formula WHERE typology_id=? AND group_name=? ORDER BY label",
            (int(typology_id), str(group_name))
        )
        out: List[Dict[str, Any]] = []
        for r in cur.fetchall():
            out.append({
                "label": r[0], "formula": r[1], "profile_name": r[2] or "",
                "qty": int(r[3] or 1), "ang_sx": float(r[4] or 0.0), "ang_dx": float(r[5] or 0.0),
                "offset": float(r[6] or 0.0), "note": r[7] or ""
            })
        return out

    def upsert_multi_formula(self, typology_id: int, group_name: str, label: str, formula: str,
                             profile_name: Optional[str] = None, qty: int = 1, ang_sx: float = 0.0, ang_dx: float = 0.0,
                             offset: float = 0.0, note: str = "") -> None:
        with contextlib.suppress(Exception):
            self._conn.execute(
                "DELETE FROM typology_multi_formula WHERE typology_id=? AND group_name=? AND label=?",
                (int(typology_id), str(group_name), str(label))
            )
        self._conn.execute(
            "INSERT INTO typology_multi_formula(typology_id, group_name, label, formula, profile_name, qty, ang_sx, ang_dx, offset, note) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (int(typology_id), str(group_name), str(label), str(formula), (profile_name or None), int(qty), float(ang_sx), float(ang_dx), float(offset), str(note or ""))
        )
        self._conn.commit()

    def delete_multi_formula(self, typology_id: int, group_name: str, label: str) -> None:
        self._conn.execute(
            "DELETE FROM typology_multi_formula WHERE typology_id=? AND group_name=? AND label=?",
            (int(typology_id), str(group_name), str(label))
        )
        self._conn.commit()

    # -------- Regole variabili (dipendenti da L) --------
    def list_multi_var_rules(self, typology_id: int, group_name: str) -> List[Dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT id, var_name, l_min, l_max, value FROM typology_multi_var_rule WHERE typology_id=? AND group_name=? ORDER BY l_min",
            (int(typology_id), str(group_name))
        )
        return [{"id": int(r[0]), "var_name": r[1], "l_min": float(r[2]), "l_max": float(r[3]), "value": float(r[4])} for r in cur.fetchall()]

    def replace_multi_var_rules(self, typology_id: int, group_name: str, rules: List[Dict[str, Any]]) -> None:
        self._conn.execute("DELETE FROM typology_multi_var_rule WHERE typology_id=? AND group_name=?", (int(typology_id), str(group_name)))
        for r in rules:
            self._conn.execute(
                "INSERT INTO typology_multi_var_rule(typology_id, group_name, var_name, l_min, l_max, value) VALUES(?,?,?,?,?,?)",
                (int(typology_id), str(group_name), str(r["var_name"]), float(r["l_min"]), float(r["l_max"]), float(r["value"]))
            )
        self._conn.commit()
