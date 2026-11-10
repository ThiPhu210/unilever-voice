"""ASR dùng faster-whisper (CPU/GPU). Biến môi trường:
  ASR_MODEL    mặc định 'nunu-willump/PhoWhisper-medium-ct2' (PhoWhisper tiếng Việt, đã convert CTranslate2).
               App chỉ nhận diện tiếng Việt nên các tên cỡ cũ 'small' / 'medium' / 'large-v3' (vd còn trong .env của CloudFormation)
               được tự ánh xạ sang PhoWhisper cùng cỡ, xem _VI_ALIASES. Muốn dùng Whisper gốc: đặt tên repo đầy đủ
               (vd 'Systran/faster-whisper-medium'). Cũng nhận repo HF khác hoặc đường dẫn thư mục model.
  ASR_DEVICE   'cuda' | 'cpu' | 'auto' (mặc định auto: có GPU thì dùng GPU)
  ASR_COMPUTE  GPU: float16 (mặc định) | int8_float16 ; CPU: int8 (mặc định)
  ASR_BEAM     beam size (mặc định 5; hạ xuống 1-2 nếu cần nhanh hơn nữa)
"""
import os
from functools import lru_cache


_VI_ALIASES = {
    "small": "qbsmlabs/PhoWhisper-small",
    "medium": "nunu-willump/PhoWhisper-medium-ct2",
    "large": "kiendt/PhoWhisper-large-ct2",
    "large-v3": "kiendt/PhoWhisper-large-ct2",
}


def _resolve_model(name: str) -> str:
    name = name.strip()
    return _VI_ALIASES.get(name, name)


def _pick_device() -> str:
    dev = os.getenv("ASR_DEVICE", "auto").lower()
    if dev != "auto":
        return dev
    try:
        import ctranslate2
        return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    except Exception:  # noqa
        return "cpu"


def _load(model: str, device: str, compute: str):
    from faster_whisper import WhisperModel
    return WhisperModel(model, device=device, compute_type=compute)


@lru_cache(maxsize=1)
def _model():
    name = _resolve_model(os.getenv("ASR_MODEL", "nunu-willump/PhoWhisper-medium-ct2"))
    device = _pick_device()
    compute = os.getenv("ASR_COMPUTE") or ("float16" if device == "cuda" else "int8")
    try:
        m = _load(name, device, compute)
    except Exception as e:  # noqa - thiếu CUDA/cuDNN, hết VRAM...: không để cả service chết, lùi về CPU
        if device != "cuda":
            raise
        print(f"ASR: không chạy được GPU ({e}); lùi về CPU int8")
        device, compute = "cpu", "int8"
        m = _load(name, device, compute)
    print(f"ASR sẵn sàng: model={name} device={device} compute={compute}")
    return m


def _run(path: str, prompt: str, word_ts: bool):
    segs, info = _model().transcribe(
        path, language="vi", vad_filter=True, beam_size=int(os.getenv("ASR_BEAM", "5")),
        initial_prompt=prompt[:800], word_timestamps=word_ts,
    )
    segments, words = [], []
    for s in segs:  # generator: lỗi (nếu có) sẽ nổ ở đây
        segments.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()})
        for w in (s.words or []):  # mốc thời gian từng từ -> dùng để tách lượt nói SA/khách
            words.append({"w": w.word, "start": round(w.start, 2), "end": round(w.end, 2)})
    return segments, words, info


def transcribe(path: str, hotwords: str = "") -> dict:
    prompt = "Dạ em xin cảm ơn anh chị, vậy mình chốt. " + hotwords
    try:
        segments, words, info = _run(path, prompt, True)
    except Exception as e:  # noqa - model convert thiếu alignment heads...: vẫn lấy được chữ, chỉ mất tách lượt nói theo từ
        print(f"ASR: word_timestamps lỗi ({e}); chạy lại không có mốc từ")
        segments, words, info = _run(path, prompt, False)
    return {
        "text": " ".join(s["text"] for s in segments),
        "segments": segments,
        "words": words,
        "duration": round(info.duration, 1),
    }