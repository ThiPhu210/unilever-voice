"""Đọc số tiếng Việt (không dấu) đến hàng trăm: 'hai muoi lam' -> 25."""
import re

DIGITS = {
    "khong": 0, "mot": 1, "hai": 2, "ba": 3, "bon": 4, "tu": 4,
    "nam": 5, "lam": 5, "sau": 6, "bay": 7, "tam": 8, "chin": 9,
}


def parse_number(tokens: list[str], i: int):
    """Trả về (giá_trị, vị_trí_token_kế_tiếp) hoặc None."""
    t = tokens[i]
    if re.fullmatch(r"\d+", t):
        return int(t), i + 1
    if t not in DIGITS and t not in ("muoi", "tram"):
        return None

    value, pending = 0, None
    can_unit, seen_tens, seen_hund = True, False, False
    consumed, j = False, i
    while j < len(tokens):
        t = tokens[j]
        if t in DIGITS:
            if pending is not None or not can_unit:
                break
            pending, can_unit = DIGITS[t], False
        elif t == "tram":
            if pending is None or seen_hund or seen_tens:
                break
            value += pending * 100
            pending, seen_hund, can_unit = None, True, True
        elif t == "muoi":
            if seen_tens:
                break
            value += (pending or 1) * 10
            pending, seen_tens, can_unit = None, True, True
        elif t in ("le", "linh") and seen_hund and pending is None and not seen_tens:
            can_unit = True
        else:
            break
        consumed = True
        j += 1
    if not consumed:
        return None
    if pending:
        value += pending
    return value, j
