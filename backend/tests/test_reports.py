"""Barcode trong DB + báo cáo bán hàng SA (JSON xem trước và file Excel)."""
import csv
import io
from datetime import datetime
import json
import os
import sqlite3
import tempfile

os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))
os.environ.setdefault("AUDIO_DIR", tempfile.mkdtemp())
import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app, catalog
from app.parser import Catalog

c = TestClient(app)
OMO, CLEAR, SUNSILK = "omo-bg-do-9kg", "clear-men-dau-goi-nuoc-hoa-warm-forest-350g", "sunsilk-dau-goi-mem-muot-dieu-ky-170g"
RANGE = {"from": "2026-03-10", "to": "2026-03-11"}


def _items(*rows):
    return json.dumps([{"sku_id": s, "sku_name": catalog.skus[s]["name"], "qty": q, "price": p, "conf": 1.0, "need_confirm": False,
                        **({"manual": True} if m else {})} for s, q, p, m in rows], ensure_ascii=False)


def _order(sid, created, confirm, items, reviewed=0):
    db.execute("INSERT INTO orders(session_id,closing_text,customer_confirm,items_json,needs_review,reviewed,created_at) VALUES(?,?,?,?,0,?,?)",
               (sid, "x", confirm, items, reviewed, created))


@pytest.fixture(scope="module", autouse=True)
def data():
    for sid, sa, name, store in (("rp1", "RPT01", "An", "=1+1"), ("rp2", "RPT02", "Bình", "Cửa hàng B")):
        db.execute("INSERT INTO sessions(id,sa_id,sa_name,store,status,created_at) VALUES(?,?,?,?,'done','2026-03-10 00:00:00')", (sid, sa, name, store))
    # giờ lưu UTC, ngày báo cáo theo giờ VN (UTC+7)
    _order("rp1", "2026-03-10 02:00:00", "yes", _items((OMO, 2, 65000, 0), (CLEAR, 1, None, 0)))     # 10/03 09:00, có 1 dòng thiếu giá
    _order("rp1", "2026-03-10 17:30:00", "none", _items((OMO, 1, 70000, 0)))                          # 11/03 00:30 (sang ngày mới theo giờ VN)
    _order("rp1", "2026-03-09 16:59:00", "yes", _items((OMO, 9, 65000, 0)))                           # 09/03 23:59 giờ VN: NGOÀI khoảng
    _order("rp2", "2026-03-10 05:00:00", "no", _items((OMO, 5, 65000, 0)))                            # khách từ chối
    _order("rp2", "2026-03-11 05:00:00", "yes", _items((SUNSILK, 3, 40000, 1)), reviewed=1)
    db.execute("INSERT INTO stores(ess_store_code,name) VALUES('ST001','=1+1'),('ST002','Cửa hàng B')")
    db.execute("INSERT INTO staff(ess_code,ba_code,name,store_code,updated_at) VALUES('ERPT1','RPT01','An','ST001','2026-01-01 00:00:00')")


def _sales(**kw):
    return c.get("/api/reports/sales", params={**RANGE, **kw})


def test_catalog_va_db_co_barcode():
    row = db.query("SELECT barcode FROM skus WHERE sku_id=?", (OMO,))[0]
    assert row["barcode"] == catalog.skus[OMO]["barcode"] == "8934868136576"
    assert all(s["barcode"] for s in catalog.skus.values())                       # đủ 96/96
    assert c.get("/api/catalog").json()[0]["barcode"]                             # app / web cũng nhận được barcode


def test_catalog_barcode_trung_bi_chan(tmp_path):
    f = tmp_path / "c.csv"
    f.write_text("name,aliases,sku_id,barcode\nA 100g,,a,111\nB 100g,,b,111\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Trùng barcode"):
        Catalog(str(f))


def test_migration_db_cu_chua_co_cot_barcode(monkeypatch, tmp_path):
    path = str(tmp_path / "old.db")
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE skus(sku_id TEXT PRIMARY KEY, name TEXT NOT NULL, unit TEXT, brand TEXT, aliases TEXT, active INTEGER DEFAULT 1)")
    con.execute("INSERT INTO skus(sku_id,name) VALUES('x','Cũ')"); con.commit(); con.close()
    monkeypatch.setattr(db, "DB_PATH", path)
    db.init(); db.init()                                                          # chạy 2 lần vẫn an toàn
    db.sync_skus(catalog.skus, catalog.rows[:1])
    cols = [r["name"] for r in db.query("PRAGMA table_info(skus)")]
    assert "barcode" in cols
    assert db.query("SELECT name FROM skus WHERE sku_id='x'")[0]["name"] == "Cũ"   # dữ liệu cũ còn nguyên
    assert db.query("SELECT barcode FROM skus WHERE barcode IS NOT NULL")[0]["barcode"]


def test_tong_hop_va_moc_ngay_gio_viet_nam():
    r = _sales().json()
    # tính: A1 (2 dòng) + A2 + B2 ; loại đơn 09/03 23:59 giờ VN và đơn khách từ chối
    assert r["kpi"] == {"sessions": 2, "orders": 3, "units": 7, "revenue": 320000, "skus": 3, "missing_price": 1}
    assert r["line_count"] == 4
    an, binh = r["by_sa"][0], r["by_sa"][1]                                       # sắp theo doanh thu giảm dần
    assert (an["sa_id"], an["orders"], an["units"], an["revenue"], an["skus"], an["missing_price"]) == ("RPT01", 2, 4, 200000, 2, 1)
    assert (binh["sa_id"], binh["revenue"]) == ("RPT02", 120000)
    omo = [k for k in r["by_sku"] if k["sku_id"] == OMO][0]
    assert (omo["qty"], omo["orders"], omo["revenue"], omo["avg_price"], omo["barcode"]) == (3, 2, 200000, 66667, "8934868136576")


