"""Nhận diện người nói: logic phân loại, parser theo lượt, API đăng ký giọng, pipeline.
Không cần model/âm thanh thật: dùng embedding giả và monkeypatch."""
import json
import os
import tempfile

import numpy as np
import pytest

os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(), "spk.db"))
os.environ.setdefault("AUDIO_DIR", tempfile.mkdtemp())

from fastapi.testclient import TestClient  # noqa: E402

from app import db, main, speaker  # noqa: E402
from app.coaching import analyze  # noqa: E402
from app.parser import parse_transcript  # noqa: E402

rng = np.random.default_rng(0)


def unit(v):
    return v / np.linalg.norm(v)


def voice(center, n, noise=0.03):
    return np.stack([unit(center + noise * rng.normal(size=center.shape)) for _ in range(n)])


A = unit(rng.normal(size=192))                       # giọng SA
B = unit(rng.normal(size=192))                       # giọng khách
C = unit(rng.normal(size=192))                       # người lạ


def test_classify_hai_giong_dung_cum():
    E = np.vstack([voice(A, 4), voice(B, 3)])
    sa, score, method = speaker.classify(E, A)
    assert method == "cluster"
    assert sa[:4].all() and not sa[4:].any()


def test_classify_chi_co_sa():
    sa, _, method = speaker.classify(voice(A, 5), A)
    assert method == "threshold" and sa.all()


def test_classify_sa_noi_nhieu_sac_thai_khong_bi_tach_nham():
    # SA nói 2 kiểu (ví dụ thì thầm / nói to): 2 cụm khác nhau nhưng cả hai đều giống dấu giọng
    D1, D2 = np.eye(192)[0], np.eye(192)[1]
    A0 = unit(np.eye(192)[2])
    E = np.vstack([voice(unit(A0 + .9 * D1), 3, .01), voice(unit(A0 + .9 * D2), 3, .01)])
    sa, _, method = speaker.classify(E, A0)
    assert sa.all() and method == "threshold"


def test_classify_chi_co_khach():
    sa, _, _ = speaker.classify(voice(B, 5), A)
    assert not sa.any()


def test_classify_cum_sa_phai_giong_dau_giong():
    # Hai giọng B và C, không ai là SA -> không được gán nhầm một cụm là SA
    sa, _, _ = speaker.classify(np.vstack([voice(B, 4), voice(C, 4)]), A)
    assert not sa.any()


def test_make_chunks_tach_theo_khoang_lang():
    w = lambda t, s, e: {"w": t, "start": s, "end": e}
    words = [w("a", 0, .4), w("b", .5, .9), w("c", 2.5, 3.0), w("d", 3.1, 3.6)]
    ch = speaker.make_chunks(words)
    assert [len(c["words"]) for c in ch] == [2, 2]


def turns(*pairs):
    return [{"speaker": s, "start": i, "end": i + 1, "text": t, "score": 0} for i, (s, t) in enumerate(pairs)]


def test_parse_turns_xac_nhan_lay_tu_loi_khach():
    t = turns(("sa", "Dạ em xin cảm ơn chị, vậy mình chốt 2 omo 800g."),
              ("customer", "Dạ đúng rồi em."))
    o = parse_transcript("", main.catalog, t)["orders"][0]
    assert o["customer_confirm"] == "yes" and o["confirm_source"] == "customer_turn"


def test_parse_turns_loi_sa_khong_bi_tinh_la_khach():
    # SA hỏi "chị có lấy thêm gì không ạ" - trước đây bị đọc là khách đồng ý/từ chối
    t = turns(("sa", "Dạ em xin cảm ơn chị, vậy mình chốt 2 omo 800g. Chị có lấy thêm gì không ạ?"),
              ("customer", "Thôi để chị suy nghĩ thêm."))
    o = parse_transcript("", main.catalog, t)["orders"][0]
    assert o["customer_confirm"] == "no"


def test_parse_turns_khach_chi_nghe_duoc_khi_dung_luot():
    t = turns(("sa", "Chào chị, chị đang dùng loại khác à, ok vậy chị xem thử nhé."),
              ("customer", "Chưa cần đâu em."),
              ("sa", "Dạ em xin cảm ơn chị, vậy mình chốt 1 dove 640ml."),
              ("customer", "Ok em lấy luôn."))
    r = parse_transcript("", main.catalog, t)
    assert len(r["orders"]) == 1 and r["orders"][0]["customer_confirm"] == "yes"


