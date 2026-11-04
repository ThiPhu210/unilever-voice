"""Đọc giá SKU trong câu chốt đơn: "65 nghìn đồng", "65k", "65.000đ", "sáu mươi lăm nghìn",
"mười lăm nghìn", "một trăm hai mươi nghìn", "sáu mươi lăm nghìn rưỡi". Trả về VND (số nguyên).
Chỉ nhận là giá khi có đơn vị tiền (nghìn/ngàn/k/đồng/triệu) hoặc là số >= 1000,
để không nhầm với số lượng ("2 omo 800g, 1 clear ...")."""
import re
from .numbers import parse_number

THOUSAND = {"nghin", "ngan", "ng", "k", "nghìn", "ngàn"}
MILLION = {"trieu", "tr"}
CURRENCY = {"dong", "d", "vnd", "viet nam dong"}
UNITS = THOUSAND | MILLION | CURRENCY
NUM_TOKEN = re.compile(r"^(\d+(?:[.,]\d+)?)([a-z]*)$")
GROUPED = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")  # 65.000 / 1,250,000

PRICE_MIN, PRICE_MAX = 500, 50_000_000


def _skip_currency(toks: list[str], j: int) -> int:
    while j < len(toks) and toks[j] in CURRENCY:
        j += 1
    return j


def _tail_after_thousand(toks: list[str], j: int) -> tuple[int, int]:
    """Phần lẻ sau 'nghìn': 'rưỡi' (+500) hoặc 'hai trăm năm mươi' (+250)."""
    if j < len(toks) and toks[j] == "ruoi":
        return 500, j + 1
    if j < len(toks):
        p = parse_number(toks, j)
        if p and 100 <= p[0] < 1000 and (p[0] % 10 == 0):
            return p[0], p[1]
    return 0, j


def parse_price(toks: list[str], i: int) -> tuple[int, int] | None:
    """Thử đọc giá tại vị trí i. Trả về (vnd, vị_trí_kế_tiếp) hoặc None."""
    n = len(toks)
    t = toks[i]
    m = NUM_TOKEN.match(t)
    if m:
        num, suffix = m.groups()
        j = i + 1
        unit = suffix or None
        if unit is not None and unit not in UNITS:
            return None
        if unit is None and j < n and toks[j] in UNITS:
            unit, j = toks[j], j + 1
        if GROUPED.match(num):
            if unit in THOUSAND | MILLION:
                return None
            value = int(re.sub(r"[.,]", "", num))
        else:
            value = float(num.replace(",", "."))
            if unit in THOUSAND:
                value *= 1000
                if float(num.replace(",", ".")).is_integer():  # "65 nghìn rưỡi" / "65 nghìn 500"
                    extra, j = _tail_after_thousand(toks, j)
                    value += extra
            elif unit in MILLION:
                value *= 1_000_000
            elif value < 1000:  # "65" hoặc "65 đồng": không đủ chắc là giá
                return None
        value = int(round(value))
    else:
        p = parse_number(toks, i)
        if not p or p[1] >= n or toks[p[1]] not in THOUSAND | MILLION:
            return None
        v, j = p
        unit, j = toks[j], j + 1
        if unit in THOUSAND:
            value = v * 1000
            extra, j = _tail_after_thousand(toks, j)
            value += extra
        else:
            value = v * 1_000_000
    j = _skip_currency(toks, j)
    return value, j


def price_suspect(price: int | None) -> bool:
    return price is not None and not (PRICE_MIN <= price <= PRICE_MAX)
