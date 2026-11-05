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
    # Chỉ nối khi dung tích KẾT THÚC dòng hàng (sau nó là dấu câu/hết câu): "BAEU 3 .8kg, dạ 52k" -> "3.8kg".
    # Nếu sau nó còn chữ ("1 .5Kg BS ngừa sâu răng") thì "1" là số lượng, ".5Kg" là rác của ASR -> KHÔNG nối.
    t = re.sub(r"(\d)\s+([.,])(\d+(?:kg|ky|ki|g|gr|gam|gram|ml|l|lit|lt))(?=\s*(?:[,;.?!]|$))", r"\1\2\3", t)
    return re.sub(r"\s+", " ", t).strip()