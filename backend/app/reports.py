"""Báo cáo bán hàng của SA/BA: tổng hợp theo SA, theo SKU (kèm barcode) và chi tiết từng dòng hàng; xuất Excel.

Cách tính khớp với trang Sản phẩm / Tổng quan trên web (app/stats.py): mặc định KHÔNG tính đơn khách từ chối,
dòng chưa có giá không tính vào doanh thu. Ngày lọc theo giờ Việt Nam (TZ_OFFSET_HOURS), tính cả ngày đầu và ngày cuối.
Admin (API_KEY) xem được mọi SA; BA đăng nhập bằng token chỉ xuất được báo cáo của chính mình.
"""
import io
import json
import re
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from . import db
from .auth import Principal, admin_only, principal
from .stats import TZ_HOURS

router = APIRouter(prefix="/api/reports")
MAX_DAYS = 366
REPLY = {"yes": "Khách đồng ý", "no": "Khách từ chối", "none": "Khách im lặng"}
_FMT = "%Y-%m-%d %H:%M:%S"


def _range(frm: str | None, to: str | None):
    today = (datetime.now(timezone.utc) + timedelta(hours=TZ_HOURS)).date()
    try:
        d1 = date.fromisoformat(frm) if frm else today - timedelta(days=6)
        d2 = date.fromisoformat(to) if to else today
    except ValueError:
        raise HTTPException(400, "Ngày phải có dạng YYYY-MM-DD")
    if d2 < d1:
        raise HTTPException(400, "Ngày kết thúc phải sau hoặc bằng ngày bắt đầu")
    if (d2 - d1).days + 1 > MAX_DAYS:
        raise HTTPException(400, f"Chỉ xuất tối đa {MAX_DAYS} ngày mỗi lần")
    shift = timedelta(hours=TZ_HOURS)   # created_at lưu UTC: đổi mốc 00:00 giờ VN về UTC
    return d1, d2, (datetime.combine(d1, time.min) - shift).strftime(_FMT), (datetime.combine(d2 + timedelta(days=1), time.min) - shift).strftime(_FMT)


def _status(it: dict, o: dict) -> str:
    if it.get("manual") or o["reviewed"]:
        return "SA/BA đã xác nhận"
    return "Chờ SA xác nhận" if (o["needs_review"] or it.get("need_confirm")) else "Tự động"


