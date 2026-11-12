"""Lớp truy cập DB: PostgreSQL (AWS RDS) khi có DATABASE_URL, ngược lại dùng SQLite (chạy thử trên máy).

Code còn lại giữ nguyên kiểu viết SQL với placeholder `?`; file này tự đổi sang `%s` cho Postgres.
Cột thời gian giữ dạng TEXT 'YYYY-MM-DD HH:MM:SS' (UTC) như trước để stats.py không phải đổi.
"""
import atexit
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

DATABASE_URL = os.getenv("DATABASE_URL", "")
DB_PATH = os.getenv("DB_PATH", "data/app.db")
IS_PG = DATABASE_URL.startswith(("postgres://", "postgresql://"))
_lock = threading.Lock()
_pool = None


def now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _pg_pool():
    global _pool
    if _pool is None:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
        _pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=5, kwargs={"row_factory": dict_row}, open=True)
        atexit.register(_pool.close)
    return _pool


def _sqlite():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def _sql(sql: str) -> str:
    return sql.replace("?", "%s") if IS_PG else sql


SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions(
    id TEXT PRIMARY KEY, sa_id TEXT, sa_name TEXT, store TEXT,
    created_at TEXT NOT NULL, audio_path TEXT, duration REAL,
    status TEXT, error TEXT, transcript_text TEXT, segments_json TEXT,
    client_id TEXT, source TEXT, asr_engine TEXT, parser_version TEXT, parser_match INTEGER);
CREATE TABLE IF NOT EXISTS orders(
    id {pk}, session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE, closing_text TEXT,
    customer_confirm TEXT, items_json TEXT, needs_review INTEGER,
    reviewed INTEGER DEFAULT 0, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_orders_session ON orders(session_id);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);
CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at);
CREATE INDEX IF NOT EXISTS idx_sessions_sa ON sessions(sa_id);

-- Danh mục SKU (đồng bộ từ data/sku_catalog.csv mỗi lần API khởi động)
CREATE TABLE IF NOT EXISTS skus(
    sku_id TEXT PRIMARY KEY, name TEXT NOT NULL, unit TEXT, brand TEXT, aliases TEXT,
    active INTEGER DEFAULT 1, barcode TEXT);

-- Dữ liệu tổ chức (nạp từ file headcount bằng scripts/import_headcount.py). KHÔNG chứa CCCD/ngày sinh/SĐT/email cá nhân/lương.
CREATE TABLE IF NOT EXISTS supervisors(
    ess_code TEXT PRIMARY KEY, name TEXT, om_code TEXT, om_name TEXT, fc_name TEXT, region TEXT);
CREATE TABLE IF NOT EXISTS stores(
    ess_store_code TEXT PRIMARY KEY, name TEXT, region TEXT, province TEXT,
    key_account TEXT, customer TEXT, sr_ess_code TEXT REFERENCES supervisors(ess_code));
CREATE TABLE IF NOT EXISTS staff(
    ess_code TEXT PRIMARY KEY, ba_code TEXT, name TEXT NOT NULL, position TEXT, level TEXT,
    bu TEXT, category TEXT, contract_status TEXT, work_status TEXT,
    joined_at TEXT, left_at TEXT, store_code TEXT REFERENCES stores(ess_store_code),
    sr_ess_code TEXT REFERENCES supervisors(ess_code), updated_at TEXT);
CREATE INDEX IF NOT EXISTS idx_staff_ba ON staff(ba_code);
CREATE INDEX IF NOT EXISTS idx_staff_store ON staff(store_code);

-- Dấu giọng SA (vector embedding, KHÔNG lưu âm thanh). Dữ liệu sinh trắc học: chỉ lưu khi SA đã đồng ý (consent_at).
CREATE TABLE IF NOT EXISTS voiceprints(
    sa_id TEXT PRIMARY KEY, embedding_json TEXT NOT NULL, dim INTEGER, model TEXT,
    n_samples INTEGER, consent_at TEXT NOT NULL, updated_at TEXT NOT NULL);
-- Đăng nhập BA (app/auth.py). ba_key = mã BA viết thường. Mật khẩu: băm scrypt (hex) + salt riêng, token chỉ lưu SHA-256.
CREATE TABLE IF NOT EXISTS ba_auth(
    ba_key TEXT PRIMARY KEY, pw_hash TEXT NOT NULL, pw_salt TEXT NOT NULL,
    fails INTEGER DEFAULT 0, locked_until TEXT DEFAULT '', updated_at TEXT);
