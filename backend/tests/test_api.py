from fastapi.testclient import TestClient
import os, tempfile
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["AUDIO_DIR"] = tempfile.mkdtemp()
from app.main import app

c = TestClient(app)


def test_flow():
    r = c.post("/api/sessions/text", json={
        "transcript": "Dạ em xin cảm ơn chị, vậy mình chốt 2 omo 800g, 1 clear men 650ml. Dạ ok em.",
        "sa_name": "Lan"})
    sid = r.json()["id"]
    s = c.get(f"/api/sessions/{sid}").json()
    assert len(s["orders"]) == 1 and s["orders"][0]["customer_confirm"] == "yes"
    top = c.get("/api/stats/top-skus").json()
    assert top["top"][0]["sku_id"] == "OMO-BOT-800G" and top["top"][0]["qty"] == 2
    oid = s["orders"][0]["id"]
    f = c.put(f"/api/orders/{oid}/items", json=[{"sku_id": "OMO-BOT-3KG", "qty": 4}]).json()
    assert f["items"][0]["qty"] == 4


def test_overview_and_coaching():
    c.post("/api/sessions/text", json={
        "transcript": "Xin chào chị, chị đang dùng loại nào ạ? Bên em có khuyến mãi tặng kèm, chị lấy thêm một chai nhé. "
                      "Dạ em xin cảm ơn chị, vậy mình chốt 1 dove 640ml. Thôi để chị suy nghĩ.",
        "sa_id": "sa02", "sa_name": "Hoa"})
    o = c.get("/api/stats/overview?days=1").json()
    assert o["kpi"]["orders"] >= 2 and o["kpi"]["declined"] >= 1
    assert any(x["sa_id"] == "sa02" for x in o["by_sa"])
    sid = c.get("/api/sessions?sa_id=sa02").json()[0]["id"]
    co = c.get(f"/api/sessions/{sid}").json()["coaching"]
    assert co["score"] == 100 and "think" in co["objections"]


def test_auth(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret")
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/catalog").status_code == 401
    assert c.get("/api/catalog", headers={"x-api-key": "secret"}).status_code == 200


def test_upload_audio_flow(monkeypatch):
    """Upload audio -> ASR (giả lập) -> parser -> lưu DB -> tải lại audio."""
    from app import asr
    monkeypatch.setattr(asr, "transcribe", lambda path, hot="": {
        "text": "Dạ em xin cảm ơn chị, vậy mình chốt 2 omo 800g. Dạ ok em.",
        "segments": [{"start": 0.0, "end": 4.0, "text": "Dạ em xin cảm ơn chị, vậy mình chốt 2 omo 800g."},
                     {"start": 4.0, "end": 5.0, "text": "Dạ ok em."}],
        "duration": 5.0})
    r = c.post("/api/sessions", files={"audio": ("rec.m4a", b"fakeaudio", "audio/m4a")},
               data={"sa_id": "sa09", "sa_name": "Test", "store": "S1"})
    assert r.status_code == 200
    sid = r.json()["id"]
    s = c.get(f"/api/sessions/{sid}").json()   # background task đã chạy xong
    assert s["status"] == "done" and s["duration"] == 5.0 and s["has_audio"]
    assert s["orders"][0]["items"][0]["sku_id"] == "OMO-BOT-800G"
    assert len(s["segments"]) == 2
    assert c.get(f"/api/sessions/{sid}/audio").content == b"fakeaudio"


def test_upload_asr_error_is_recorded(monkeypatch):
    from app import asr
    def boom(*a, **k): raise RuntimeError("model missing")
    monkeypatch.setattr(asr, "transcribe", boom)
    sid = c.post("/api/sessions", files={"audio": ("r.m4a", b"x", "audio/m4a")}).json()["id"]
    s = c.get(f"/api/sessions/{sid}").json()
    assert s["status"] == "error" and "model missing" in s["error"]
