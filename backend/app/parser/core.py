"""Phát hiện câu chốt đơn + tách (số lượng, SKU) + dò phản hồi khách.
Không dùng LLM: chỉ regex + fuzzy matching.
"""
import re
from rapidfuzz import fuzz
from .normalize import normalize
from .numbers import parse_number
from .tokens import TOKEN_RE, SIZE_RE, SIZE_UNIT_MAP, size_norm
from .catalog import Catalog
from .prices import parse_price, price_suspect
from .confirm_words import YES_RE, NO_RE, YES_OVERRIDE_RE, CONFIRM_CUT

SEPARATORS = {",", ";", "va", "voi", "cong", "them"}
QTY_UNITS = {"chai", "goi", "lon", "hop", "thung", "tuyp", "tui", "loc", "cai",
             "bich", "hu", "bo", "lo", "can", "bao", "vi"}
STOP_NAME = {"a", "nhe", "nha", "ha", "da", "vang", "di", "cua", "loai", "hang",
             "cai", "x", "la", "don", "gia", "moi", "tien", "dong", "vnd", "d"}
LEAD_STRIP = {"don", "luon", "cho", "nhe", "la", "gom", "vay"}
AMBIGUOUS = {"nam", "sau"}  # vừa là số vừa là từ thường (clear nam, ...)
BATH_PREV = {"sua", "phong", "dau", "bon", "gel"}  # "sữa/xà phòng/dầu tắm": 'tam' ở đây là TẮM, không phải số TÁM
CLOSE_PREV = {"minh", "vay", "em", "nhe", "la", "se", "luon", "anh", "chi", "con"}
SENT_END = re.compile(r"[.?!](?=\s|$)")
# ASR hay nghe "chốt" thành những từ này (fuzz.ratio với "chot" < 75 nên không tự bắt được).
# Là từ thật trong tiếng Việt ("cháu") nên chỉ nhận khi có ngữ cảnh câu chốt.
ASR_CHOT_VARIANTS = {"chau", "chaut", "chao"}
# "con chau" = con cháu -> không coi "con" là ngữ cảnh cho nhóm biến thể này
CLOSE_PREV_STRICT = CLOSE_PREV - {"con"}


def find_closings(text: str) -> list[dict]:
    """Tìm các vị trí 'chốt' (chịu lỗi ASR như chót/chốc/chấu) trong text đã normalize."""
    hits = []
    for m in re.finditer(r"\b[a-z]{3,5}\b", text):
        tok = m.group()
        exact = tok == "chot"
        variant = tok in ASR_CHOT_VARIANTS
        if not exact and not variant and fuzz.ratio(tok, "chot") < 60:
            continue
        before = text[max(0, m.start() - 60):m.start()]
        prev = before.split()[-1] if before.split() else ""
        if variant:
            ok = prev in CLOSE_PREV_STRICT or "cam on" in before
        else:
            ok = exact or prev in CLOSE_PREV or "cam on" in before
        if ok:
            hits.append(m)
    out = []
    for k, m in enumerate(hits):
        end_limit = hits[k + 1].start() if k + 1 < len(hits) else len(text)
        out.append({"tail": text[m.end():end_limit].strip(), "start": m.start()})
    return out


# Số thứ tự đầu dòng do ASR tự thêm: "chốt 1. Omo 800g, 2. Clear ..." -> dấu chấm sau "1" KHÔNG phải hết câu.
LIST_NO = re.compile(r"(^|[,;]\s*)(\d{1,2})\.(?=\s)")


def split_tail(tail: str) -> tuple[str, str]:
    """Tách phần liệt kê SKU và phần còn lại (phản hồi của khách)."""
    tail = re.sub(r"^[\s.,;]+(?=\d{1,2}\.\s)", "", tail)   # "chốt. 1. omo ..." -> bỏ dấu câu thừa trước số thứ tự
    tail = LIST_NO.sub(r"\1\2", tail)
    m = SENT_END.search(tail)
    if m:
        return tail[:m.start()], tail[m.end():]
    c = CONFIRM_CUT.search(tail)
    if c:
        return tail[:c.start()], tail[c.start():]
    return tail, ""


def detect_customer_confirm(after: str) -> tuple[str, str | None]:
    after = " ".join(after.split()[:25])
    after = YES_OVERRIDE_RE.sub("ok", after)  # "không sao", "thôi được", "cũng được"... = đồng ý
    y, n = YES_RE.search(after), NO_RE.search(after)
    if y and (not n or y.start() < n.start()):
        return "yes", y.group()
    if n:
        return "no", n.group()
    return "none", None


PRICE_LEAD = {"gia", "da", "don", "la"}  # "giá", "đơn giá là" đứng trước con số giá; "da" = ASR nghe "giá" thành "dạ"


def _like_gia(t: str) -> bool:
    """ASR nghe 'giá' thành 'dạ', 'dạm', 'dả', 'giạ'... -> token ngắn, toàn chữ, gần giống 'gia'/'da'."""
    return t.isalpha() and len(t) <= 4 and max(fuzz.ratio(t, "gia"), fuzz.ratio(t, "da")) >= 66


def _skip_price_lead(toks: list[str], j: int) -> int:
    while j < len(toks) and toks[j] in PRICE_LEAD:
        j += 1
    # tiền tố nghe sai ("dạm 103k"): chỉ bỏ qua khi NGAY SAU đó thật sự là một mức giá, để không nuốt nhầm tên SKU
    k = j
    while k < len(toks) and k - j < 2 and _like_gia(toks[k]):
        k += 1
    if k > j and parse_price(toks, k):
        return k
    return j


