import os
import sqlite3
import threading

DB_PATH = os.getenv("DB_PATH", "data/app.db")
_lock = threading.Lock()


def conn():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS sessions(
            id TEXT PRIMARY KEY, sa_id TEXT, sa_name TEXT, store TEXT,
            created_at TEXT DEFAULT (datetime('now')), audio_path TEXT, duration REAL,
            status TEXT, error TEXT, transcript_text TEXT, segments_json TEXT);
        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, closing_text TEXT,
            customer_confirm TEXT, items_json TEXT, needs_review INTEGER,
            reviewed INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now')));
        CREATE INDEX IF NOT EXISTS idx_orders_session ON orders(session_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at);
        """)


def execute(sql, args=()):
    with _lock, conn() as c:
        return c.execute(sql, args).lastrowid


def query(sql, args=()):
    with _lock, conn() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def save_orders(session_id: str, parsed: dict):
    import json
    for o in parsed["orders"]:
        execute(
            "INSERT INTO orders(session_id,closing_text,customer_confirm,items_json,needs_review) VALUES(?,?,?,?,?)",
            (session_id, o["closing_text"], o["customer_confirm"],
             json.dumps(o["items"], ensure_ascii=False), int(o["needs_review"])),
        )
