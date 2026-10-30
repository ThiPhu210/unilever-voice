"""ASR dùng faster-whisper (CPU/GPU). Model đọc từ biến môi trường ASR_MODEL:
  - 'small' / 'medium' / 'large-v3'  : Whisper gốc
  - đường dẫn tới PhoWhisper đã convert sang CTranslate2 (khuyến nghị cho tiếng Việt)
"""
import os
from functools import lru_cache


@lru_cache(maxsize=1)
def _model():
    from faster_whisper import WhisperModel
    return WhisperModel(
        os.getenv("ASR_MODEL", "small"),
        device=os.getenv("ASR_DEVICE", "cpu"),
        compute_type=os.getenv("ASR_COMPUTE", "int8"),
    )


def transcribe(path: str, hotwords: str = "") -> dict:
    prompt = "Dạ em xin cảm ơn anh chị, vậy mình chốt. " + hotwords
    segs, info = _model().transcribe(
        path, language="vi", vad_filter=True, beam_size=5,
        initial_prompt=prompt[:800],
    )
    segments = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()} for s in segs]
    return {
        "text": " ".join(s["text"] for s in segments),
        "segments": segments,
        "duration": round(info.duration, 1),
    }
