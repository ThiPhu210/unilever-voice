import hmac
import json
import os
import threading
import uuid

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import db, stats
from .coaching import analyze
from .parser import Catalog, parse_transcript

AUDIO_DIR = os.getenv("AUDIO_DIR", "data/audio")
os.makedirs(AUDIO_DIR, exist_ok=True)
db.init()
catalog = Catalog()
_asr_lock = threading.Semaphore(1)  # chỉ chạy 1 phiên ASR một lúc để không tràn RAM


def auth(request: Request):
    """Nếu đặt biến môi trường API_KEY thì mọi request (trừ /api/health) phải kèm
    header X-API-Key (hoặc ?key= cho thẻ <audio>)."""
    key = os.getenv("API_KEY", "")
    if not key or request.url.path == "/api/health":
        return
    got = request.headers.get("x-api-key") or request.query_params.get("key") or ""
    if not hmac.compare_digest(got, key):
        raise HTTPException(401, "invalid api key")


app = FastAPI(title="Unilever Voice Coach", dependencies=[Depends(auth)])
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _warm():
    if os.getenv("PRELOAD_ASR", "0") == "1":
        def go():
            try:
                from . import asr
                asr._model()
            except Exception as e:  # noqa
                print("ASR preload failed:", e)
        threading.Thread(target=go, daemon=True).start()


def _process(session_id: str):
    """Chạy ASR -> parser -> lưu DB (chạy nền)."""
    with _asr_lock:
        try:
            from . import asr
            db.execute("UPDATE sessions SET status='processing' WHERE id=?", (session_id,))
            s = db.query("SELECT audio_path FROM sessions WHERE id=?", (session_id,))[0]
            r = asr.transcribe(s["audio_path"], catalog.hotwords())
            parsed = parse_transcript(r["text"], catalog)
            db.execute(
                "UPDATE sessions SET transcript_text=?, segments_json=?, duration=?, status='done' WHERE id=?",
                (r["text"], json.dumps(r["segments"], ensure_ascii=False), r["duration"], session_id),
            )
            db.save_orders(session_id, parsed)
        except Exception as e:  # noqa
            db.execute("UPDATE sessions SET status='error', error=? WHERE id=?", (str(e)[:500], session_id))


@app.get("/api/health")
def health():
    return {"ok": True, "skus": len(catalog.skus)}


@app.get("/api/catalog")
def get_catalog():
    return list(catalog.skus.values())


@app.post("/api/sessions")
async def create_session(
    background: BackgroundTasks,
    audio: UploadFile = File(...),
    sa_id: str = Form("sa01"),
    sa_name: str = Form("SA Demo"),
    store: str = Form(""),
):
    sid = uuid.uuid4().hex[:12]
    ext = os.path.splitext(audio.filename or "")[1] or ".m4a"
    path = os.path.join(AUDIO_DIR, sid + ext)
    with open(path, "wb") as f:
        while chunk := await audio.read(1024 * 1024):
            f.write(chunk)
    db.execute(
        "INSERT INTO sessions(id,sa_id,sa_name,store,audio_path,status) VALUES(?,?,?,?,?,'queued')",
        (sid, sa_id, sa_name, store, path),
    )
    background.add_task(_process, sid)
    return {"id": sid, "status": "queued"}


class TextIn(BaseModel):
    transcript: str
    sa_id: str = "sa01"
    sa_name: str = "SA Demo"
    store: str = ""


@app.post("/api/parse-text")
def parse_text(body: TextIn):
    """Công cụ dev: thử parser bằng text, không lưu DB."""
    return parse_transcript(body.transcript, catalog)


@app.post("/api/sessions/text")
def create_session_from_text(body: TextIn):
    """Tạo session từ transcript (để thử web Coach khi chưa có ASR)."""
    sid = uuid.uuid4().hex[:12]
    db.execute(
        "INSERT INTO sessions(id,sa_id,sa_name,store,status,transcript_text) VALUES(?,?,?,?,'done',?)",
        (sid, body.sa_id, body.sa_name, body.store, body.transcript),
    )
    db.save_orders(sid, parse_transcript(body.transcript, catalog))
    return {"id": sid, "status": "done"}


def _orders(sid: str):
    rows = db.query("SELECT * FROM orders WHERE session_id=? ORDER BY id", (sid,))
    for r in rows:
        r["items"] = json.loads(r.pop("items_json"))
    return rows


@app.get("/api/sessions")
def list_sessions(sa_id: str | None = None, status: str | None = None, limit: int = 100):
    where, args = [], []
    if sa_id:
        where.append("sa_id=?"); args.append(sa_id)
    if status:
        where.append("status=?"); args.append(status)
    sql = "SELECT id,sa_id,sa_name,store,created_at,duration,status FROM sessions"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
    sessions = db.query(sql, args + [limit])
    if sessions:
        ph = ",".join("?" * len(sessions))
        rows = db.query(
            f"SELECT session_id, customer_confirm, items_json, needs_review, reviewed FROM orders WHERE session_id IN ({ph})",
            [s["id"] for s in sessions])
        agg: dict[str, dict] = {}
        for r in rows:
            a = agg.setdefault(r["session_id"], {"orders": 0, "units": 0, "confirm": [], "review": 0})
            a["orders"] += 1
            a["units"] += sum(i["qty"] for i in json.loads(r["items_json"]))
            a["confirm"].append(r["customer_confirm"])
            a["review"] += bool(r["needs_review"]) and not r["reviewed"]
        for s in sessions:
            a = agg.get(s["id"], {"orders": 0, "units": 0, "confirm": [], "review": 0})
            s.update(orders=a["orders"], units=a["units"], confirm=a["confirm"], pending_review=a["review"])
    return sessions


@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    rows = db.query("SELECT * FROM sessions WHERE id=?", (sid,))
    if not rows:
        raise HTTPException(404, "not found")
    s = rows[0]
    s["segments"] = json.loads(s.pop("segments_json") or "[]")
    s["has_audio"] = bool(s.pop("audio_path", None))
    s["orders"] = _orders(sid)
    s["coaching"] = analyze(s.get("transcript_text") or "")
    return s


@app.get("/api/sessions/{sid}/audio")
def get_audio(sid: str):
    rows = db.query("SELECT audio_path FROM sessions WHERE id=?", (sid,))
    if not rows or not rows[0]["audio_path"] or not os.path.exists(rows[0]["audio_path"]):
        raise HTTPException(404, "no audio")
    return FileResponse(rows[0]["audio_path"])


class ItemFix(BaseModel):
    sku_id: str
    qty: int


@app.put("/api/orders/{order_id}/items")
def fix_order(order_id: int, items: list[ItemFix]):
    """SA/BA chạm sửa lại SKU/số lượng trên app."""
    fixed = []
    for it in items:
        if it.sku_id not in catalog.skus:
            raise HTTPException(400, f"unknown sku {it.sku_id}")
        if it.qty < 1 or it.qty > 999:
            raise HTTPException(400, "invalid qty")
        fixed.append({"sku_id": it.sku_id, "sku_name": catalog.skus[it.sku_id]["name"],
                      "qty": it.qty, "conf": 1.0, "need_confirm": False, "manual": True})
    db.execute("UPDATE orders SET items_json=?, needs_review=0, reviewed=1 WHERE id=?",
               (json.dumps(fixed, ensure_ascii=False), order_id))
    return {"ok": True, "items": fixed}


@app.get("/api/stats/top-skus")
def top_skus(days: int = 7, include_declined: bool = False):
    return stats.top_skus(days, include_declined)


@app.get("/api/stats/overview")
def overview(days: int = 7):
    return stats.overview(days)