def test_parse_turns_nhieu_don():
    t = turns(("sa", "Dạ em cảm ơn chị, vậy mình chốt 2 omo 800g."), ("customer", "Dạ ok em."),
              ("sa", "Dạ em cảm ơn chị, vậy mình chốt 1 dove 640ml."), ("customer", "Thôi chị ơi."))
    r = parse_transcript("", main.catalog, t)
    assert [o["customer_confirm"] for o in r["orders"]] == ["yes", "no"]


def test_parse_turns_khong_co_luot_khach_dung_cach_cu():
    t = turns(("sa", "Dạ em xin cảm ơn chị, vậy mình chốt 2 omo 800g. Dạ đúng rồi em."))
    o = parse_transcript("", main.catalog, t)["orders"][0]
    assert o["customer_confirm"] == "yes" and o["confirm_source"] == "text"


def test_parse_turns_nhan_sai_thi_quay_ve_toan_van():
    t = turns(("customer", "x"))   # không có câu chốt trong lời SA
    r = parse_transcript("vậy mình chốt 1 dove 640ml. Dạ ok em.", main.catalog, t)
    assert r["orders"][0]["customer_confirm"] == "yes"


def test_coaching_cham_sa_theo_loi_sa_va_loi_tu_choi_theo_loi_khach():
    sa = "Xin chào chị, bên em có khuyến mãi tặng kèm."
    cu = "Đắt quá, để chị suy nghĩ."
    a = analyze("", sa, cu)
    passed = {c["key"]: c["passed"] for c in a["checklist"]}
    assert passed["greeting"] and passed["promo"]
    assert "price" in a["objections"] and "think" in a["objections"]
    # nếu "đắt quá" là lời SA thì không phải lý do từ chối của khách
    assert analyze("", "Xin chào chị, đắt quá nhỉ", "")["objections"] == []


def test_split_text():
    segs = [{"speaker": "sa", "text": "a"}, {"speaker": "customer", "text": "b"}, {"speaker": "sa", "text": "c"}]
    assert speaker.split_text(segs) == ("a c", "b")
    assert speaker.split_text([{"text": "x"}]) is None


# ---------------- API đăng ký giọng ----------------
c = TestClient(main.app)
FAKE = {"embedding": unit(rng.normal(size=192)).tolist(), "n_samples": 3, "voiced_seconds": 12.0, "consistency": 0.8}


@pytest.fixture
def fake_audio(monkeypatch):
    monkeypatch.setattr(speaker, "load_audio", lambda p: np.zeros(16000, np.float32))
    monkeypatch.setattr(speaker, "enroll_from_clips", lambda clips: FAKE)


def files(n=2):
    return [("audio", (f"s{i}.m4a", b"x", "audio/m4a")) for i in range(n)]


def test_dang_ky_can_dong_y(fake_audio):
    r = c.post("/api/voiceprints/saX", files=files(), data={"consent": "false"})
    assert r.status_code == 400
    assert c.get("/api/voiceprints/saX").json()["enrolled"] is False


def test_dang_ky_xem_xoa(fake_audio):
    r = c.post("/api/voiceprints/saY", files=files(), data={"consent": "true"})
    assert r.status_code == 200 and r.json()["n_samples"] == 3
    st = c.get("/api/voiceprints/saY").json()
    assert st["enrolled"] and "embedding_json" not in st          # không lộ vector ra ngoài
    assert c.post("/api/voiceprints/saY", files=files(), data={"consent": "true"}).status_code == 409
    assert c.post("/api/voiceprints/saY", files=files(), data={"consent": "true", "replace": "true"}).status_code == 200
    assert c.delete("/api/voiceprints/saY").status_code == 200
    assert c.get("/api/voiceprints/saY").json()["enrolled"] is False


def test_dang_ky_that_bai_422(monkeypatch):
    monkeypatch.setattr(speaker, "load_audio", lambda p: np.zeros(16000, np.float32))
    def boom(clips): raise ValueError("Cần ít nhất 8 giây")
    monkeypatch.setattr(speaker, "enroll_from_clips", boom)
    r = c.post("/api/voiceprints/saZ", files=files(1), data={"consent": "true"})
    assert r.status_code == 422 and "8 giây" in r.json()["detail"]


