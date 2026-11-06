"""Đăng nhập BA + phân quyền. Danh sách BA lấy từ bảng staff (như khi nạp headcount)."""
import os
import tempfile

os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))
os.environ.setdefault("AUDIO_DIR", tempfile.mkdtemp())
import pytest
from fastapi.testclient import TestClient

from app import asr, db
from app.main import app

c = TestClient(app)
PW = "matkhau-cua-lan"


def _staff(ess, ba, name, store="S1", left=None, updated="2026-01-01 00:00:00"):
    db.execute("INSERT INTO staff(ess_code,ba_code,name,store_code,left_at,updated_at) VALUES(?,?,?,?,?,?)",
               (ess, ba, name, store, left, updated))


@pytest.fixture(scope="module", autouse=True)
def roster():
    db.execute("INSERT INTO stores(ess_store_code,name) VALUES('S1','Co.opmart Q1') ON CONFLICT(ess_store_code) DO NOTHING")
    _staff("E1", "BA001", "Lan")
    _staff("E2", "BA002", "Hoa", store="S1")
    _staff("E3", "BA003", "Đã Nghỉ", left="2020-01-01")
    _staff("E4", "BA004", "Cũ", left="2020-01-01", updated="2026-06-01 00:00:00")   # trùng mã BA004: dòng đã nghỉ ...
    _staff("E5", "BA004", "Mới", updated="2025-01-01 00:00:00")                       # ... và dòng đang làm (cũ hơn)
    _staff("E6", None, "Không có mã BA")


def _set(ba, pw=PW):
    return c.post("/api/auth/set-password", json={"sa_id": ba, "password": pw})


def _login(ba, pw=PW):
    return c.post("/api/auth/login", json={"sa_id": ba, "password": pw})


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def _status(ba):
    return c.get("/api/auth/status", params={"sa_id": ba}).json()["status"]


def test_status_roster_rules():
    assert _status("khong-co") == "unknown"
    assert _status("BA003") == "unknown"            # đã nghỉ việc
    assert _status("ba001") == "set_password"       # không phân biệt hoa thường
    assert _set("BA004", "ok-matkhau-1").json()["sa_name"] == "Mới"   # trùng mã: lấy dòng đang làm


def test_set_password_rules_and_login():
    assert _set("zzz").status_code == 404
    assert _set("BA003").status_code == 404
    assert _set("ba001", "ngan").status_code == 400
    assert _set("ba001", "BA001").status_code == 400
    assert _login("ba001").status_code == 401                      # chưa có mật khẩu: không lộ lý do
    r = _set("ba001")
    assert r.status_code == 200
    assert r.json() | {"token": "x"} == {"token": "x", "sa_id": "BA001", "sa_name": "Lan", "store": "Co.opmart Q1"}
    assert _set("BA001", "mat-khau-khac-1").status_code == 409     # đã có mật khẩu: không ai đặt đè được
    assert _status("BA001") == "login"
    assert _login("BA001", "sai-mat-khau").status_code == 401
    ok = _login("Ba001")
    assert ok.status_code == 200 and ok.json()["sa_id"] == "BA001"
    row = db.query("SELECT * FROM ba_auth WHERE ba_key='ba001'")[0]
    assert PW not in str(row)                                       # không lưu mật khẩu thô
    assert not db.query("SELECT 1 FROM auth_tokens WHERE token_hash=?", (ok.json()["token"],))   # không lưu token thô


def test_lockout_after_5_failures():
    _set("BA002", "mat-khau-hoa-1")
    for _ in range(5):
        assert _login("BA002", "sai-roi-nhe").status_code == 401
    assert _login("BA002", "mat-khau-hoa-1").status_code == 429
    db.execute("UPDATE ba_auth SET locked_until='' WHERE ba_key='ba002'")
    assert _login("BA002", "mat-khau-hoa-1").status_code == 200


def _tok(ba, pw):
    return _login(ba, pw).json()["token"]


def _upload(tok, **form):
    return c.post("/api/sessions", headers=_h(tok), files={"audio": ("r.m4a", b"voice", "audio/m4a")}, data=form)