def build(p: Principal, frm: str | None, to: str | None, sa_id: str | None, include_declined: bool) -> dict:
    d1, d2, start, end = _range(frm, to)
    if p.kind == "ba":
        sa_id = p.sa_id   # BA chỉ xuất báo cáo của mình, bỏ qua sa_id client gửi
    where, args = ["o.created_at>=?", "o.created_at<?"], [start, end]
    if sa_id:
        where.append("lower(s.sa_id)=?"); args.append(sa_id.strip().lower())
    if not include_declined:
        where.append("COALESCE(o.customer_confirm,'none')<>'no'")
    rows = db.query(
        "SELECT o.id AS order_id, o.session_id, o.customer_confirm, o.items_json, o.needs_review, o.reviewed, "
        "o.created_at, s.sa_id, s.sa_name, s.store FROM orders o JOIN sessions s ON s.id=o.session_id "
        f"WHERE {' AND '.join(where)} ORDER BY o.created_at, o.id", args)
    barcode = {r["sku_id"]: r["barcode"] or "" for r in db.query("SELECT sku_id, barcode FROM skus")}
    lines, by_sa, by_sku = [], {}, {}
    for o in rows:
        local = datetime.strptime(o["created_at"], _FMT) + timedelta(hours=TZ_HOURS)
        sa = by_sa.setdefault((o["sa_id"] or "").lower(), {
            "sa_id": o["sa_id"], "sa_name": o["sa_name"], "sessions": set(), "orders": 0, "units": 0,
            "revenue": 0, "missing_price": 0, "skus": set()})
        sa["sessions"].add(o["session_id"]); sa["orders"] += 1
        for it in json.loads(o["items_json"]):
            price = it.get("price")
            amount = it["qty"] * price if price is not None else None
            lines.append({
                "date": local.date().isoformat(), "time": local.strftime("%H:%M"), "sa_id": o["sa_id"], "sa_name": o["sa_name"],
                "store": o["store"] or "", "session_id": o["session_id"], "order_id": o["order_id"],
                "reply": REPLY.get(o["customer_confirm"], o["customer_confirm"] or ""), "barcode": barcode.get(it["sku_id"], ""),
                "sku_id": it["sku_id"], "sku_name": it["sku_name"], "qty": it["qty"], "price": price, "amount": amount,
                "status": _status(it, o)})
            sa["units"] += it["qty"]; sa["skus"].add(it["sku_id"])
            k = by_sku.setdefault(it["sku_id"], {"sku_id": it["sku_id"], "name": it["sku_name"], "barcode": barcode.get(it["sku_id"], ""),
                                                 "qty": 0, "orders": 0, "revenue": 0, "priced_qty": 0, "sas": set()})
            k["qty"] += it["qty"]; k["orders"] += 1; k["sas"].add((o["sa_id"] or "").lower())
            if amount is None:
                sa["missing_price"] += 1
            else:
                sa["revenue"] += amount; k["revenue"] += amount; k["priced_qty"] += it["qty"]
    sa_rows = sorted(({**a, "sessions": len(a["sessions"]), "skus": len(a["skus"])} for a in by_sa.values()), key=lambda a: -a["revenue"])
    sku_rows = sorted(({**k, "sas": len(k["sas"]), "avg_price": round(k["revenue"] / k["priced_qty"]) if k["priced_qty"] else None,
                        } for k in by_sku.values()), key=lambda k: -k["qty"])
    for k in sku_rows:
        del k["priced_qty"]
    return {
        "from": d1.isoformat(), "to": d2.isoformat(), "sa_id": sa_id or "", "include_declined": include_declined,
        "kpi": {"sessions": sum(a["sessions"] for a in sa_rows), "orders": len(rows), "units": sum(a["units"] for a in sa_rows),
                "revenue": sum(a["revenue"] for a in sa_rows), "skus": len(sku_rows), "missing_price": sum(a["missing_price"] for a in sa_rows)},
        "by_sa": sa_rows, "by_sku": sku_rows, "lines": lines,
    }


