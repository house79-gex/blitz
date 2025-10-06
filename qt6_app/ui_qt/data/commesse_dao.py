from __future__ import annotations
from typing import Dict, Any, List, Optional
from .db import get_conn

def list_all() -> List[Dict[str, Any]]:
    with get_conn() as cx:
        cur = cx.execute("SELECT * FROM commesse ORDER BY id DESC")
        return [dict(r) for r in cur.fetchall()]

def get_by_id(cid: int) -> Optional[Dict[str, Any]]:
    with get_conn() as cx:
        cur = cx.execute("SELECT * FROM commesse WHERE id = ?", (cid,))
        r = cur.fetchone()
        return dict(r) if r else None

def insert(cliente: str = "", note: str = "") -> int:
    with get_conn() as cx:
        cur = cx.execute("INSERT INTO commesse (cliente, note) VALUES (?,?)", (cliente, note))
        return int(cur.lastrowid)

def update(cid: int, cliente: str, note: str) -> None:
    with get_conn() as cx:
        cx.execute("UPDATE commesse SET cliente=?, note=? WHERE id=?", (cliente, note, cid))

def items_for_commessa(cid: int) -> List[Dict[str, Any]]:
    sql = """SELECT ci.*, t.nome AS tipologia_nome
             FROM commessa_items ci
             LEFT JOIN tipologie t ON t.id = ci.tipologia_id
             WHERE ci.commessa_id = ?
             ORDER BY ci.id"""
    with get_conn() as cx:
        cur = cx.execute(sql, (cid,))
        return [dict(r) for r in cur.fetchall()]

def add_item(cid: int, tipologia_id: int | None, len_mm: float, qty: int) -> int:
    with get_conn() as cx:
        cur = cx.execute(
            "INSERT INTO commessa_items (commessa_id, tipologia_id, len_mm, qty) VALUES (?,?,?,?)",
            (cid, tipologia_id, float(len_mm), int(qty)),
        )
        return int(cur.lastrowid)

def delete_item(item_id: int) -> None:
    with get_conn() as cx:
        cx.execute("DELETE FROM commessa_items WHERE id = ?", (item_id,))