def _price_follows(toks: list[str], j: int) -> bool:
    """Sau toks[j-1] có dấu phẩy rồi tới một mức giá riêng ('..., dạm 86k') không?"""
    return j < len(toks) and toks[j] in {",", ";"} and parse_price(toks, _skip_price_lead(toks, j + 1)) is not None


def _starts_item(toks: list[str], i: int) -> bool:
    """toks[i] là 'va'/'voi': sau nó có phải số lượng của một dòng hàng mới không?"""
    j = i + 1
    while j < len(toks) and toks[j] in LEAD_STRIP:
        j += 1
    return j < len(toks) and parse_number(toks, j) is not None


def scan_segments(text: str) -> list[tuple[int | None, list[str], int | None]]:
    toks = TOKEN_RE.findall(text)
    segs, qty, name, price = [], None, [], None

    def flush():
        nonlocal qty, name, price
        words = [t for t in name if t not in STOP_NAME]
        if words:
            segs.append((qty, words, price))
        qty, name, price = None, [], None

    i, n = 0, len(toks)
    while i < n:
        t = toks[i]
        if t in SEPARATORS:
            if t in {",", ";"} and name and price is None:
                pr = parse_price(toks, _skip_price_lead(toks, i + 1))  # "800g, giá 65k đồng": ASR chèn dấu phẩy giữa tên SKU và giá
                if pr:
                    price, i = pr
                    continue
            if t in {"va", "voi"} and name and price is None and not _starts_item(toks, i):
                name.append(t); i += 1; continue  # "và" nằm trong tên SKU, không phải ranh giới
            flush(); i += 1; continue
        m = SIZE_RE.match(t)
        if m:
            name.append(size_norm(m.group(1), m.group(2))); i += 1; continue
        if t in LEAD_STRIP and not name and qty is None:
            i += 1; continue
        if name and price is None and re.fullmatch(r"\d+", t) and _price_follows(toks, i + 1):
            name.append(t); i += 1; continue  # "bảo vệ 123, giá 48k" / "viên rửa chén 1401, giá 86k": số đứng cuối TÊN, giá nằm sau dấu phẩy
        if not name and qty is None and segs and segs[-1][2] is None:
            k = _skip_price_lead(toks, i)  # giá "mồ côi" ngay sau một dòng đã đóng: gắn lại vào dòng trước, không tạo dòng mới
            pr = parse_price(toks, k) if (k > i or not re.fullmatch(r"\d+", t)) else None
            if pr:
                segs[-1] = (segs[-1][0], segs[-1][1], pr[0]); i = pr[1]
                continue
        if name and price is None:
            pr = parse_price(toks, i)  # "... 65 nghìn đồng" ngay sau tên SKU
            if pr:
                price, i = pr
                continue
        if t == "tam" and name and name[-1] in BATH_PREV:
            name.append(t); i += 1; continue
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


def _build_order(items_text: str, after: str, catalog: Catalog, source: str = "text") -> dict | None:
    """Dựng một đơn từ phần liệt kê SKU + phần phản hồi của khách.
    source: 'customer_turn' (phản hồi lấy từ lượt KHÁCH), 'no_customer_turn' (chỉ SA nói -> chưa rõ) hoặc 'text' (chưa tách người nói)."""
    items = []
    for qty, words, price in scan_segments(items_text):
        res = catalog.match(words)
        assumed = qty is None
        q = 1 if assumed else qty
        need = res["conf"] < 0.85 or assumed or q == 0 or q > 200 or price_suspect(price)
        items.append({
            "raw": " ".join(words), "qty": q, "qty_assumed": assumed,
            "price": price, "price_missing": price is None,
            **res, "need_confirm": need,
        })
    if not items:
        return None
    confirm, evidence = detect_customer_confirm(after)
    return {
        "closing_text": items_text.strip(),
        "items": items,
        "customer_confirm": confirm,
        "customer_evidence": evidence,
        "confirm_source": source,
        "needs_review": any(i["need_confirm"] for i in items),
        "missing_price": any(i["price_missing"] for i in items),
    }


def _orders_from_turns(turns: list[dict], catalog: Catalog) -> list[dict]:
    """Câu chốt chỉ tìm trong lượt SA; phản hồi lấy từ lượt KHÁCH ngay sau đó.
    Không có lượt khách liền sau -> "chưa rõ" (lời SA như "dạ ok em" KHÔNG được tính là khách đồng ý)."""
    orders = []
    for k, t in enumerate(turns):
        if t.get("speaker") != "sa":
            continue
        closings = find_closings(normalize(t.get("text", "")))
        if not closings:
            continue
        cust, j = [], k + 1
        while j < len(turns) and turns[j].get("speaker") == "customer":
            cust.append(turns[j].get("text", ""))
            j += 1
        cust_norm = normalize(" ".join(cust))
        for idx, c in enumerate(closings):
            items_text, _sa_tail = split_tail(c["tail"])  # phần đuôi là lời SA -> bỏ, không dùng để đoán khách
            if idx == len(closings) - 1 and cust_norm:
                after, source = cust_norm, "customer_turn"
            else:
                after, source = "", "no_customer_turn"
            o = _build_order(items_text, after, catalog, source)
            if o:
                orders.append(o)
    return orders


def parse_transcript(text: str, catalog: Catalog, turns: list[dict] | None = None) -> dict:
    orders = _orders_from_turns(turns, catalog) if turns else []
    if not orders:  # không có turns, hoặc không thấy câu chốt trong lời SA -> quay về toàn văn
        for c in find_closings(normalize(text)):
            items_text, after = split_tail(c["tail"])
            o = _build_order(items_text, after, catalog)
            if o:
                orders.append(o)
    return {"closing_detected": bool(orders), "orders": orders}