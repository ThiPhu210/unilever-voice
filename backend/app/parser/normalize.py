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


# Dung tích thập phân bị ASR tách rời cả đơn vị: "3 ,8 ki" / "3,8 ki" / "3 .8 kg" -> "3.8kg".
# Vẫn áp dụng kiểm tra "số lượng" ở trên (đầu câu / sau dấu câu / sau giá-dung tích thì KHÔNG nối).
_SPLIT_SIZE_SP = re.compile(
    r"(?<![\d.,])(\d+)\s*([.,])(\d+)\s+(kg|ky|ki|g|gr|gam|gram|ml|l|lit|lt)(?![a-z])"
)


def _repeats_later(m: re.Match, d: str, x: str, unit: str) -> bool:
    """Cùng dung tích "d.x<unit>" lặp lại phía sau TRONG CÙNG CÂU?
    Có -> số đầu dòng không phải số lượng mà là dung tích bị ASR đọc đè lên số lượng
    ("3 .1KG, COMFORT ... 3 .1KG, GIÁ 92K": số lượng thật bị rớt, dòng được giả định SL=1 và đánh dấu cần xác nhận).
    Không -> số đầu dòng là số lượng còn ".xL" là rác chèn sau nó ("1 .1L, COMFORT ... 3 .1Kg")."""
    base = m.end()
    rest = re.split(r"(?<!\d)[?!]|\.(?=\s|$)", m.string[base:], maxsplit=1)[0]
    u = "(?:kg|ky|ki)" if unit in ("kg", "ky", "ki") else re.escape(unit)
    pat = rf"(?<![\d.,]){re.escape(d)}\s*[.,]\s*{re.escape(x)}\s*{u}(?![a-z])"
    # Chỉ tính bản lặp nằm GIỮA TÊN HÀNG. Bản lặp đứng ở vị trí số lượng (đầu dòng sau, sau một giá) là rác của dòng kế
    # ("1 .2L, A ... 92k 1 .2L, B ...") nên không được tính.
    return any(not _QTY_CONTEXT.search(m.string[:base + r.start()]) for r in re.finditer(pat, rest))


def _join_size_sp(m: re.Match) -> str:
    d, x, unit = m.group(1), m.group(3), m.group(4)
    if _QTY_CONTEXT.search(m.string[:m.start()]) and not _repeats_later(m, d, x, unit):
        return m.group(0)
    return f"{d}.{x}{unit}"


def _join_size(m: re.Match) -> str:
    d, x, unit = m.group(1), *re.fullmatch(r"(\d+)([a-z]+)", m.group(3)).groups()
    if _QTY_CONTEXT.search(m.string[:m.start()]) and not _repeats_later(m, d, x, unit):
        return m.group(0)
    return m.group(1) + m.group(2) + m.group(3)


def normalize(text: str) -> str:
    t = strip_accents(text.lower())
    # Nhãn người nói ở đầu câu ("SA: 1 .1L, ..." / "Khách: ...") không phải tên hàng; bỏ trước khi xoá dấu hai chấm,
    # nếu không "sa" đứng trước số lượng và làm mất ngữ cảnh "số đầu câu" của bước nối dung tích bên dưới.
    t = re.sub(r"(?m)(^|[.?!]\s+)(?:sa|ba|khach|kh)\s*:\s*", r"\1", t)
    t = re.sub(r"[^a-z0-9.,;?!\s]", " ", t)
    # Model tiếng Việt viết đơn vị theo âm ("chín ki lô gam", "ba trăm mi li lít", "ba phẩy tám ki") -> đơn vị chuẩn.
    # (Brand đọc theo âm KHÔNG thay ở đây: xem brands.py, brand được nạp thành alias SKU trong Catalog.)
    from .brands import canon_units
    t = canon_units(t)
    # ASR nghe "92k" thành "92Khz"/"92kz" (k + hz): trong câu chốt đơn không có đơn vị tần số nào -> đọc lại là "92k".
    t = re.sub(r"(?<![\d.,])(\d{1,3})\s*(?:khz|kz)\b", r"\1k", t)
    t = re.sub(r"(\d)\s+([.,])\s*(\d{3})(?!\d)", r"\1\2\3", t)
    # ASR hay chèn khoảng trắng trước dấu thập phân của dung tích: "3 .8kg" -> "3.8kg"
    # Chỉ nối khi dung tích KẾT THÚC dòng hàng (sau nó là dấu câu/hết câu) VÀ số đứng trước KHÔNG phải số lượng.
    # Số lượng nằm ở đầu câu, sau dấu phẩy/chấm, hoặc ngay sau một giá/dung tích ("92kg 2 .2L, HAZERLIN"):
    # khi đó ".2L" là rác ASR chèn sau số lượng -> KHÔNG nối (nếu nối sẽ thành "2.2l" và mất số lượng).
    t = _SPLIT_SIZE.sub(_join_size, t)
    t = _SPLIT_SIZE_SP.sub(_join_size_sp, t)
    return re.sub(r"\s+", " ", t).strip()