def test_gom_ca_don_khach_tu_choi():
    r = _sales(include_declined=True).json()
    assert r["kpi"]["orders"] == 4 and r["kpi"]["units"] == 12 and r["kpi"]["revenue"] == 645000


def test_loc_theo_sa_va_ngay():
    r = _sales(sa_id="rpt02").json()                                              # không phân biệt hoa thường
    assert [a["sa_id"] for a in r["by_sa"]] == ["RPT02"] and r["kpi"]["revenue"] == 120000
    assert _sales(**{"from": "2026-03-11", "to": "2026-03-11"}).json()["kpi"]["orders"] == 2   # A2 (00:30 giờ VN) + B2
    assert c.get("/api/reports/sales", params={"from": "2030-01-01", "to": "2030-01-02"}).json()["kpi"]["orders"] == 0


def test_ngay_khong_hop_le():
    assert c.get("/api/reports/sales", params={"from": "abc"}).status_code == 400
    assert c.get("/api/reports/sales", params={"from": "2026-03-11", "to": "2026-03-10"}).status_code == 400
    assert c.get("/api/reports/sales", params={"from": "2024-01-01", "to": "2026-03-10"}).status_code == 400   # > 366 ngày


def test_file_excel():
    openpyxl = pytest.importorskip("openpyxl")   # CI không cài openpyxl thì bỏ qua đúng test này; nên thêm openpyxl vào bước cài của CI
    r = c.get("/api/reports/sales.xlsx", params={**RANGE, "sa_id": "RPT01"})
    assert r.status_code == 200 and "spreadsheetml" in r.headers["content-type"]
    assert r.headers["content-disposition"] == 'attachment; filename="report_2026-03-10_2026-03-11_RPT01.xlsx"'
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Chi tiết", "Tổng hợp theo SA", "Theo SKU"]
    ws = wb["Chi tiết"]
    assert [c.value for c in ws[1]][:6] == ["Timestamp", "Mã cửa hàng (Store code)", "Tên cửa hàng", "Tên nhân viên", "Mã nhân viên (BA code)", "Mã đơn hàng"]
    det = list(ws.iter_rows(min_row=2, values_only=True))
    assert len(det) == 3                                                           # A1 (2 dòng) + A2 (1 dòng)
    first = det[0]
    assert first[0] == datetime(2026, 3, 10, 9, 0, 0)                              # timestamp thật, giờ VN (UTC+7)
    assert ws.cell(row=2, column=1).number_format == "dd/mm/yyyy hh:mm:ss"
    assert first[1] == "ST001" and first[2] == "=1+1" and first[3] == "An" and first[4] == "RPT01"
    assert first[7] == "8934868136576" and first[10:13] == (2, 65000, 130000)      # barcode, số lượng, đơn giá, thành tiền
    assert det[1][11] is None and det[1][12] is None                               # dòng thiếu giá: để trống, không bịa 0
    assert ws.cell(row=2, column=8).number_format == "@"                           # barcode là chữ, không thành 8.93E+12
    assert ws.cell(row=2, column=3).data_type == "s"                               # chống công thức độc hại qua tên cửa hàng
    assert det[2][0] == datetime(2026, 3, 11, 0, 30, 0)                            # đơn 17:30 UTC -> 00:30 hôm sau giờ VN
    tot = list(wb["Tổng hợp theo SA"].iter_rows(min_row=8, values_only=True))
    assert tot[0][:2] == ("RPT01", "An") and tot[-1][0] == "Tổng cộng" and tot[-1][6] == 200000
    sku = {row[1]: row for row in wb["Theo SKU"].iter_rows(min_row=2, values_only=True)}
    assert sku[OMO][0] == "8934868136576" and sku[OMO][3] == 3


def _token():
    c.post("/api/auth/set-password", json={"sa_id": "RPT01", "password": "mat-khau-an-1"})
    return c.post("/api/auth/login", json={"sa_id": "RPT01", "password": "mat-khau-an-1"}).json()["token"]


def test_phan_quyen(monkeypatch):
    h = {"Authorization": f"Bearer {_token()}"}
    r = c.get("/api/reports/sales", params={**RANGE, "sa_id": "RPT02", "include_declined": "true"}, headers=h).json()
    assert [a["sa_id"] for a in r["by_sa"]] == ["RPT01"]                           # BA xin sa_id người khác: vẫn chỉ thấy của mình
    assert c.get("/api/reports/sas", headers=h).status_code == 403                 # danh sách mọi SA: chỉ admin
    assert {"RPT01", "RPT02"} <= {s["sa_id"] for s in c.get("/api/reports/sas").json()}
    monkeypatch.setenv("API_KEY", "secret")
    assert c.get("/api/reports/sales", params=RANGE).status_code == 401
    assert c.get("/api/reports/sales", params=RANGE, headers={"x-api-key": "secret"}).status_code == 200
    assert c.get("/api/reports/sales.xlsx", params=RANGE).status_code == 401      # chưa tới bước tạo file: bị chặn trước


def test_phan_quyen_file_excel():
    pytest.importorskip("openpyxl")
    h = {"Authorization": f"Bearer {_token()}"}
    x = c.get("/api/reports/sales.xlsx", params={**RANGE, "sa_id": "RPT02"}, headers=h)    # BA xin file của SA khác
    assert x.status_code == 200 and "RPT01" in x.headers["content-disposition"] and "RPT02" not in x.headers["content-disposition"]
