import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from . import db
from .coaching import OBJECTIONS, analyze

TZ_HOURS = int(os.getenv("TZ_OFFSET_HOURS", "7"))  # Việt Nam UTC+7


def _since(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def _local_date(ts: str) -> str:
    d = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S") + timedelta(hours=TZ_HOURS)
    return d.strftime("%Y-%m-%d")


def _line(it: dict) -> tuple[int, int]:
    """(doanh thu dòng, số lượng có giá). Dòng chưa có giá không tính vào doanh thu."""
    p = it.get("price")
    return (it["qty"] * p, it["qty"]) if p is not None else (0, 0)


def top_skus(days: int = 7, include_declined: bool = False) -> dict:
    rows = db.query("SELECT customer_confirm, items_json FROM orders WHERE created_at>=?", (_since(days),))
    agg: dict[str, dict] = {}
    for r in rows:
        if r["customer_confirm"] == "no" and not include_declined:
            continue
        for it in json.loads(r["items_json"]):
            a = agg.setdefault(it["sku_id"], {"sku_id": it["sku_id"], "name": it["sku_name"], "qty": 0,
                                              "orders": 0, "revenue": 0, "priced_qty": 0})
            rev, pq = _line(it)
            a["qty"] += it["qty"]
            a["orders"] += 1
            a["revenue"] += rev
            a["priced_qty"] += pq
    for a in agg.values():
        a["avg_price"] = round(a["revenue"] / a["priced_qty"]) if a["priced_qty"] else None
    return {"top": sorted(agg.values(), key=lambda x: -x["qty"])}


def sku_stats(days: int = 14) -> dict:
    """Mỗi SKU: tổng + chuỗi theo ngày (giờ VN) để vẽ xu hướng."""
    rows = db.query("SELECT customer_confirm, items_json, created_at FROM orders WHERE created_at>=?", (_since(days),))
    today = datetime.now(timezone.utc) + timedelta(hours=TZ_HOURS)
    dates = [(today - timedelta(days=k)).strftime("%Y-%m-%d") for k in range(days - 1, -1, -1)]
    agg: dict[str, dict] = {}
    for r in rows:
        if r["customer_confirm"] == "no":
            continue
        d = _local_date(r["created_at"])
        for it in json.loads(r["items_json"]):
            a = agg.setdefault(it["sku_id"], {"sku_id": it["sku_id"], "name": it["sku_name"], "qty": 0, "orders": 0,
                                              "revenue": 0, "priced_qty": 0, "last_sold": d,
                                              "by_day": {x: {"qty": 0, "revenue": 0} for x in dates}})
            rev, pq = _line(it)
            a["qty"] += it["qty"]; a["orders"] += 1; a["revenue"] += rev; a["priced_qty"] += pq
            a["last_sold"] = max(a["last_sold"], d)
            if d in a["by_day"]:
                a["by_day"][d]["qty"] += it["qty"]; a["by_day"][d]["revenue"] += rev
    out = []
    for a in agg.values():
        a["avg_price"] = round(a["revenue"] / a["priced_qty"]) if a["priced_qty"] else None
        a["by_day"] = [{"date": x, **a["by_day"][x]} for x in dates]
        out.append(a)
    return {"days": days, "dates": dates, "skus": sorted(out, key=lambda x: -x["qty"])}


def overview(days: int = 7) -> dict:
    since = _since(days)
    sessions = db.query(
        "SELECT id, sa_id, sa_name, created_at, transcript_text FROM sessions WHERE created_at>=?", (since,))
    orders = db.query(
        "SELECT o.*, s.sa_id, s.sa_name FROM orders o JOIN sessions s ON s.id=o.session_id WHERE o.created_at>=?",
        (since,))

    by_day = defaultdict(lambda: {"sessions": 0, "orders": 0, "units": 0, "revenue": 0})
    by_sa = defaultdict(lambda: {"sessions": 0, "orders": 0, "confirmed": 0, "units": 0, "revenue": 0, "scores": []})
    objections: dict[str, int] = defaultdict(int)
    scores = []

    for s in sessions:
        d = _local_date(s["created_at"])
        by_day[d]["sessions"] += 1
        sa = by_sa[(s["sa_id"], s["sa_name"])]
        sa["sessions"] += 1
        if s["transcript_text"]:
            a = analyze(s["transcript_text"])
            scores.append(a["score"])
            sa["scores"].append(a["score"])
            for o in a["objections"]:
                objections[o] += 1

    n_yes = n_no = pending = units_total = items_total = revenue_total = missing_price = 0
    for o in orders:
        items = json.loads(o["items_json"])
        units = sum(i["qty"] for i in items)
        d = _local_date(o["created_at"])
        by_day[d]["orders"] += 1
        sa = by_sa[(o["sa_id"], o["sa_name"])]
        sa["orders"] += 1
        counted = o["customer_confirm"] != "no"
        rev = sum(_line(i)[0] for i in items)
        if counted:
            by_day[d]["units"] += units
            by_day[d]["revenue"] += rev
            sa["units"] += units
            sa["revenue"] += rev
            units_total += units
            revenue_total += rev
            items_total += len(items)
        missing_price += any(i.get("price") is None for i in items)
        n_yes += o["customer_confirm"] == "yes"
        n_no += o["customer_confirm"] == "no"
        sa["confirmed"] += o["customer_confirm"] == "yes"
        pending += bool(o["needs_review"]) and not o["reviewed"]

    n_orders = len(orders)
    n_counted = n_orders - n_no
    return {
        "days": days,
        "kpi": {
            "sessions": len(sessions), "orders": n_orders, "confirmed": n_yes, "declined": n_no,
            "confirm_rate": round(100 * n_yes / n_orders) if n_orders else 0,
            "avg_units_per_order": round(units_total / n_counted, 1) if n_counted else 0,
            "avg_skus_per_order": round(items_total / n_counted, 1) if n_counted else 0,
            "pending_review": pending,
            "revenue": revenue_total,
            "avg_order_value": round(revenue_total / n_counted) if n_counted else 0,
            "missing_price": missing_price,
            "avg_compliance": round(sum(scores) / len(scores)) if scores else 0,
        },
        "by_day": [{"date": k, **v} for k, v in sorted(by_day.items())],
        "by_sa": sorted(
            [{"sa_id": k[0], "sa_name": k[1], "sessions": v["sessions"], "orders": v["orders"],
              "confirmed": v["confirmed"], "units": v["units"], "revenue": v["revenue"],
              "avg_compliance": round(sum(v["scores"]) / len(v["scores"])) if v["scores"] else 0}
             for k, v in by_sa.items()],
            key=lambda x: -x["units"]),
        "objections": [{"key": k, "label": OBJECTIONS[k][0], "count": c}
                       for k, c in sorted(objections.items(), key=lambda x: -x[1])],
        "top_skus": top_skus(days)["top"][:10],
    }
