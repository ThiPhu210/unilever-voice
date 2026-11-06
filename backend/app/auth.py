"""Đăng nhập BA (mã BA + mật khẩu tự đặt) và phân quyền cho mọi endpoint.

Hai loại người gọi API cùng tồn tại:
- admin: web Coach / công cụ nội bộ, dùng API_KEY dùng chung như trước (header X-API-Key hoặc ?key=). Thấy mọi dữ liệu.
  Nếu KHÔNG đặt biến môi trường API_KEY thì coi mọi request không có token là admin (chế độ chạy thử như trước đây).
- ba: app điện thoại, dùng token đăng nhập (Authorization: Bearer ...). Chỉ thấy / sửa dữ liệu của chính mình.

Danh sách BA được phép đăng nhập = bảng `staff` (cột ba_code, nạp bằng scripts/import_headcount.py), nên mã nào không có
trong headcount (hoặc đã nghỉ việc) thì không đăng nhập được. Lần đầu BA tự đặt mật khẩu; server chỉ lưu băm scrypt.
Token là chuỗi ngẫu nhiên; DB chỉ lưu SHA-256 của token. Quản lý đặt lại mật khẩu: DELETE /api/auth/password/{ba_code} (admin).
"""
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from . import db

MIN_PW = 8
TOKEN_DAYS = int(os.getenv("TOKEN_DAYS", "30"))
MAX_FAILS, LOCK_MINUTES = 5, 10
PUBLIC_PATHS = {"/api/health", "/api/auth/status", "/api/auth/login", "/api/auth/set-password"}

router = APIRouter(prefix="/api/auth")


@dataclass
class Principal:
    kind: str                 # "admin" | "ba" | "public"
    sa_id: str = ""           # mã BA chuẩn (đúng chữ hoa/thường trong headcount), chỉ có khi kind == "ba"
    sa_name: str = ""
    store: str = ""


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _scrypt(pw: str, salt: bytes) -> str:
    return hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32).hex()


def _roster(ba_code: str) -> dict | None:
    """BA đang làm việc có mã này (không phân biệt hoa thường). Mã trùng thì ưu tiên dòng chưa nghỉ, mới cập nhật nhất."""
    rows = db.query(
        "SELECT s.ba_code, s.name, s.left_at, st.name AS store_name FROM staff s "
        "LEFT JOIN stores st ON st.ess_store_code = s.store_code WHERE lower(s.ba_code)=? "
        "ORDER BY CASE WHEN s.left_at IS NULL THEN 0 ELSE 1 END, s.updated_at DESC LIMIT 1",
        (ba_code.strip().lower(),))
    r = rows[0] if rows else None
    if r and r["left_at"] and r["left_at"] <= db.now_str()[:10]:
        return None   # đã nghỉ việc
    return r


def _key(ba_code: str) -> str:
    return ba_code.strip().lower()


def _issue(r: dict) -> dict:
    tok = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db.execute("DELETE FROM auth_tokens WHERE expires_at < ?", (_fmt(now),))
    db.execute("INSERT INTO auth_tokens(token_hash,ba_key,created_at,expires_at) VALUES(?,?,?,?)",
               (_sha(tok), _key(r["ba_code"]), _fmt(now), _fmt(now + timedelta(days=TOKEN_DAYS))))
    return {"token": tok, "sa_id": r["ba_code"], "sa_name": r["name"], "store": r["store_name"] or ""}


class Creds(BaseModel):
    sa_id: str
    password: str


@router.get("/status")
def status(sa_id: str):
    if not _roster(sa_id):
        return {"status": "unknown"}
    has_pw = db.query("SELECT 1 FROM ba_auth WHERE ba_key=?", (_key(sa_id),))
    return {"status": "login" if has_pw else "set_password"}


@router.post("/set-password")
def set_password(c: Creds):
    r = _roster(c.sa_id)
    if not r:
        raise HTTPException(404, "Mã BA này chưa được cấp. Hãy liên hệ quản lý.")
    if len(c.password) < MIN_PW or c.password.strip().lower() == _key(r["ba_code"]):
        raise HTTPException(400, f"Mật khẩu cần ít nhất {MIN_PW} ký tự và không được trùng mã BA.")
    salt = secrets.token_bytes(16)
    try:   # khoá chính ba_key: hai máy đặt cùng lúc thì đúng một máy thắng (kể cả khi chạy nhiều worker)
        db.execute("INSERT INTO ba_auth(ba_key,pw_hash,pw_salt,fails,locked_until,updated_at) VALUES(?,?,?,0,'',?)",
                   (_key(r["ba_code"]), _scrypt(c.password, salt), salt.hex(), db.now_str()))
    except Exception:
        if db.query("SELECT 1 FROM ba_auth WHERE ba_key=?", (_key(r["ba_code"]),)):
            raise HTTPException(409, "Mã BA này đã có mật khẩu. Hãy đăng nhập, hoặc nhờ quản lý đặt lại.")
        raise
    return _issue(r)


