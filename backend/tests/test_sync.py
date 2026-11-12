"""Phiên tạo từ app: nhận dạng + parser trên máy -> /api/sessions/sync, audio nén + S3, chỉ mục catalog cho app."""
import io
import math
import os
import struct
import tempfile
import wave

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "sync.db")
os.environ["AUDIO_DIR"] = tempfile.mkdtemp()

import pytest
from fastapi.testclient import TestClient

from app import audio_codec, storage
from app.main import app, catalog
from app.parser import parse_transcript

c = TestClient(app, follow_redirects=False)
TEXT = ("dạ em xin cảm ơn chị, vậy mình chốt 2 omo bột giặt đỏ 9kg 65 nghìn, "
        "1 clear men nước hoa warm forest 350g 120 nghìn. dạ ok em")
OMO = "omo-bg-do-9kg"


def wav_bytes(seconds=2.0, rate=16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate))) for i in range(int(seconds * rate))))
    return buf.getvalue()


def sync(client_id, **kw):
    body = {"client_id": client_id, "transcript": TEXT, "duration": 12.5, "asr_engine": "test", "parser_version": "ts-1"} | kw
    return c.post("/api/sessions/sync", json=body)


def test_catalog_index_and_etag():
    r = c.get("/api/catalog/index")
    d = r.json()
    assert r.status_code == 200 and d["version"] and len(d["skus"]) == len(catalog.skus) and d["index"] and d["hotwords"]
    r2 = c.get("/api/catalog/index", headers={"If-None-Match": r.headers["etag"]})
    assert r2.status_code == 304


def test_sync_uses_device_orders_and_flags_parser_match():
    server = parse_transcript(TEXT, catalog)["orders"]
    r = sync("client-0001-aaaa", orders=server).json()
    assert r["status"] == "done" and not r["duplicate"] and r["audio_needed"]
    s = c.get(f"/api/sessions/{r['id']}").json()
    assert s["status"] == "done" and len(s["orders"]) == 1 and s["has_audio"] is False
    assert any(i["sku_id"] == OMO and i["qty"] == 2 for i in s["orders"][0]["items"])
    row = __import__("app.db", fromlist=["x"]).query("SELECT source, parser_match, asr_engine FROM sessions WHERE id=?", (r["id"],))[0]
    assert row == {"source": "device", "parser_match": 1, "asr_engine": "test"}


def test_sync_is_idempotent():
    a = sync("client-0002-bbbb").json()
    b = sync("client-0002-bbbb").json()
    assert a["id"] == b["id"] and b["duplicate"] is True
    assert len([s for s in c.get("/api/sessions").json() if s["id"] == a["id"]]) == 1


def test_sync_without_orders_parses_on_server():
    sid = sync("client-0003-cccc").json()["id"]
    assert len(c.get(f"/api/sessions/{sid}").json()["orders"]) == 1


def test_sync_sanitizes_device_orders():
    bad = [{"items": [
        {"sku_id": "khong-ton-tai", "qty": 1, "price": 1000},
        {"sku_id": OMO, "qty": 5000, "price": 1000},
        {"sku_id": OMO, "qty": 3, "price": -5, "conf": 7},
    ], "customer_confirm": "hack"}]
    sid = sync("client-0004-dddd", orders=bad).json()["id"]
    o = c.get(f"/api/sessions/{sid}").json()["orders"][0]
    assert len(o["items"]) == 1 and o["items"][0]["qty"] == 3 and o["items"][0]["price"] is None
    assert o["items"][0]["conf"] == 1.0 and o["items"][0]["need_confirm"] is True and o["customer_confirm"] == "none"


def test_sync_validates_client_id_and_rejects_empty_orders_gracefully():
    assert sync("x").status_code == 400
    sid = sync("client-0005-eeee", orders=[]).json()["id"]
    assert c.get(f"/api/sessions/{sid}").json()["orders"] == []


def test_capture_time_is_kept_within_30_days_only():
    import time
    two_days_ago = int((time.time() - 2 * 86400) * 1000)
    sid = sync("client-0006-ffff", captured_at=two_days_ago).json()["id"]
    created = c.get(f"/api/sessions/{sid}").json()["created_at"]
    assert created < __import__("app.db", fromlist=["x"]).now_str()
    sid2 = sync("client-0007-gggg", captured_at=1000).json()["id"]    # 1970: đồng hồ máy sai -> giờ server
    assert c.get(f"/api/sessions/{sid2}").json()["created_at"][:4] >= "2024"


def test_audio_upload_compresses_and_plays_local():
    sid = sync("client-0008-hhhh").json()["id"]
    wav = wav_bytes(3.0)
    r = c.post(f"/api/sessions/{sid}/audio", files={"audio": ("a.wav", wav, "audio/wav")})
    assert r.status_code == 200 and r.json()["stored"] == "local"
    assert c.get(f"/api/sessions/{sid}").json()["has_audio"] is True
    u = c.get(f"/api/sessions/{sid}/audio-url").json()
    assert u == {"url": f"/api/sessions/{sid}/audio", "auth": True, "expires_in": None}
    got = c.get(u["url"])
    assert got.status_code == 200
    if audio_codec.FFMPEG:                                                # máy test thiếu ffmpeg thì file được giữ nguyên
        assert len(got.content) < len(wav) / 3                            # nén >3 lần (WAV 16 kHz -> AAC 24 kbps)
    assert sync("client-0008-hhhh").json()["audio_needed"] is False


def test_audio_upload_guards():
    assert c.post("/api/sessions/nope/audio", files={"audio": ("a.wav", wav_bytes(), "audio/wav")}).status_code == 404
    sid = sync("client-0009-iiii").json()["id"]
    assert c.post(f"/api/sessions/{sid}/audio", files={"audio": ("a.wav", b"", "audio/wav")}).status_code == 400
    assert c.get(f"/api/sessions/{sid}/audio-url").status_code == 404


def test_audio_on_s3(monkeypatch):
    boto3 = pytest.importorskip("boto3")
    moto = pytest.importorskip("moto")
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(k, "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-southeast-1")
    with moto.mock_aws():
        boto3.client("s3").create_bucket(Bucket="voice-test", CreateBucketConfiguration={"LocationConstraint": "ap-southeast-1"})
        monkeypatch.setattr(storage, "AUDIO_BUCKET", "voice-test")
        monkeypatch.setattr(storage, "_client", None)
        sid = sync("client-0010-jjjj", sa_id="sa77").json()["id"]
        r = c.post(f"/api/sessions/{sid}/audio", files={"audio": ("a.wav", wav_bytes(), "audio/wav")})
        assert r.json()["stored"] == "s3"
        obj = boto3.client("s3").list_objects_v2(Bucket="voice-test", Prefix="audio/sa77/")["Contents"][0]
        assert obj["Key"].endswith(f"{sid}.m4a")
        head = boto3.client("s3").head_object(Bucket="voice-test", Key=obj["Key"])
        assert head["ContentType"] == "audio/mp4" and head["ServerSideEncryption"] == "AES256"
        u = c.get(f"/api/sessions/{sid}/audio-url").json()
        assert u["auth"] is False and u["url"].startswith("https://") and "voice-test" in u["url"] and "Signature" in u["url"]
        red = c.get(f"/api/sessions/{sid}/audio")
        assert red.status_code == 307 and red.headers["location"].startswith("https://")
        assert not [f for f in os.listdir(storage.AUDIO_DIR) if f.startswith(sid)]   # bản local đã xoá
