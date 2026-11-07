import json
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import db, speaker, stats
from .auth import Principal, admin_only, owns, principal, router as auth_router
from .reports import router as reports_router
from .coaching import analyze
from .parser import Catalog, parse_transcript

AUDIO_DIR = os.getenv("AUDIO_DIR", "data/audio")
os.makedirs(AUDIO_DIR, exist_ok=True)
db.init()
catalog = Catalog()
db.sync_skus(catalog.skus, catalog.rows)
_asr_lock = threading.Semaphore(1)  # chỉ chạy 1 phiên ASR một lúc để không tràn RAM


app = FastAPI(title="Unilever Voice Coach", dependencies=[Depends(principal)])
app.include_router(auth_router)
app.include_router(reports_router)
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
            s = db.query("SELECT audio_path, sa_id FROM sessions WHERE id=?", (session_id,))[0]
            r = asr.transcribe(s["audio_path"], catalog.hotwords())
            segments, turns = r["segments"], None
            vp = db.query("SELECT embedding_json FROM voiceprints WHERE sa_id=?", (s["sa_id"],))
            if vp:  # SA đã đăng ký giọng -> tách lượt nói SA / khách
                try:
                    d = speaker.diarize(s["audio_path"], r.get("words", []), json.loads(vp[0]["embedding_json"]))
                    if d["turns"]:
                        turns = d["turns"]
                        segments = [{k: t[k] for k in ("start", "end", "speaker", "score")} | {"text": t["text"]} for t in turns]
                except Exception as e:  # noqa - lỗi nhận diện giọng không được làm hỏng cả phiên: dùng cách cũ
                    print("diarize failed:", e)
            parsed = parse_transcript(r["text"], catalog, turns)
            db.execute(
                "UPDATE sessions SET transcript_text=?, segments_json=?, duration=?, status='done' WHERE id=?",
                (r["text"], json.dumps(segments, ensure_ascii=False), r["duration"], session_id),
            )
            db.save_orders(session_id, parsed)
        except Exception as e:  # noqa
            db.execute("UPDATE sessions SET status='error', error=? WHERE id=?", (str(e)[:500], session_id))


@app.get("/api/health")
def health():
    return {"ok": True, "skus": len(catalog.skus), "db": "postgres" if db.IS_PG else "sqlite"}


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
    p: Principal = Depends(principal),
):
    if p.kind == "ba":   # BA đã đăng nhập: danh tính lấy từ token, không tin sa_id/sa_name app gửi lên
        sa_id, sa_name, store = p.sa_id, p.sa_name, (store or p.store)
    sid = uuid.uuid4().hex[:12]
    ext = os.path.splitext(audio.filename or "")[1] or ".m4a"
    path = os.path.join(AUDIO_DIR, sid + ext)
    with open(path, "wb") as f:
        while chunk := await audio.read(1024 * 1024):
            f.write(chunk)
    db.execute(
        "INSERT INTO sessions(id,sa_id,sa_name,store,audio_path,status,created_at) VALUES(?,?,?,?,?,'queued',?)",
        (sid, sa_id, sa_name, store, path, db.now_str()),
    )
    background.add_task(_process, sid)
    return {"id": sid, "status": "queued"}


class TextIn(BaseModel):
    transcript: str
    sa_id: str = "sa01"
    sa_name: str = "SA Demo"
    store: str = ""
    days_ago: int = 0  # chỉ để nạp dữ liệu mẫu nhiều ngày


@app.post("/api/parse-text")
def parse_text(body: TextIn, p: Principal = Depends(principal)):
    """Công cụ dev: thử parser bằng text, không lưu DB."""
    admin_only(p)
    return parse_transcript(body.transcript, catalog)


@app.post("/api/sessions/text")
def create_session_from_text(body: TextIn, p: Principal = Depends(principal)):
    """Tạo session từ transcript (để thử web Coach khi chưa có ASR)."""
    admin_only(p)
    sid = uuid.uuid4().hex[:12]
    created = (datetime.now(timezone.utc) - timedelta(days=max(0, min(body.days_ago, 365)))).strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        "INSERT INTO sessions(id,sa_id,sa_name,store,status,transcript_text,created_at) "
        "VALUES(?,?,?,?,'done',?,?)",
        (sid, body.sa_id, body.sa_name, body.store, body.transcript, created),
    )
    db.save_orders(sid, parse_transcript(body.transcript, catalog), created)
    return {"id": sid, "status": "done"}


def _orders(sid: str):
    rows = db.query("SELECT * FROM orders WHERE session_id=? ORDER BY id", (sid,))
    for r in rows:
        r["items"] = json.loads(r.pop("items_json"))
        r["missing_price"] = sum(1 for i in r["items"] if i.get("price") is None)
        r["total"] = sum(i["qty"] * i["price"] for i in r["items"] if i.get("price") is not None)
    return rows