@router.post("/login")
def login(c: Creds):
    bad = HTTPException(401, "Sai mã BA hoặc mật khẩu.")   # cùng một thông báo cho "không có mã" và "sai mật khẩu"
    r = _roster(c.sa_id)
    rows = db.query("SELECT * FROM ba_auth WHERE ba_key=?", (_key(c.sa_id),)) if r else []
    if not rows:
        raise bad
    a = rows[0]
    if a["locked_until"] and a["locked_until"] > db.now_str():
        raise HTTPException(429, "Nhập sai nhiều lần. Hãy thử lại sau ít phút.")
    if not hmac.compare_digest(_scrypt(c.password, bytes.fromhex(a["pw_salt"])), a["pw_hash"]):
        fails = a["fails"] + 1
        lock = fails >= MAX_FAILS
        db.execute("UPDATE ba_auth SET fails=?, locked_until=? WHERE ba_key=?",
                   (0 if lock else fails,
                    _fmt(datetime.now(timezone.utc) + timedelta(minutes=LOCK_MINUTES)) if lock else "", a["ba_key"]))
        raise bad
    if a["fails"]:
        db.execute("UPDATE ba_auth SET fails=0, locked_until='' WHERE ba_key=?", (a["ba_key"],))
    return _issue(r)


def _bearer(request: Request) -> str:
    h = request.headers.get("authorization", "")
    if h.lower().startswith("bearer "):
        return h[7:].strip()
    # ?token= chỉ cho trình phát âm thanh (không gắn được header), không mở cho endpoint khác
    return request.query_params.get("token", "") if request.url.path.endswith("/audio") else ""


def principal(request: Request) -> Principal:
    """Dependency toàn app: xác định người gọi hoặc trả 401. Endpoint cần phân quyền thì khai báo lại Depends(principal)."""
    if request.url.path in PUBLIC_PATHS:
        return Principal("public")
    tok = _bearer(request)
    if tok:
        rows = db.query("SELECT ba_key, expires_at FROM auth_tokens WHERE token_hash=?", (_sha(tok),))
        r = _roster(rows[0]["ba_key"]) if rows and rows[0]["expires_at"] >= db.now_str() else None
        if not r:
            raise HTTPException(401, "invalid or expired token")
        return Principal("ba", r["ba_code"], r["name"], r["store_name"] or "")
    key = os.getenv("API_KEY", "")
    if key:
        got = request.headers.get("x-api-key") or request.query_params.get("key") or ""
        if not hmac.compare_digest(got, key):
            raise HTTPException(401, "invalid api key")
    return Principal("admin")


def admin_only(p: Principal) -> None:
    if p.kind == "ba":
        raise HTTPException(403, "Chức năng này chỉ dành cho quản trị viên")


def owns(p: Principal, sa_id: str | None) -> bool:
    """Admin thấy mọi thứ; BA chỉ thấy dữ liệu có sa_id là mã của mình (không phân biệt hoa thường)."""
    return p.kind != "ba" or (sa_id or "").lower() == p.sa_id.lower()


@router.post("/logout")
def logout(request: Request):
    tok = _bearer(request)
    if not tok:
        raise HTTPException(401, "invalid or expired token")
    db.execute("DELETE FROM auth_tokens WHERE token_hash=?", (_sha(tok),))
    return {"ok": True}


@router.delete("/password/{ba_code}")
def reset_password(ba_code: str, request: Request):
    """Quản lý đặt lại: xoá mật khẩu + mọi token của BA này; lần đăng nhập sau BA tự đặt mật khẩu mới."""
    admin_only(principal(request))
    db.execute("DELETE FROM ba_auth WHERE ba_key=?", (_key(ba_code),))
    db.execute("DELETE FROM auth_tokens WHERE ba_key=?", (_key(ba_code),))
    return {"ok": True}