# ---------- Excel ----------
def _xl():
    """openpyxl chỉ nạp khi thật sự xuất file: API (xem trước, đăng nhập, ...) khởi động được cả khi môi trường không cài openpyxl."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    return Workbook, Alignment, Font, PatternFill, get_column_letter


def _table(ws, row: int, headers: list[str], data: list[list], money: set[int] = frozenset(), text: set[int] = frozenset(), widths: list[int] | None = None):
    _, Alignment, Font, PatternFill, get_column_letter = _xl()
    head, fill = Font(bold=True, color="3A2316"), PatternFill("solid", fgColor="FFF1DD")
    for j, h in enumerate(headers, 1):
        c = ws.cell(row=row, column=j, value=h)
        c.font, c.fill, c.alignment = head, fill, Alignment(wrap_text=True, vertical="center")
    for i, vals in enumerate(data, row + 1):
        for j, v in enumerate(vals, 1):
            c = ws.cell(row=i, column=j, value=v)
            if isinstance(v, str):
                c.data_type = "s"   # chuỗi nào cũng là CHỮ: tên cửa hàng / SA bắt đầu bằng "=" không bị Excel hiểu là công thức
            if j in money:
                c.number_format = "#,##0"
            if j in text:
                c.number_format = "@"   # barcode giữ nguyên dạng chữ, không thành số khoa học 8.93E+12
    for j, w in enumerate(widths or [], 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = ws.cell(row=row + 1, column=1)
    if data:
        ws.auto_filter.ref = f"A{row}:{get_column_letter(len(headers))}{row + len(data)}"


def to_xlsx(rep: dict) -> bytes:
    Workbook, _, Font, _, _ = _xl()
    wb = Workbook()
    ws = wb.active
    ws.title = "Tổng hợp theo SA"
    d1, d2 = date.fromisoformat(rep["from"]), date.fromisoformat(rep["to"])
    ws["A1"] = "Báo cáo bán hàng SA/BA"; ws["A1"].font = Font(bold=True, size=14, color="3A2316")
    ws["A2"] = f"Từ {d1:%d/%m/%Y} đến {d2:%d/%m/%Y} (giờ Việt Nam)"
    ws["A3"] = f"SA/BA: {rep['sa_id'] or 'tất cả'}"
    ws["A4"] = "Gồm cả đơn khách từ chối" if rep["include_declined"] else "Không tính đơn khách từ chối"
    ws["A5"] = "Dòng chưa có giá không tính vào doanh thu"
    for r in (3,):
        ws.cell(row=r, column=1).data_type = "s"
    k = rep["kpi"]
    sa = [[a["sa_id"], a["sa_name"], a["sessions"], a["orders"], a["units"], a["skus"], a["revenue"], a["missing_price"]] for a in rep["by_sa"]]
    sa.append(["Tổng cộng", "", k["sessions"], k["orders"], k["units"], k["skus"], k["revenue"], k["missing_price"]])
    _table(ws, 7, ["Mã SA/BA", "Tên SA/BA", "Số cuộc tư vấn", "Số đơn", "Số sản phẩm", "Số SKU khác nhau", "Doanh thu (đ)", "Dòng thiếu giá"],
           sa, money={7}, widths=[14, 26, 14, 10, 14, 16, 16, 14])
    for c in ws[7 + len(sa)]:
        c.font = Font(bold=True)
    ws2 = wb.create_sheet("Theo SKU")
    _table(ws2, 1, ["Barcode", "Mã SKU", "Tên SKU", "Số lượng", "Số đơn", "Giá TB (đ)", "Doanh thu (đ)", "Số SA/BA bán"],
           [[s["barcode"], s["sku_id"], s["name"], s["qty"], s["orders"], s["avg_price"], s["revenue"], s["sas"]] for s in rep["by_sku"]],
           money={6, 7}, text={1}, widths=[17, 34, 58, 11, 10, 14, 16, 14])
    ws3 = wb.create_sheet("Chi tiết")
    _table(ws3, 1, ["Ngày", "Giờ", "Mã SA/BA", "Tên SA/BA", "Cửa hàng", "Mã cuộc", "Đơn #", "Phản hồi của khách", "Barcode", "Mã SKU",
                    "Tên SKU", "Số lượng", "Đơn giá (đ)", "Thành tiền (đ)", "Tình trạng"],
           [[l["date"], l["time"], l["sa_id"], l["sa_name"], l["store"], l["session_id"], l["order_id"], l["reply"], l["barcode"], l["sku_id"],
             l["sku_name"], l["qty"], l["price"], l["amount"], l["status"]] for l in rep["lines"]],
           money={13, 14}, text={9}, widths=[12, 7, 12, 22, 26, 15, 8, 20, 17, 34, 58, 10, 13, 15, 20])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------- API ----------
@router.get("/sas")
def sas(p: Principal = Depends(principal)):
    """Danh sách SA/BA đã có cuộc tư vấn (cho ô chọn SA trên web)."""
    admin_only(p)
    return db.query("SELECT MIN(sa_id) AS sa_id, MAX(sa_name) AS sa_name FROM sessions WHERE sa_id IS NOT NULL AND sa_id<>'' "
                    "GROUP BY lower(sa_id) ORDER BY MAX(sa_name)")


@router.get("/sales")
def sales(frm: str | None = Query(None, alias="from"), to: str | None = None, sa_id: str | None = None, include_declined: bool = False,
          p: Principal = Depends(principal)):
    """Xem trước: số liệu tổng hợp theo SA và theo SKU (chi tiết từng dòng nằm trong file Excel)."""
    rep = build(p, frm, to, sa_id, include_declined)
    rep["line_count"] = len(rep.pop("lines"))
    return rep


@router.get("/sales.xlsx")
def sales_xlsx(frm: str | None = Query(None, alias="from"), to: str | None = None, sa_id: str | None = None, include_declined: bool = False,
               p: Principal = Depends(principal)):
    rep = build(p, frm, to, sa_id, include_declined)
    who = re.sub(r"[^A-Za-z0-9_-]", "", rep["sa_id"])
    name = f"bao-cao-ban-hang_{rep['from']}_{rep['to']}{'_' + who if who else ''}.xlsx"
    return Response(to_xlsx(rep), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