@app.get("/api/sessions")
def list_sessions(sa_id: str | None = None, status: str | None = None, limit: int = 100,
                  p: Principal = Depends(principal)):
    where, args = [], []
    if p.kind == "ba":   # BA chỉ thấy cuộc tư vấn của mình (bỏ qua sa_id client gửi)
        where.append("lower(sa_id)=?"); args.append(p.sa_id.lower())
    elif sa_id:
        where.append("sa_id=?"); args.append(sa_id)
    if status:
        where.append("status=?"); args.append(status)
    sql = "SELECT id,sa_id,sa_name,store,created_at,duration,status FROM sessions"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    sessions = db.query(sql, args + [limit])
    if sessions:
        ph = ",".join("?" * len(sessions))
        rows = db.query(
            f"SELECT session_id, customer_confirm, items_json, needs_review, reviewed FROM orders WHERE session_id IN ({ph})",
            [s["id"] for s in sessions])
        agg: dict[str, dict] = {}
        for r in rows:
            a = agg.setdefault(r["session_id"], {"orders": 0, "units": 0, "confirm": [], "review": 0, "missing": 0, "revenue": 0})
            a["orders"] += 1
            its = json.loads(r["items_json"])
            a["units"] += sum(i["qty"] for i in its)
            a["revenue"] += sum(i["qty"] * i["price"] for i in its if i.get("price") is not None)
            a["missing"] += any(i.get("price") is None for i in its)
            a["confirm"].append(r["customer_confirm"])
            a["review"] += bool(r["needs_review"]) and not r["reviewed"]
        for s in sessions:
            a = agg.get(s["id"], {"orders": 0, "units": 0, "confirm": [], "review": 0, "missing": 0, "revenue": 0})
            s.update(orders=a["orders"], units=a["units"], confirm=a["confirm"], pending_review=a["review"],
                     missing_price=a["missing"], revenue=a["revenue"])
    return sessions


@app.get("/api/sessions/{sid}")
def get_session(sid: str, p: Principal = Depends(principal)):
    rows = db.query("SELECT * FROM sessions WHERE id=?", (sid,))
    if not rows or not owns(p, rows[0]["sa_id"]):
        raise HTTPException(404, "not found")
    s = rows[0]
    s["segments"] = json.loads(s.pop("segments_json") or "[]")
    s["has_audio"] = bool(s.pop("audio_path", None))
    s["orders"] = _orders(sid)
    sp = speaker.split_text(s["segments"])  # đã tách người nói: chấm SA theo lời SA, lý do từ chối theo lời khách
    s["diarized"] = sp is not None
    s["coaching"] = analyze(s.get("transcript_text") or "", *(sp or (None, None)))
    return s


@app.get("/api/sessions/{sid}/audio")
def get_audio(sid: str, p: Principal = Depends(principal)):
    rows = db.query("SELECT audio_path, sa_id FROM sessions WHERE id=?", (sid,))
    if not rows or not owns(p, rows[0]["sa_id"]) or not rows[0]["audio_path"] or not os.path.exists(rows[0]["audio_path"]):
        raise HTTPException(404, "no audio")
    return FileResponse(rows[0]["audio_path"])


class ItemFix(BaseModel):
    sku_id: str
    qty: int
    price: int | None = None  # đơn giá (VND) / 1 đơn vị SKU; None = chưa có giá


def _clean_items(items: list[ItemFix]) -> list[dict]:
    if not items:
        raise HTTPException(400, "empty order")
    fixed = []
    for it in items:
        if it.sku_id not in catalog.skus:
            raise HTTPException(400, f"unknown sku {it.sku_id}")
        if it.qty < 1 or it.qty > 999:
            raise HTTPException(400, "invalid qty")
        if it.price is not None and not (0 <= it.price <= 50_000_000):
            raise HTTPException(400, "invalid price")
        fixed.append({"sku_id": it.sku_id, "sku_name": catalog.skus[it.sku_id]["name"],
                      "qty": it.qty, "price": it.price, "price_missing": it.price is None,
                      "conf": 1.0, "need_confirm": False, "manual": True})
    return fixed


@app.put("/api/orders/{order_id}/items")
def fix_order(order_id: int, items: list[ItemFix], p: Principal = Depends(principal)):
    """SA/BA chạm sửa lại SKU / số lượng / giá (hoặc bổ sung giá quên nói) trên app."""
    own = db.query("SELECT s.sa_id FROM orders o JOIN sessions s ON s.id=o.session_id WHERE o.id=?", (order_id,))
    if not own or not owns(p, own[0]["sa_id"]):
        raise HTTPException(404, "order not found")
    fixed = _clean_items(items)
    db.execute("UPDATE orders SET items_json=?, needs_review=0, reviewed=1 WHERE id=?",
               (json.dumps(fixed, ensure_ascii=False), order_id))
    return {"ok": True, "items": fixed}


