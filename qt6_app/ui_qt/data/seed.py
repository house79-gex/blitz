from __future__ import annotations
import os
from .db import get_conn

SEED_SQL_PATH = os.path.join("data", "seed.sql")

def seed_if_empty():
    with get_conn() as cx:
        # Se non ci sono tipologie, applichiamo la seed.sql
        cur = cx.execute("SELECT COUNT(*) AS n FROM tipologie")
        n = int(cur.fetchone()["n"])
        if n == 0 and os.path.exists(SEED_SQL_PATH):
            with open(SEED_SQL_PATH, "r", encoding="utf-8") as f:
                cx.executescript(f.read())