# ---------------- pipeline xử lý cuộc ghi ----------------
def test_process_dung_dau_giong(monkeypatch):
    import app.asr as asr
    db.execute("INSERT INTO voiceprints(sa_id,embedding_json,dim,model,n_samples,consent_at,updated_at) VALUES(?,?,?,?,?,?,?)",
               ("saP", json.dumps(FAKE["embedding"]), 192, "m", 3, db.now_str(), db.now_str()))
    db.execute("INSERT INTO sessions(id,sa_id,sa_name,store,audio_path,status,created_at) VALUES(?,?,?,?,?,'queued',?)",
               ("p1", "saP", "P", "", "/nonexistent.m4a", db.now_str()))
    text = "Dạ em xin cảm ơn chị, vậy mình chốt 2 omo 800g. Chị có lấy thêm gì không ạ. Thôi để chị suy nghĩ."
    monkeypatch.setattr(asr, "transcribe", lambda path, hot="": {
        "text": text, "segments": [{"start": 0, "end": 9, "text": text}], "words": [{"w": "x", "start": 0, "end": 1}], "duration": 9.0})
    monkeypatch.setattr(speaker, "diarize", lambda path, words, vp: {"method": "cluster", "sa_score": .9, "turns": [
        {"speaker": "sa", "start": 0, "end": 5, "score": .9, "text": "Dạ em xin cảm ơn chị, vậy mình chốt 2 omo 800g. Chị có lấy thêm gì không ạ."},
        {"speaker": "customer", "start": 5.5, "end": 8, "score": .1, "text": "Thôi để chị suy nghĩ."}]})
    main._process("p1")
    s = c.get("/api/sessions/p1").json()
    assert s["status"] == "done" and s["diarized"] is True
    assert [x["speaker"] for x in s["segments"]] == ["sa", "customer"]
    assert s["orders"][0]["customer_confirm"] == "no"


def test_process_khong_co_dau_giong_chay_nhu_cu(monkeypatch):
    import app.asr as asr
    db.execute("INSERT INTO sessions(id,sa_id,sa_name,store,audio_path,status,created_at) VALUES(?,?,?,?,?,'queued',?)",
               ("p2", "saNone", "N", "", "/nonexistent.m4a", db.now_str()))
    text = "Dạ em xin cảm ơn chị, vậy mình chốt 2 omo 800g. Dạ ok em."
    monkeypatch.setattr(asr, "transcribe", lambda path, hot="": {
        "text": text, "segments": [{"start": 0, "end": 5, "text": text}], "words": [], "duration": 5.0})
    called = []
    monkeypatch.setattr(speaker, "diarize", lambda *a: called.append(1))
    main._process("p2")
    s = c.get("/api/sessions/p2").json()
    assert not called and s["diarized"] is False and s["orders"][0]["customer_confirm"] == "yes"


def test_process_loi_nhan_dien_khong_lam_hong_phien(monkeypatch):
    import app.asr as asr
    db.execute("INSERT INTO voiceprints(sa_id,embedding_json,dim,model,n_samples,consent_at,updated_at) VALUES(?,?,?,?,?,?,?)",
               ("saQ", json.dumps(FAKE["embedding"]), 192, "m", 3, db.now_str(), db.now_str()))
    db.execute("INSERT INTO sessions(id,sa_id,sa_name,store,audio_path,status,created_at) VALUES(?,?,?,?,?,'queued',?)",
               ("p3", "saQ", "Q", "", "/nonexistent.m4a", db.now_str()))
    text = "Dạ em xin cảm ơn chị, vậy mình chốt 2 omo 800g. Dạ ok em."
    monkeypatch.setattr(asr, "transcribe", lambda path, hot="": {
        "text": text, "segments": [{"start": 0, "end": 5, "text": text}], "words": [{"w": "x", "start": 0, "end": 1}], "duration": 5.0})
    def boom(*a): raise RuntimeError("model missing")
    monkeypatch.setattr(speaker, "diarize", boom)
    main._process("p3")
    s = c.get("/api/sessions/p3").json()
    assert s["status"] == "done" and s["orders"][0]["customer_confirm"] == "yes"