@app.post("/api/sessions/{sid}/orders")
def add_order(sid: str, items: list[ItemFix], p: Principal = Depends(principal)):
    """SA/BA tự thêm đơn khi hệ thống không nghe thấy câu chốt đơn (đã được SA xác nhận)."""
    own = db.query("SELECT sa_id FROM sessions WHERE id=?", (sid,))
    if not own or not owns(p, own[0]["sa_id"]):
        raise HTTPException(404, "session not found")
    fixed = _clean_items(items)
    oid = db.execute(
        "INSERT INTO orders(session_id,closing_text,customer_confirm,items_json,needs_review,reviewed,created_at) "
        "VALUES(?,?,?,?,0,1,?)",
        (sid, "(SA/BA nhập tay)", "yes", json.dumps(fixed, ensure_ascii=False), db.now_str()))
    return {"ok": True, "id": oid, "items": fixed}


# ---------- Đăng ký giọng nói SA ----------
def _own_voice_id(p: Principal, sa_id: str) -> str:
    """BA chỉ được đụng vào dấu giọng của chính mình; luôn dùng mã chuẩn từ token để khớp với sessions.sa_id."""
    if p.kind != "ba":
        return sa_id
    if sa_id.lower() != p.sa_id.lower():
        raise HTTPException(403, "Chỉ được thao tác dấu giọng của chính bạn")
    return p.sa_id


@app.get("/api/voiceprints/{sa_id}")
def voiceprint_status(sa_id: str, p: Principal = Depends(principal)):
    sa_id = _own_voice_id(p, sa_id)
    r = db.query("SELECT n_samples, consent_at, updated_at FROM voiceprints WHERE sa_id=?", (sa_id,))
    return {"enrolled": bool(r), **(r[0] if r else {})}


@app.post("/api/voiceprints/{sa_id}")
async def enroll_voiceprint(
    sa_id: str,
    audio: list[UploadFile] = File(...),
    consent: bool = Form(False),
    replace: bool = Form(False),
    p: Principal = Depends(principal),
):
    """SA ghi 2-3 đoạn đọc mẫu (tổng >= 8s có tiếng) -> lưu dấu giọng. Không lưu file âm thanh."""
    sa_id = _own_voice_id(p, sa_id)
    if not consent:
        raise HTTPException(400, "Cần SA đồng ý (consent=true) trước khi lưu dấu giọng")
    if db.query("SELECT 1 FROM voiceprints WHERE sa_id=?", (sa_id,)) and not replace:
        raise HTTPException(409, "SA này đã đăng ký giọng; gửi replace=true để đăng ký lại")
    if len(audio) > 6:
        raise HTTPException(400, "Tối đa 6 đoạn ghi")
    import tempfile
    clips = []
    for f in audio:
        ext = os.path.splitext(f.filename or "")[1] or ".m4a"
        with tempfile.NamedTemporaryFile(suffix=ext, delete=True) as tmp:
            total = 0
            while chunk := await f.read(1024 * 1024):
                total += len(chunk)
                if total > 20 * 1024 * 1024:
                    raise HTTPException(413, "File quá lớn")
                tmp.write(chunk)
            tmp.flush()
            try:
                clips.append(speaker.load_audio(tmp.name))
            except Exception:
                raise HTTPException(400, "Không đọc được file âm thanh")
    try:
        r = speaker.enroll_from_clips(clips)
    except ValueError as e:
        raise HTTPException(422, str(e))
    now = db.now_str()
    db.execute(
        "INSERT INTO voiceprints(sa_id,embedding_json,dim,model,n_samples,consent_at,updated_at) VALUES(?,?,?,?,?,?,?) "
        "ON CONFLICT(sa_id) DO UPDATE SET embedding_json=excluded.embedding_json, dim=excluded.dim, model=excluded.model, "
        "n_samples=excluded.n_samples, consent_at=excluded.consent_at, updated_at=excluded.updated_at",
        (sa_id, json.dumps(r["embedding"]), len(r["embedding"]), os.path.basename(speaker.MODEL_PATH),
         r["n_samples"], now, now))
    return {"ok": True, "n_samples": r["n_samples"], "voiced_seconds": r["voiced_seconds"], "consistency": r["consistency"]}


@app.delete("/api/voiceprints/{sa_id}")
def delete_voiceprint(sa_id: str, p: Principal = Depends(principal)):
    """SA rút lại đồng ý -> xoá dấu giọng."""
    sa_id = _own_voice_id(p, sa_id)
    db.execute("DELETE FROM voiceprints WHERE sa_id=?", (sa_id,))
    return {"ok": True}


@app.get("/api/stats/top-skus")
def top_skus(days: int = 7, include_declined: bool = False, p: Principal = Depends(principal)):
    admin_only(p)
    return stats.top_skus(days, include_declined)


@app.get("/api/stats/skus")
def sku_stats(days: int = 14, p: Principal = Depends(principal)):
    """Xu hướng mua sắm theo SKU: số lượng, doanh thu, giá TB, theo từng ngày."""
    admin_only(p)
    return stats.sku_stats(days)


@app.get("/api/stats/overview")
def overview(days: int = 7, p: Principal = Depends(principal)):
    admin_only(p)
    return stats.overview(days)
