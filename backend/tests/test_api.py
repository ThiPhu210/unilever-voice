from fastapi.testclient import TestClient
import os, tempfile
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["AUDIO_DIR"] = tempfile.mkdtemp()
from app.main import app

c = TestClient(app)

# SKU còn trong sku_catalog.csv (sku_id trống trong CSV -> parser tự sinh slug từ tên)
OMO = "omo-bg-do-9kg"                                            # OMO BG đỏ 9kg
CLEAR_MEN = "clear-men-dau-goi-nuoc-hoa-warm-forest-350g"        # CLEAR MEN Dầu Gội Nước Hoa Warm Forest 350G
SUNSILK = "sunsilk-dau-goi-mem-muot-dieu-ky-170g"                # SUNSILK Dầu Gội Mềm Mượt Diệu Kỳ 170G
HAZELINE_900G = "HAZELINE-SUATAM-GAO-900G"                       # sku_id khai báo sẵn trong CSV


def test_flow():
    r = c.post("/api/sessions/text", json={
        "transcript": "Dạ em xin cảm ơn chị, vậy mình chốt 2 omo bột giặt đỏ 9kg 65 nghìn, "
                      "1 clear men nước hoa warm forest 350g 120 nghìn. Dạ ok em.",
        "sa_name": "Lan"})
    sid = r.json()["id"]
    s = c.get(f"/api/sessions/{sid}").json()
    assert len(s["orders"]) == 1 and s["orders"][0]["customer_confirm"] == "yes"
    top = c.get("/api/stats/top-skus").json()
    assert top["top"][0]["sku_id"] == OMO and top["top"][0]["qty"] == 2
    oid = s["orders"][0]["id"]
    f = c.put(f"/api/orders/{oid}/items", json=[{"sku_id": HAZELINE_900G, "qty": 4}]).json()
    assert f["items"][0]["qty"] == 4


def test_overview_and_coaching():
    c.post("/api/sessions/text", json={
        "transcript": "Xin chào chị, chị đang dùng loại nào ạ? Bên em có khuyến mãi tặng kèm, chị lấy thêm một chai nhé. "
                      "Dạ em xin cảm ơn chị, vậy mình chốt 1 sunsilk mềm mượt diệu kỳ 170g 65 nghìn. Thôi để chị suy nghĩ.",
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
        "text": "Dạ em xin cảm ơn chị, vậy mình chốt 2 omo bột giặt đỏ 9kg 65 nghìn. Dạ ok em.",
        "segments": [{"start": 0.0, "end": 4.0, "text": "Dạ em xin cảm ơn chị, vậy mình chốt 2 omo bột giặt đỏ 9kg 65 nghìn."},
                     {"start": 4.0, "end": 5.0, "text": "Dạ ok em."}],
        "duration": 5.0})
    r = c.post("/api/sessions", files={"audio": ("rec.m4a", b"fakeaudio", "audio/m4a")},
               data={"sa_id": "sa09", "sa_name": "Test", "store": "S1"})
    assert r.status_code == 200
    sid = r.json()["id"]
    s = c.get(f"/api/sessions/{sid}").json()   # background task đã chạy xong
    assert s["status"] == "done" and s["duration"] == 5.0 and s["has_audio"]
    assert s["orders"][0]["items"][0]["sku_id"] == OMO
    assert len(s["segments"]) == 2
    assert c.get(f"/api/sessions/{sid}/audio").content == b"fakeaudio"


def test_upload_asr_error_is_recorded(monkeypatch):
    from app import asr
    def boom(*a, **k): raise RuntimeError("model missing")
    monkeypatch.setattr(asr, "transcribe", boom)
    sid = c.post("/api/sessions", files={"audio": ("r.m4a", b"x", "audio/m4a")}).json()["id"]
    s = c.get(f"/api/sessions/{sid}").json()
    assert s["status"] == "error" and "model missing" in s["error"]


def test_gia_va_sua_gia_va_doanh_thu():
    # dòng clear không đọc giá -> parser bỏ; đơn chỉ có omo (đủ số lượng + giá)
    r = c.post("/api/sessions/text", json={
        "transcript": "Dạ em xin cảm ơn anh chị, vậy mình chốt 2 omo bột giặt đỏ 9kg 65 nghìn đồng, "
                      "1 clear men nước hoa warm forest 350g. Dạ ok em.",
        "sa_id": "sa09", "sa_name": "Giá"})
    sid = r.json()["id"]
    s = c.get(f"/api/sessions/{sid}").json()
    o = s["orders"][0]
    assert [i["sku_id"] for i in o["items"]] == [OMO]
    assert o["missing_price"] == 0 and o["total"] == 130000
    row = [x for x in c.get("/api/sessions?sa_id=sa09").json() if x["id"] == sid][0]
    assert row["missing_price"] == 0 and row["revenue"] == 130000
    # SA bổ sung dòng bị bỏ sót + thêm 1 SKU
    items = [{"sku_id": OMO, "qty": 2, "price": 65000},
             {"sku_id": CLEAR_MEN, "qty": 1, "price": 120000},
             {"sku_id": SUNSILK, "qty": 1, "price": 99000}]
    f = c.put(f"/api/orders/{o['id']}/items", json=items).json()
    assert [i["price"] for i in f["items"]] == [65000, 120000, 99000]
    o2 = c.get(f"/api/sessions/{sid}").json()["orders"][0]
    assert o2["missing_price"] == 0 and o2["total"] == 349000 and o2["reviewed"] == 1
    ov = c.get("/api/stats/overview?days=1").json()
    assert ov["kpi"]["revenue"] >= 349000
    sk = c.get("/api/stats/skus?days=3").json()
    omo = [x for x in sk["skus"] if x["sku_id"] == OMO][0]
    assert omo["revenue"] >= 130000 and omo["avg_price"] == 65000 and len(omo["by_day"]) == 3


def test_sua_gia_khong_hop_le():
    r = c.post("/api/sessions/text", json={"transcript": "vậy mình chốt 1 omo bột giặt đỏ 9kg 65 nghìn.", "sa_id": "sa10"})
    oid = c.get(f"/api/sessions/{r.json()['id']}").json()["orders"][0]["id"]
    assert c.put(f"/api/orders/{oid}/items", json=[{"sku_id": OMO, "qty": 1, "price": -5}]).status_code == 400
    assert c.put(f"/api/orders/{oid}/items", json=[]).status_code == 400
    assert c.put("/api/orders/999999/items", json=[{"sku_id": OMO, "qty": 1}]).status_code == 404


def test_sa_them_don_thu_cong():
    sid = c.post("/api/sessions/text", json={"transcript": "Chào chị ạ, chị cần gì ạ?", "sa_id": "sa11"}).json()["id"]
    assert c.get(f"/api/sessions/{sid}").json()["orders"] == []
    r = c.post(f"/api/sessions/{sid}/orders", json=[{"sku_id": OMO, "qty": 2, "price": 65000}])
    assert r.status_code == 200
    o = c.get(f"/api/sessions/{sid}").json()["orders"][0]
    assert o["total"] == 130000 and o["reviewed"] == 1 and o["customer_confirm"] == "yes"
    assert c.post("/api/sessions/nope/orders", json=[{"sku_id": OMO, "qty": 1}]).status_code == 404
