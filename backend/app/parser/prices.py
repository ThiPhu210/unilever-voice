"""Đọc giá SKU trong câu chốt đơn: "65 nghìn đồng", "65k", "65.000đ", "sáu mươi lăm nghìn",
"mười lăm nghìn", "một trăm hai mươi nghìn", "sáu mươi lăm nghìn rưỡi". Trả về VND (số nguyên).
Chỉ nhận là giá khi có đơn vị tiền (nghìn/ngàn/k/đồng/triệu) hoặc là số >= 1000,
để không nhầm với số lượng ("2 omo 800g, 1 clear ...")."""
import re
from .numbers import parse_number, DIGITS

THOUSAND = {"nghin", "ngan", "ng", "k", "nghìn", "ngàn"}
MILLION = {"trieu", "tr"}
CURRENCY = {"dong", "d", "vnd", "viet nam dong"}
UNITS = THOUSAND | MILLION | CURRENCY
NUM_TOKEN = re.compile(r"^(\d+(?:[.,]\d+)?)([a-z]*)$")
GROUPED = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")  # 65.000 / 1,250,000

# ASR hay nghe "92k" thành "92Kg" (k -> kg). Chỉ dùng khi NGỮ CẢNH chắc chắn là vị trí giá (kg_as_k=True).
KG_AS_K = {"kg", "ky", "ki"}

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


def _spoken_digits(toks: list[str], i: int) -> tuple[int, int] | None:
    """Giá đọc từng chữ số, không có "mươi": "bảy bảy ngàn" = 77k, "một trăm hai sáu ngàn" = 126k, "tám ba nghìn" = 83k.
    Chỉ nhận khi ngay sau là nghìn/ngàn/triệu (đơn vị giá) nên không nhầm với số lượng."""
    n, j, hund = len(toks), i, 0
    if j + 1 < n and toks[j] in DIGITS and toks[j + 1] == "tram":
        hund, j = DIGITS[toks[j]] * 100, j + 2
    if j + 2 < n and toks[j] in DIGITS and toks[j + 1] in DIGITS and toks[j] != "khong" and toks[j + 2] in THOUSAND | MILLION:
        return hund + DIGITS[toks[j]] * 10 + DIGITS[toks[j + 1]], j + 2
    return None


def _tam_la_tram(toks: list[str], i: int) -> list[str]:
    """ASR nghe "trăm" thành "tăm" (-> 'tam' = tám): "hai tăm mười bảy ngàn" = 217k, không phải "hai, tám mươi bảy".
    Chỉ trong ngữ cảnh GIÁ: số đơn + "tam" + (mười/chục/lẻ/chữ số) và cả cụm kết thúc bằng nghìn/ngàn/triệu."""
    n = len(toks)
    end = next((k for k in range(i, min(n, i + 8)) if toks[k] in THOUSAND | MILLION), None)
    if end is None:
        return toks
    out = list(toks)
    for k in range(i + 1, end):
        if toks[k] == "tam" and toks[k - 1] in DIGITS and toks[k + 1] in {"muoi", "chuc", "le", "linh", *DIGITS}:
            out[k] = "tram"
    return out


def _small(t: str) -> int | None:
    """Số 0-99 viết bằng chữ số ("5", "50") hoặc một chữ số đọc bằng chữ ("năm")."""
    if re.fullmatch(r"\d{1,2}", t):
        return int(t)
    return DIGITS.get(t)


def _mixed_hundreds(toks: list[str], i: int) -> tuple[int, int] | None:
    """Giá đọc LẪN chữ số và chữ ("2 trăm lẻ 1 ngàn", "3 trăm 50 nghìn", "hai trăm lẻ 1 ngàn") = 201k / 350k.
    Bộ nhận dạng của HĐH (Google/Siri) hay trả số theo kiểu này. Chỉ nhận khi CÓ ÍT NHẤT MỘT token số (cụm toàn chữ đã có
    nhánh parse_number) và ngay sau là nghìn/ngàn/triệu. Trả về (giá trị trước đơn vị, vị trí token đơn vị)."""
    n = len(toks)
    if i + 1 >= n or toks[i + 1] != "tram":
        return None
    h = _small(toks[i])
    if h is None or not 1 <= h <= 9:
        return None
    numeric, value, j = toks[i].isdigit(), h * 100, i + 2
    if j < n and toks[j] in ("le", "linh"):                  # "2 trăm lẻ 1": chỉ nhận một chữ số 1-9
        j += 1
        u = _small(toks[j]) if j < n else None
        if u is None or not 1 <= u <= 9:
            return None
        numeric, value, j = numeric or toks[j].isdigit(), value + u, j + 1
    elif j < n and re.fullmatch(r"\d{1,2}", toks[j]) and int(toks[j]) >= 1:     # "3 trăm 50" / "2 trăm 1"
        numeric, value, j = True, value + int(toks[j]), j + 1
    elif j < n and (p := parse_number(toks, j)) and 1 <= p[0] < 100:       # "2 trăm mười" / "3 trăm hai mươi lăm"
        value, j = value + p[0], p[1]
    if not numeric or j >= n or toks[j] not in THOUSAND | MILLION:
        return None
    return value, j


def parse_price(toks: list[str], i: int, kg_as_k: bool = False) -> tuple[int, int] | None:
    """Thử đọc giá tại vị trí i. Trả về (vnd, vị_trí_kế_tiếp) hoặc None.
    kg_as_k=True: coi "92Kg" (số nguyên 1-3 chữ số + kg/ky/ki) là "92k" = 92.000đ."""
    n = len(toks)
    if i >= n:  # hết câu ngay sau dấu phẩy / chữ "giá" -> không có gì để đọc
        return None
    t = toks[i]
    if (mx := _mixed_hundreds(toks, i)) is not None:
        v, j = mx
        unit, j = toks[j], j + 1
        if unit in THOUSAND:
            value = v * 1000
            extra, j = _tail_after_thousand(toks, j)
            value += extra
        else:
            value = v * 1_000_000
        return value, _skip_currency(toks, j)
    m = NUM_TOKEN.match(t)
    if m:
        num, suffix = m.groups()
        j = i + 1
        unit = suffix or None
        if kg_as_k and unit in KG_AS_K and re.fullmatch(r"\d{1,3}", num):
            unit = "k"
        if unit is not None and unit not in UNITS:
            return None
        if unit is None and j < n and toks[j] in UNITS:
            unit, j = toks[j], j + 1
        if GROUPED.match(num):
            if unit in THOUSAND | MILLION:
                return None
            value = int(re.sub(r"[.,]", "", num))
        elif unit in (None, *CURRENCY) and re.fullmatch(r"\d{3}0[.,]000", num):
            # Google ghi "hai trăm lẻ một ngàn" thành "2010.000đ" (thừa một số 0 trước ".000"): đọc lại là 201.000đ.
            # Chỉ đúng dạng 3 chữ số + "0" + ".000"; giá triệu hợp lệ ("2.010.000") đã đi nhánh GROUPED ở trên.
            value = int(num[:3]) * 1000
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
        if p and p[1] < n and toks[p[1]] in THOUSAND | MILLION:
            v, j = p
        elif (fixed := _tam_la_tram(toks, i)) is not toks and (p2 := parse_number(fixed, i)) and p2[1] < n and fixed[p2[1]] in THOUSAND | MILLION:
            v, j = p2
        else:
            p = _spoken_digits(toks, i)
            if not p:
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