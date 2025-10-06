from __future__ import annotations
import os
import sqlite3

DB_PATH = os.path.join("data", "app.db")

def get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    from .seed import seed_if_empty  # import locale per evitare cicli
    with get_conn() as cx:
        cx.executescript(SCHEMA_SQL)
    seed_if_empty()

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS tipologie (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL,
  categoria TEXT DEFAULT '',
  materiale TEXT DEFAULT '',
  rif TEXT DEFAULT '',
  extra TEXT DEFAULT '',
  attiva INTEGER NOT NULL DEFAULT 1,
  comp INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS commesse (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cliente TEXT DEFAULT '',
  note TEXT DEFAULT '',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS commessa_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  commessa_id INTEGER NOT NULL REFERENCES commesse(id) ON DELETE CASCADE,
  tipologia_id INTEGER REFERENCES tipologie(id),
  len_mm REAL NOT NULL DEFAULT 0,
  qty INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS stock_bars (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  material TEXT DEFAULT '',
  length_mm REAL NOT NULL,
  available_qty INTEGER NOT NULL DEFAULT 0
);
"""
