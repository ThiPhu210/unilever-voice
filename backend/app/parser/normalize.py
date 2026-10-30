import re
import unicodedata


def strip_accents(s: str) -> str:
    s = s.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def normalize(text: str) -> str:
    """Lowercase, bỏ dấu tiếng Việt, giữ lại , . ; ? ! để cắt câu/mệnh đề."""
    t = strip_accents(text.lower())
    t = re.sub(r"[^a-z0-9.,;?!\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()
