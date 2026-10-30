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


def top_skus(days: int = 7, include_declined: bool = False) -> dict:
    rows = db.query("SELECT customer_confirm, items_json FROM orders WHERE created_at>=?", (_since(days),))
    agg: dict[str, dict] = {}
    for r in rows:
        if r["customer_confirm"] == "no" and not include_declined:
            continue
        for it in json.loads(r["items_json"]):
            a = agg.setdefault(it["sku_id"], {"sku_id": it["sku_id"], "name": it["sku_name"], "qty": 0, "orders": 0})
            a["qty"] += it["qty"]
            a["orders"] += 1
    return {"top": sorted(agg.values(), key=lambda x: -x["qty"])}


def overview(days: int = 7) -> dict:
    since = _since(days)
    sessions = db.query(
        "SELECT id, sa_id, sa_name, created_at, transcript_text FROM sessions WHERE created_at>=?", (since,))
    orders = db.query(
        "SELECT o.*, s.sa_id, s.sa_name FROM orders o JOIN sessions s ON s.id=o.session_id WHERE o.created_at>=?",
        (since,))

    by_day = defaultdict(lambda: {"sessions": 0, "orders": 0, "units": 0})
    by_sa = defaultdict(lambda: {"sessions": 0, "orders": 0, "confirmed": 0, "units": 0, "scores": []})
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

    n_yes = n_no = pending = units_total = items_total = 0
    for o in orders:
        items = json.loads(o["items_json"])
        units = sum(i["qty"] for i in items)
        d = _local_date(o["created_at"])
        by_day[d]["orders"] += 1
        sa = by_sa[(o["sa_id"], o["sa_name"])]
        sa["orders"] += 1
        counted = o["customer_confirm"] != "no"
        if counted:
            by_day[d]["units"] += units
            sa["units"] += units
            units_total += units
            items_total += len(items)
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
            "avg_compliance": round(sum(scores) / len(scores)) if scores else 0,
        },
        "by_day": [{"date": k, **v} for k, v in sorted(by_day.items())],
        "by_sa": sorted(
            [{"sa_id": k[0], "sa_name": k[1], "sessions": v["sessions"], "orders": v["orders"],
              "confirmed": v["confirmed"], "units": v["units"],
              "avg_compliance": round(sum(v["scores"]) / len(v["scores"])) if v["scores"] else 0}
             for k, v in by_sa.items()],
            key=lambda x: -x["units"]),
        "objections": [{"key": k, "label": OBJECTIONS[k][0], "count": c}
                       for k, c in sorted(objections.items(), key=lambda x: -x[1])],
        "top_skus": top_skus(days)["top"][:10],
    }
