import sqlite3
from pathlib import Path

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
            con.commit()

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
