import re
import unicodedata


def strip_accents(s: str) -> str:
    s = s.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")

def normalize(text: str) -> str:
    t = strip_accents(text.lower())
    t = re.sub(r"[^a-z0-9.,;?!\s]", " ", t)
    t = re.sub(r"(\d)\s+([.,])\s*(\d{3})(?!\d)", r"\1\2\3", t)
    # ASR hay chèn khoảng trắng trước dấu thập phân của dung tích: "3 .8kg" -> "3.8kg"
    t = re.sub(r"(\d)\s+([.,])(\d+(?:kg|ky|ki|g|gr|gam|gram|ml|l|lit|lt)\b)", r"\1\2\3", t)
    return re.sub(r"\s+", " ", t).strip()