import re
from .normalize import normalize

TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)?[a-z]*|[a-z]+|[,;]")
SIZE_RE = re.compile(r"^(\d+(?:[.,]\d+)?)(kg|ky|ki|g|gr|gam|gram|ml|l|lit|lt)$")
SIZE_UNIT_MAP = {
    "kg": "kg", "ky": "kg", "ki": "kg",
    "g": "g", "gr": "g", "gam": "g", "gram": "g",
    "ml": "ml", "l": "l", "lit": "l", "lt": "l",
}
NUM_RE = re.compile(r"^\d+(?:[.,]\d+)?$")


def size_norm(num: str, unit: str) -> str:
    return f"{str(num).replace(',', '.')}{SIZE_UNIT_MAP[unit]}"


def canon_tokens(text: str) -> list[str]:
    """Token hóa + gộp 'số + đơn vị' thành size chuẩn (800g, 3.2kg, 1.6l)."""
    toks = TOKEN_RE.findall(normalize(text))
    out, i = [], 0
    while i < len(toks):
        t = toks[i]
        m = SIZE_RE.match(t)
        if m:
            out.append(size_norm(m.group(1), m.group(2)))
            i += 1
        elif NUM_RE.match(t) and i + 1 < len(toks) and toks[i + 1] in SIZE_UNIT_MAP:
            out.append(size_norm(t, toks[i + 1]))
            i += 2
        else:
            out.append(t)
            i += 1
    return out
