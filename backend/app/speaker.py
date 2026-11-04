"""Nhận diện người nói: SA đăng ký "dấu giọng" (voiceprint) -> gắn nhãn từng lượt nói là SA hay khách.

Không dùng LLM, không dùng torch: embedding giọng nói bằng sherpa-onnx (CAM++ 192 chiều, chạy CPU).
Chỉ lưu vector embedding (không lưu âm thanh đăng ký). Vector là dữ liệu sinh trắc học -> cần SA đồng ý (consent).

Luồng:
  enroll()  : 3 đoạn ghi mẫu của SA -> embedding trung bình -> bảng voiceprints
  diarize() : từ danh sách từ có mốc thời gian của ASR -> chia khúc -> embedding từng khúc -> SA/khách
"""
import json
import os
import subprocess
import threading
from functools import lru_cache

import numpy as np

SR = 16000
MODEL_PATH = os.getenv("SPEAKER_MODEL", "models/speaker.onnx")
SA_THRESHOLD = float(os.getenv("SPEAKER_THRESHOLD", "0.45"))   # cosine >= ngưỡng => SA (khi chỉ có 1 giọng)
CLUSTER_MAX_SIM = 0.75   # hai tâm cụm giống nhau hơn mức này => coi như chỉ có 1 người nói
MIN_VOICED_ENROLL = float(os.getenv("SPEAKER_MIN_ENROLL_SEC", "8"))
MIN_PAIR_SIM = 0.40      # các đoạn đăng ký phải giống nhau ít nhất mức này (cùng một người, không quá ồn)
_lock = threading.Lock()


def load_audio(path: str) -> np.ndarray:
    """Giải mã mọi định dạng (m4a/aac/wav/webm) -> float32 mono 16kHz."""
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
        capture_output=True, check=True)
    return np.frombuffer(p.stdout, dtype=np.float32).copy()


@lru_cache(maxsize=1)
def _extractor():
    import sherpa_onnx
    if not os.path.exists(MODEL_PATH):
        raise RuntimeError(f"Chưa có model nhận diện giọng: {MODEL_PATH} (đặt biến SPEAKER_MODEL)")
    cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=MODEL_PATH, num_threads=2, debug=False, provider="cpu")
    return sherpa_onnx.SpeakerEmbeddingExtractor(cfg)


def embed(samples: np.ndarray) -> np.ndarray:
    with _lock:
        ex = _extractor()
        st = ex.create_stream()
        st.accept_waveform(sample_rate=SR, waveform=samples.astype(np.float32))
        st.input_finished()
        v = np.array(ex.compute(st), dtype=np.float32)
    return v / (np.linalg.norm(v) + 1e-9)


def voiced_ratio_samples(x: np.ndarray) -> np.ndarray:
    """Giữ lại các khung có tiếng (loại khoảng lặng) bằng ngưỡng năng lượng thích nghi."""
    fr = 400  # 25 ms
    n = len(x) // fr
    if n == 0:
        return x
    f = x[: n * fr].reshape(n, fr)
    e = np.sqrt((f ** 2).mean(axis=1) + 1e-12)
    thr = max(np.percentile(e, 90) * 0.15, 1e-3)
    return f[e > thr].reshape(-1)


# ---------------- đăng ký giọng ----------------
def enroll_from_clips(clips: list[np.ndarray]) -> dict:
    """clips: danh sách đoạn ghi mẫu (đã decode). Trả về {embedding, n_samples, voiced_seconds, consistency}."""
    embs, voiced = [], 0.0
    for c in clips:
        v = voiced_ratio_samples(c)
        voiced += len(v) / SR
        if len(v) >= SR * 1.0:
            embs.append(embed(v))
    if voiced < MIN_VOICED_ENROLL or len(embs) < 1:
        raise ValueError(f"Cần ít nhất {MIN_VOICED_ENROLL:.0f} giây có tiếng nói (hiện có {voiced:.1f}s). Hãy đọc to và rõ hơn.")
    cons = 1.0
    if len(embs) >= 2:
        sims = [float(embs[i] @ embs[j]) for i in range(len(embs)) for j in range(i + 1, len(embs))]
        cons = min(sims)
        if cons < MIN_PAIR_SIM:
            raise ValueError("Các đoạn ghi nghe không giống cùng một người hoặc quá nhiều tạp âm. Hãy ghi lại ở nơi yên tĩnh.")
    m = np.mean(embs, axis=0)
    m = m / np.linalg.norm(m)
    return {"embedding": m.tolist(), "n_samples": len(embs), "voiced_seconds": round(voiced, 1), "consistency": round(cons, 2)}