def test_ba_scoping(monkeypatch):
    monkeypatch.setattr(asr, "transcribe", lambda p, h="": {
        "text": "Dạ em xin cảm ơn chị, vậy mình chốt 2 omo bột giặt đỏ 9kg 65 nghìn. Dạ ok em.",
        "segments": [], "duration": 5.0})
    lan, hoa = _tok("BA001", PW), _tok("BA002", "mat-khau-hoa-1")
    # giả mạo sa_id/sa_name trong form: server bỏ qua, dùng danh tính trong token
    sid = _upload(lan, sa_id="BA002", sa_name="Hacker", store="Cửa hàng riêng").json()["id"]
    s = db.query("SELECT sa_id, sa_name, store FROM sessions WHERE id=?", (sid,))[0]
    assert (s["sa_id"], s["sa_name"], s["store"]) == ("BA001", "Lan", "Cửa hàng riêng")
    sid_h = _upload(hoa).json()["id"]
    assert db.query("SELECT store FROM sessions WHERE id=?", (sid_h,))[0]["store"] == "Co.opmart Q1"   # mặc định theo headcount

    assert [x["id"] for x in c.get("/api/sessions?sa_id=BA002", headers=_h(lan)).json()] == [sid]   # sa_id client gửi bị bỏ qua
    assert c.get(f"/api/sessions/{sid}", headers=_h(lan)).status_code == 200
    assert c.get(f"/api/sessions/{sid}/audio", headers=_h(lan)).content == b"voice"
    oid = c.get(f"/api/sessions/{sid}", headers=_h(lan)).json()["orders"][0]["id"]
    fix = [{"sku_id": "omo-bg-do-9kg", "qty": 3, "price": 65000}]
    # BA khác: không đọc, không nghe, không sửa, không thêm đơn
    assert c.get(f"/api/sessions/{sid}", headers=_h(hoa)).status_code == 404
    assert c.get(f"/api/sessions/{sid}/audio", headers=_h(hoa)).status_code == 404
    assert c.put(f"/api/orders/{oid}/items", json=fix, headers=_h(hoa)).status_code == 404
    assert c.post(f"/api/sessions/{sid}/orders", json=fix, headers=_h(hoa)).status_code == 404
    assert c.put(f"/api/orders/{oid}/items", json=fix, headers=_h(lan)).status_code == 200
    assert c.post(f"/api/sessions/{sid}/orders", json=fix, headers=_h(lan)).status_code == 200
    # công cụ dev + thống kê toàn hệ thống: chỉ admin
    assert c.get("/api/stats/overview", headers=_h(lan)).status_code == 403
    assert c.post("/api/sessions/text", json={"transcript": "x"}, headers=_h(lan)).status_code == 403
    assert c.post("/api/parse-text", json={"transcript": "x"}, headers=_h(lan)).status_code == 403
    assert c.get("/api/catalog", headers=_h(lan)).status_code == 200
    # chế độ không đặt API_KEY (chạy thử): request không token vẫn là admin, thấy mọi phiên
    assert {sid, sid_h} <= {x["id"] for x in c.get("/api/sessions").json()}


def test_voiceprint_only_own():
    lan = _tok("BA001", PW)
    assert c.get("/api/voiceprints/BA001", headers=_h(lan)).json()["enrolled"] is False
    assert c.get("/api/voiceprints/ba001", headers=_h(lan)).status_code == 200       # hoa thường không quan trọng
    assert c.get("/api/voiceprints/BA002", headers=_h(lan)).status_code == 403
    assert c.delete("/api/voiceprints/BA002", headers=_h(lan)).status_code == 403
    assert c.post("/api/voiceprints/BA002", headers=_h(lan), data={"consent": "true"},
                  files={"audio": ("a.m4a", b"x", "audio/m4a")}).status_code == 403


def test_with_api_key_enabled(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret")
    lan = _tok("BA001", PW)
    sid = db.query("SELECT id FROM sessions WHERE sa_id='BA001' LIMIT 1")[0]["id"]
    assert _status("BA001") == "login"                                              # đăng nhập không cần API key
    assert c.get("/api/sessions").status_code == 401                                # không thông tin xác thực
    assert c.get("/api/sessions", headers={"Authorization": "Bearer sai"}).status_code == 401
    assert c.get("/api/sessions", headers=_h(lan)).status_code == 200               # token BA đủ, không cần API key
    assert len(c.get("/api/sessions", headers={"x-api-key": "secret"}).json()) > len(c.get("/api/sessions", headers=_h(lan)).json())
    assert c.get("/api/stats/overview", headers={"x-api-key": "secret"}).status_code == 200   # web Coach không đổi
    assert c.get("/api/sessions", params={"token": lan}).status_code == 401         # ?token= chỉ dùng cho /audio
    assert c.get(f"/api/sessions/{sid}/audio", params={"token": lan}).status_code == 200


def test_logout_expiry_and_admin_reset(monkeypatch):
    t = _tok("BA001", PW)
    assert c.post("/api/auth/logout", headers=_h(t)).status_code == 200
    assert c.get("/api/sessions", headers=_h(t)).status_code == 401
    t2 = _tok("BA001", PW)
    db.execute("UPDATE auth_tokens SET expires_at='2000-01-01 00:00:00'")
    assert c.get("/api/sessions", headers=_h(t2)).status_code == 401
    t3 = _tok("BA001", PW)
    assert c.delete("/api/auth/password/BA001", headers=_h(t3)).status_code == 403   # BA không tự reset
    assert c.delete("/api/auth/password/BA001").status_code == 200                   # admin reset
    assert c.get("/api/sessions", headers=_h(t3)).status_code == 401                 # token cũ bị thu hồi
    assert _status("BA001") == "set_password"
    assert _set("BA001", "mat-khau-moi-1").status_code == 200
