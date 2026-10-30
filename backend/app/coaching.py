"""Chấm điểm tuân thủ kịch bản + bắt lý do từ chối bằng từ khóa (không LLM)."""
import re
from .parser.normalize import normalize

CHECKS = [
    ("greeting", "Chào hỏi khách", r"\b(xin chao|chao (anh|chi|co|chu|ban|em))\b"),
    ("ask_need", "Hỏi nhu cầu / thói quen dùng", r"\b(can tim|dang tim|nhu cau|thuong dung|dang dung|cho em hoi|minh can)\b"),
    ("promo", "Giới thiệu khuyến mãi", r"\b(khuyen mai|giam gia|tang kem|uu dai|combo|qua tang)\b"),
    ("upsell", "Gợi ý mua thêm / bán kèm", r"\b(mua them|lay them|dung kem|di kem|ket hop|size lon|loai lon|tiet kiem hon)\b"),
]
CLOSING_TEMPLATE = r"cam on.{0,60}\bch[oua]t\b"

OBJECTIONS = {
    "price": ("Chê giá đắt", r"\b(dat qua|hoi dat|dat vay|mac qua|hoi mac|mac vay|gia cao|qua tien)\b"),
    "no_need": ("Chưa cần", r"\b(chua can|khong can|con o nha|con dung)\b"),
    "competitor": ("Dùng hãng khác", r"\b(hang khac|quen dung|loai khac|dung cua)\b"),
    "think": ("Để suy nghĩ", r"\b(de (anh |chi |co |chu |minh |em )?(suy nghi|xem lai|sau)|xem them|tham khao)\b"),
}


def analyze(text: str) -> dict:
    n = normalize(text or "")
    checklist = [{"key": k, "label": lbl, "passed": bool(re.search(rx, n))} for k, lbl, rx in CHECKS]
    checklist.append({"key": "closing_template", "label": "Dùng đúng câu chốt đơn mẫu",
                      "passed": bool(re.search(CLOSING_TEMPLATE, n))})
    score = round(100 * sum(c["passed"] for c in checklist) / len(checklist))
    objections = [k for k, (_, rx) in OBJECTIONS.items() if re.search(rx, n)]
    return {"checklist": checklist, "score": score, "objections": objections}