# ---------------- gắn nhãn người nói ----------------
def make_chunks(words: list[dict], max_dur: float = 4.0, gap_split: float = 0.6, gap_soft: float = 0.25) -> list[dict]:
    """Chia các từ (có start/end) thành khúc để embedding: tách khi có khoảng lặng dài hoặc khúc quá dài."""
    chunks, cur = [], []
    for w in words:
        if cur:
            gap = w["start"] - cur[-1]["end"]
            dur = cur[-1]["end"] - cur[0]["start"]
            if gap >= gap_split or (dur >= max_dur and gap >= gap_soft) or dur >= max_dur * 1.8:
                chunks.append(cur); cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    out = [{"words": c, "start": c[0]["start"], "end": c[-1]["end"]} for c in chunks]
    # khúc quá ngắn (<0.6s) dính vào khúc liền trước nếu sát nhau (<1s)
    merged: list[dict] = []
    for c in out:
        if merged and (c["end"] - c["start"]) < 0.6 and (c["start"] - merged[-1]["end"]) < 1.0:
            merged[-1]["words"] += c["words"]; merged[-1]["end"] = c["end"]
        else:
            merged.append(c)
    return merged


def classify(embs: np.ndarray, vp: np.ndarray, thr: float = SA_THRESHOLD) -> tuple[np.ndarray, np.ndarray, str]:
    """Trả về (is_sa[bool], score[cosine với dấu giọng], method).

    Có >=2 giọng khác nhau trong cuộc ghi -> gom 2 cụm (2-means, khởi tạo từ khúc giống/không giống SA nhất),
    cụm nào giống dấu giọng hơn là SA. Chỉ có 1 giọng -> dùng ngưỡng tuyệt đối."""
    s = embs @ vp
    if len(embs) >= 3:
        a, b = embs[int(np.argmax(s))], embs[int(np.argmin(s))]
        if float(a @ b) < CLUSTER_MAX_SIM:
            grp = np.ones(len(embs), bool)
            for _ in range(8):
                grp = (embs @ a) >= (embs @ b)
                if grp.all() or (~grp).all():
                    break
                a = embs[grp].mean(0); a /= np.linalg.norm(a)
                b = embs[~grp].mean(0); b /= np.linalg.norm(b)
            if not (grp.all() or (~grp).all()):
                sa = grp if s[grp].mean() >= s[~grp].mean() else ~grp
                # cụm "SA" phải giống dấu giọng, và cụm còn lại phải KHÁC dấu giọng rõ rệt; nếu cả hai cụm đều
                # giống SA thì đó chỉ là SA nói với nhiều sắc thái -> dùng ngưỡng tuyệt đối, không tách nhầm.
                if s[sa].mean() >= thr * 0.7 and s[~sa].mean() < thr:
                    return sa, s, "cluster"
    return s >= thr, s, "threshold"


def _smooth(lab: list[bool], dur: list[float]) -> list[bool]:
    """Khúc ngắn (<1.2s) bị kẹp giữa hai khúc cùng nhãn -> theo nhãn hàng xóm."""
    out = lab[:]
    for i in range(1, len(lab) - 1):
        if dur[i] < 1.2 and lab[i - 1] == lab[i + 1] != lab[i]:
            out[i] = lab[i - 1]
    return out


def diarize(audio_path: str, words: list[dict], voiceprint: list[float]) -> dict:
    """words: [{'w':str,'start':float,'end':float}], trả về {'turns': [...], 'method': str, 'sa_score': float}.
    turn = {'speaker': 'sa'|'customer', 'start', 'end', 'text', 'score'}"""
    if not words:
        return {"turns": [], "method": "none", "sa_score": 0.0}
    audio = load_audio(audio_path)
    vp = np.array(voiceprint, dtype=np.float32)
    chunks = make_chunks(words)
    embs = []
    for c in chunks:
        pad = max(0.0, (0.9 - (c["end"] - c["start"])) / 2) + 0.05  # khúc quá ngắn: nới thêm ngữ cảnh
        a, b = int(max(0, (c["start"] - pad) * SR)), int(min(len(audio), (c["end"] + pad) * SR))
        embs.append(embed(audio[a:b]) if b - a >= SR * 0.4 else vp * 0)
    E = np.stack(embs)
    is_sa, score, method = classify(E, vp)
    labels = _smooth(list(map(bool, is_sa)), [c["end"] - c["start"] for c in chunks])
    turns: list[dict] = []
    for c, sa, sc in zip(chunks, labels, score):
        sp = "sa" if sa else "customer"
        text = " ".join(w["w"].strip() for w in c["words"]).strip()
        if turns and turns[-1]["speaker"] == sp:
            t = turns[-1]; t["end"] = round(c["end"], 2); t["text"] += " " + text; t["_s"].append(float(sc))
        else:
            turns.append({"speaker": sp, "start": round(c["start"], 2), "end": round(c["end"], 2), "text": text, "_s": [float(sc)]})
    for t in turns:
        t["score"] = round(float(np.mean(t.pop("_s"))), 2)
    sa_scores = [t["score"] for t in turns if t["speaker"] == "sa"]
    return {"turns": turns, "method": method, "sa_score": round(float(np.mean(sa_scores)), 2) if sa_scores else 0.0}


def split_text(segments: list[dict]) -> tuple[str, str] | None:
    """Từ segments đã có nhãn -> (lời SA, lời khách). None nếu cuộc ghi chưa gắn nhãn người nói."""
    if not segments or not any("speaker" in s for s in segments):
        return None
    sa = " ".join(s["text"] for s in segments if s.get("speaker") == "sa")
    cu = " ".join(s["text"] for s in segments if s.get("speaker") == "customer")
    return sa, cu
