import sqlite3
from pathlib import Path
import json

# Database condiviso per profili/spessori (interoperabile con Tipologie)
# Percorso unico: data/profiles.db a livello progetto
DB_PATH = Path(__file__).resolve().parents[3] / "data" / "profiles.db"

class ProfilesStore:
    def __init__(self):
        self._ensure_db()

    def _connect(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(DB_PATH)

    def _ensure_db(self):
        with self._connect() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    thickness REAL NOT NULL DEFAULT 0
                )
            """)
            # Tabella opzionale per metadata/shape del profilo (non rompe compatibilità)
            con.execute("""
                CREATE TABLE IF NOT EXISTS profile_shapes (
                    profile_id INTEGER UNIQUE NOT NULL,
                    dxf_path TEXT,
                    bbox_w REAL,
                    bbox_h REAL,
                    meta_json TEXT,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
                )
            """)
            con.commit()

    # ---- CRUD profili (spessore) ----
    def upsert_profile(self, name: str, thickness: float):
        with self._connect() as con:
            con.execute("""
                INSERT INTO profiles(name, thickness) VALUES(?, ?)
                ON CONFLICT(name) DO UPDATE SET thickness=excluded.thickness
            """, (name, float(thickness)))
            con.commit()

    def list_profiles(self):
        with self._connect() as con:
            cur = con.execute("SELECT id, name, thickness FROM profiles ORDER BY name ASC")
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def get_profile(self, name: str):
        with self._connect() as con:
            cur = con.execute("SELECT id, name, thickness FROM profiles WHERE name=?", (name,))
            row = cur.fetchone()
            if not row:
                return None
            return {"id": row[0], "name": row[1], "thickness": row[2]}

    def delete_profile(self, name: str) -> bool:
        with self._connect() as con:
            cur = con.execute("DELETE FROM profiles WHERE name=?", (name,))
            con.commit()
            return cur.rowcount > 0

    # ---- Metadata shape DXF (facoltativo) ----
    def upsert_profile_shape(self, name: str, dxf_path: str | None, bbox_w: float | None, bbox_h: float | None, meta: dict | None):
        with self._connect() as con:
            # Assicura esistenza profilo
            cur = con.execute("SELECT id FROM profiles WHERE name=?", (name,))
            row = cur.fetchone()
            if not row:
                con.execute("INSERT INTO profiles(name, thickness) VALUES(?, ?)", (name, 0.0))
                pid = con.execute("SELECT id FROM profiles WHERE name=?", (name,)).fetchone()[0]
            else:
                pid = row[0]
            payload = json.dumps(meta or {}, ensure_ascii=False)
            # upsert su profile_shapes
            con.execute("""
                INSERT INTO profile_shapes(profile_id, dxf_path, bbox_w, bbox_h, meta_json)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(profile_id) DO UPDATE SET
                    dxf_path=excluded.dxf_path,
                    bbox_w=excluded.bbox_w,
                    bbox_h=excluded.bbox_h,
                    meta_json=excluded.meta_json
            """, (pid, dxf_path or "", float(bbox_w or 0.0), float(bbox_h or 0.0), payload))
            con.commit()

    def get_profile_shape(self, name: str) -> dict | None:
        with self._connect() as con:
            cur = con.execute("""
                SELECT ps.dxf_path, ps.bbox_w, ps.bbox_h, ps.meta_json
                FROM profile_shapes ps
                JOIN profiles p ON p.id = ps.profile_id
                WHERE p.name=?
            """, (name,))
            row = cur.fetchone()
            if not row:
                return None
            dxf_path, w, h, meta_json = row
            try:
                meta = json.loads(meta_json or "{}")
            except Exception:
                meta = {}
            return {"dxf_path": dxf_path, "bbox_w": w, "bbox_h": h, "meta": meta}