CREATE TABLE IF NOT EXISTS auth_tokens(
    token_hash TEXT PRIMARY KEY, ba_key TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_auth_tokens_ba ON auth_tokens(ba_key);
"""


# Cột thêm cho phiên tạo từ app (nhận dạng giọng nói trên máy): DB đã có từ trước được thêm cột khi khởi động
_SESSION_COLS = [("client_id", "TEXT"), ("source", "TEXT"), ("asr_engine", "TEXT"),
                 ("parser_version", "TEXT"), ("parser_match", "INTEGER")]
# app tự sinh client_id: gửi lại cùng phiên (mạng chập chờn / retry) không tạo bản trùng
_CLIENT_IDX = ("CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_client ON sessions(sa_id, client_id) "
               "WHERE client_id IS NOT NULL")


def init():
    pk = "BIGSERIAL PRIMARY KEY" if IS_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"
    script = SCHEMA.format(pk=pk)
    if IS_PG:
        with _pg_pool().connection() as c:
            for stmt in filter(str.strip, script.split(";")):
                c.execute(stmt)
            # DB đã có từ trước (bảng skus chưa có cột barcode): thêm cột, rồi mới tạo index
            c.execute("ALTER TABLE skus ADD COLUMN IF NOT EXISTS barcode TEXT")
            c.execute("CREATE INDEX IF NOT EXISTS idx_skus_barcode ON skus(barcode)")
            for col, typ in _SESSION_COLS:
                c.execute(f"ALTER TABLE sessions ADD COLUMN IF NOT EXISTS {col} {typ}")
            c.execute(_CLIENT_IDX)
    else:
        with _sqlite() as c:
            c.executescript(script)
            if "barcode" not in [r[1] for r in c.execute("PRAGMA table_info(skus)")]:
                c.execute("ALTER TABLE skus ADD COLUMN barcode TEXT")
            c.execute("CREATE INDEX IF NOT EXISTS idx_skus_barcode ON skus(barcode)")
            have = [r[1] for r in c.execute("PRAGMA table_info(sessions)")]
            for col, typ in _SESSION_COLS:
                if col not in have:
                    c.execute(f"ALTER TABLE sessions ADD COLUMN {col} {typ}")
            c.execute(_CLIENT_IDX)


def execute(sql, args=()):
    """Chạy lệnh ghi. Trả về id của dòng vừa chèn khi chèn vào bảng orders (nếu không thì None/0)."""
    want_id = sql.lstrip().upper().startswith("INSERT INTO ORDERS")
    with _lock:
        if IS_PG:
            q = _sql(sql) + (" RETURNING id" if want_id else "")
            with _pg_pool().connection() as c:
                cur = c.execute(q, args)
                return cur.fetchone()["id"] if want_id else None
        with _sqlite() as c:
            return c.execute(sql, args).lastrowid


def query(sql, args=()):
    with _lock:
        if IS_PG:
            with _pg_pool().connection() as c:
                return list(c.execute(_sql(sql), args).fetchall())
        with _sqlite() as c:
            return [dict(r) for r in c.execute(sql, args).fetchall()]


def save_orders(session_id: str, parsed: dict, created_at: str | None = None):
    for o in parsed["orders"]:
        execute(
            "INSERT INTO orders(session_id,closing_text,customer_confirm,items_json,needs_review,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (session_id, o["closing_text"], o["customer_confirm"],
             json.dumps(o["items"], ensure_ascii=False), int(o["needs_review"]), created_at or now_str()),
        )


def sync_skus(catalog_skus: dict, rows: list[dict] | None = None):
    """Upsert danh mục SKU từ CSV vào bảng skus."""
    for r in rows or []:
        brand = r["name"].split()[0]
        execute(
            "INSERT INTO skus(sku_id,name,unit,brand,aliases,barcode) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(sku_id) DO UPDATE SET name=excluded.name, unit=excluded.unit, "
            "brand=excluded.brand, aliases=excluded.aliases, barcode=excluded.barcode",
            (r["sku_id"], r["name"], r["unit"], brand, r["aliases"], r.get("barcode") or None),
        )
