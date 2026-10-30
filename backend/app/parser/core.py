"""Phát hiện câu chốt đơn + tách (số lượng, SKU) + dò phản hồi khách.
Không dùng LLM: chỉ regex + fuzzy matching.
"""
import re
from rapidfuzz import fuzz
from .normalize import normalize
from .numbers import parse_number
from .tokens import TOKEN_RE, SIZE_RE, SIZE_UNIT_MAP, size_norm
from .catalog import Catalog

SEPARATORS = {",", ";", "va", "voi", "cong", "them"}
QTY_UNITS = {"chai", "goi", "lon", "hop", "thung", "tuyp", "tui", "loc", "cai",
             "bich", "hu", "bo", "lo", "can", "bao", "vi"}
STOP_NAME = {"a", "nhe", "nha", "ha", "da", "vang", "di", "cua", "loai", "hang",
             "cai", "x", "la", "don"}
LEAD_STRIP = {"don", "luon", "cho", "nhe", "la", "gom", "vay"}
AMBIGUOUS = {"nam", "sau"}  # vừa là số vừa là từ thường (clear nam, ...)
CLOSE_PREV = {"minh", "vay", "em", "nhe", "la", "se", "luon", "anh", "chi", "con"}
CONFIRM_CUT = re.compile(r"\b(da dung|dung roi|duoc roi|ok|oke|thoi)\b")
YES_RE = re.compile(r"\b(dung roi|duoc roi|ok|oke|okay|dong y|vang|u|uh|uhm|dung|chuan|duoc|lay)\b")
NO_RE = re.compile(r"\b(thoi|khong|ko|chua|de (anh |chi |co |chu |minh )?(suy nghi|xem)|khoan|huy|bo bot)\b")
SENT_END = re.compile(r"[.?!](?=\s|$)")


def find_closings(text: str) -> list[dict]:
    """Tìm các vị trí 'chốt' (chịu lỗi ASR như chót/chốc) trong text đã normalize."""
    hits = []
    for m in re.finditer(r"\b[a-z]{3,5}\b", text):
        tok = m.group()
        exact = tok == "chot"
        if not exact and fuzz.ratio(tok, "chot") < 75:
            continue
        before = text[max(0, m.start() - 60):m.start()]
        prev = before.split()[-1] if before.split() else ""
        if exact or prev in CLOSE_PREV or "cam on" in before:
            hits.append(m)
    out = []
    for k, m in enumerate(hits):
        end_limit = hits[k + 1].start() if k + 1 < len(hits) else len(text)
        out.append({"tail": text[m.end():end_limit].strip(), "start": m.start()})
    return out


def split_tail(tail: str) -> tuple[str, str]:
    """Tách phần liệt kê SKU và phần còn lại (phản hồi của khách)."""
    m = SENT_END.search(tail)
    if m:
        return tail[:m.start()], tail[m.end():]
    c = CONFIRM_CUT.search(tail)
    if c:
        return tail[:c.start()], tail[c.start():]
    return tail, ""


def detect_customer_confirm(after: str) -> tuple[str, str | None]:
    after = " ".join(after.split()[:25])
    after = re.sub(r"\bkhong (sao|van de|co gi)\b", "ok", after)
    y, n = YES_RE.search(after), NO_RE.search(after)
    if y and (not n or y.start() < n.start()):
        return "yes", y.group()
    if n:
        return "no", n.group()
    return "none", None


def scan_segments(text: str) -> list[tuple[int | None, list[str]]]:
    toks = TOKEN_RE.findall(text)
    segs, qty, name = [], None, []

    def flush():
        nonlocal qty, name
        words = [t for t in name if t not in STOP_NAME]
        if words:
            segs.append((qty, words))
        qty, name = None, []

    i, n = 0, len(toks)
    while i < n:
        t = toks[i]
        if t in SEPARATORS:
            flush(); i += 1; continue
        m = SIZE_RE.match(t)
        if m:
            name.append(size_norm(m.group(1), m.group(2))); i += 1; continue
        if t in LEAD_STRIP and not name and qty is None:
            i += 1; continue
        if not (t in AMBIGUOUS and name):
            p = parse_number(toks, i)
            if p:
                v, j = p
                if j < n and toks[j] in SIZE_UNIT_MAP:  # "tam tram gam" = 800g
                    name.append(size_norm(str(v), toks[j])); i = j + 1; continue
                if name or qty is not None:
                    flush()
                qty, i = v, j
                if i < n and toks[i] in QTY_UNITS:
                    i += 1
                continue
        name.append(t); i += 1
    flush()
    return segs


def parse_transcript(text: str, catalog: Catalog) -> dict:
    norm = normalize(text)
    orders = []
    for c in find_closings(norm):
        items_text, after = split_tail(c["tail"])
        items = []
        for qty, words in scan_segments(items_text):
            res = catalog.match(words)
            assumed = qty is None
            q = 1 if assumed else qty
            need = res["conf"] < 0.85 or assumed or q == 0 or q > 200
            items.append({
                "raw": " ".join(words), "qty": q, "qty_assumed": assumed,
                **res, "need_confirm": need,
            })
        if not items:
            continue
        confirm, evidence = detect_customer_confirm(after)
        orders.append({
            "closing_text": items_text.strip(),
            "items": items,
            "customer_confirm": confirm,
            "customer_evidence": evidence,
            "needs_review": any(i["need_confirm"] for i in items),
        })
    return {"closing_detected": bool(orders), "orders": orders}
