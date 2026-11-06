import re
import unicodedata


def strip_accents(s: str) -> str:
    s = s.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


_SPLIT_SIZE = re.compile(
    r"(?<![\d.,])(\d+)\s+([.,])(\d+(?:kg|ky|ki|g|gr|gam|gram|ml|l|lit|lt))(?=\s*(?:[,;.?!]|$))"
)
# Phần văn bản đứng trước con số: đầu chuỗi, dấu câu, hoặc một token số (giá/dung tích) -> con số là SỐ LƯỢNG.
_QTY_CONTEXT = re.compile(r"(?:^|[,;.?!]\s*|(?<![a-z])\d[0-9.,]*[a-z]*\s+)$")


def _join_size(m: re.Match) -> str:
    if _QTY_CONTEXT.search(m.string[:m.start()]):
        return m.group(0)
    return m.group(1) + m.group(2) + m.group(3)

def normalize(text: str) -> str:
    t = strip_accents(text.lower())
    t = re.sub(r"[^a-z0-9.,;?!\s]", " ", t)
    t = re.sub(r"(\d)\s+([.,])\s*(\d{3})(?!\d)", r"\1\2\3", t)
    # ASR hay chèn khoảng trắng trước dấu thập phân của dung tích: "3 .8kg" -> "3.8kg"
    # Chỉ nối khi dung tích KẾT THÚC dòng hàng (sau nó là dấu câu/hết câu) VÀ số đứng trước KHÔNG phải số lượng.
    # Số lượng nằm ở đầu câu, sau dấu phẩy/chấm, hoặc ngay sau một giá/dung tích ("92kg 2 .2L, HAZERLIN"):
    # khi đó ".2L" là rác ASR chèn sau số lượng -> KHÔNG nối (nếu nối sẽ thành "2.2l" và mất số lượng).
    t = _SPLIT_SIZE.sub(_join_size, t)
    return re.sub(r"\s+", " ", t).strip()