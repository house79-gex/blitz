from __future__ import annotations
import sqlite3
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ui_qt.services.typologies_store import default_db_path

SCHEMA = """
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    customer TEXT,
    data_json TEXT NOT NULL,        -- JSON serializzato della commessa (rows + meta)
    created_at INTEGER,
    updated_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer);
"""

def _now_ts() -> int:
    return int(time.time())

def default_orders_db_path() -> Path:
    # usa lo stesso DB delle tipologie per comodità
    return default_db_path()

class OrdersStore:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path) if db_path else default_orders_db_path()
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
            try:
                self._conn.close()
            except Exception:
                pass
        self._conn = None

    def create_order(self, name: str, customer: str, data: Dict[str, Any]) -> int:
        ts = _now_ts()
        jd = json.dumps(data, ensure_ascii=False)
        cur = self._conn.execute(
            "INSERT INTO orders(name,customer,data_json,created_at,updated_at) VALUES(?,?,?,?,?)",
            (name, customer or "", jd, ts, ts)
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def update_order(self, order_id: int, name: str, customer: str, data: Dict[str, Any]) -> None:
        ts = _now_ts()
        jd = json.dumps(data, ensure_ascii=False)
        self._conn.execute(
            "UPDATE orders SET name=?, customer=?, data_json=?, updated_at=? WHERE id=?",
            (name, customer or "", jd, ts, int(order_id))
        )
        self._conn.commit()

    def delete_order(self, order_id: int) -> None:
        self._conn.execute("DELETE FROM orders WHERE id=?", (int(order_id),))
        self._conn.commit()

    def get_order(self, order_id: int) -> Optional[Dict[str, Any]]:
        r = self._conn.execute("SELECT id,name,customer,data_json,created_at,updated_at FROM orders WHERE id=?", (int(order_id),)).fetchone()
        if not r:
            return None
        try:
            data = json.loads(r[3]) if r[3] else {}
        except Exception:
            data = {}
        return {"id": int(r[0]), "name": r[1], "customer": r[2], "data": data, "created_at": int(r[4]), "updated_at": int(r[5])}

    def list_orders(self, limit: int = 200) -> List[Dict[str, Any]]:
        cur = self._conn.execute("SELECT id,name,customer,created_at,updated_at FROM orders ORDER BY updated_at DESC LIMIT ?", (int(limit),))
        out = []
        for r in cur.fetchall():
            out.append({"id": int(r[0]), "name": r[1], "customer": r[2], "created_at": int(r[3]), "updated_at": int(r[4])})
        return out

    def list_orders_by_customer(self, customer: str, limit: int = 200) -> List[Dict[str, Any]]:
        cur = self._conn.execute("SELECT id,name,customer,created_at,updated_at FROM orders WHERE customer=? ORDER BY updated_at DESC LIMIT ?", (customer, int(limit)))
        out = []
        for r in cur.fetchall():
            out.append({"id": int(r[0]), "name": r[1], "customer": r[2], "created_at": int(r[3]), "updated_at": int(r[4])})
        return out
