"""Tách đơn hàng từ transcript theo mẫu {số lượng} {sản phẩm} {giá} + dò phản hồi khách.
Không dùng LLM: chỉ regex + fuzzy matching. Không cần từ khoá "chốt".
"""
import re
from rapidfuzz import fuzz
from .normalize import normalize
from .numbers import parse_number
from .tokens import TOKEN_RE, SIZE_RE, SIZE_UNIT_MAP, size_norm
from .catalog import Catalog
from .prices import parse_price, price_suspect
from .confirm_words import YES_RE, NO_RE, YES_OVERRIDE_RE

SEPARATORS = {",", ";", "va", "voi", "cong", "them"}
QTY_UNITS = {"chai", "goi", "lon", "hop", "thung", "tuyp", "tui", "loc", "cai",
             "bich", "hu", "bo", "lo", "can", "bao", "vi"}
STOP_NAME = {"a", "nhe", "nha", "ha", "da", "vang", "di", "cua", "loai", "hang",
             "cai", "x", "la", "don", "gia", "moi", "tien", "dong", "vnd", "d"}
LEAD_STRIP = {"don", "luon", "cho", "nhe", "la", "gom", "vay"}
AMBIGUOUS = {"nam", "sau"}  # vừa là số vừa là từ thường (clear nam, ...)
BATH_PREV = {"sua", "phong", "dau", "bon", "gel"}  # "sữa/xà phòng/dầu tắm": 'tam' ở đây là TẮM, không phải số TÁM
SENT_END = re.compile(r"[.?!](?=\s|$)")
MIN_MATCH = 0.6   # độ khớp SKU tối thiểu, dưới mức này coi là câu nói thường, bỏ qua

# Số thứ tự đầu dòng do ASR tự thêm: "Omo 800g, 2. Clear ..." -> dấu chấm sau "2" KHÔNG phải hết câu.
LIST_NO = re.compile(r"(^|[,;]\s*)(\d{1,2})\.(?=\s)")


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
        if price is not None and t not in SEPARATORS and parse_number(toks, i) is None:
            flush()   # đã có giá -> kết thúc dòng hàng, chữ lan man phía sau không thuộc tên SKU
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


def _extract_items(text: str, catalog: Catalog) -> list[dict]:
    """Quét toàn văn, chỉ giữ dòng có ĐỦ số lượng + sản phẩm khớp catalog + giá."""
    text = LIST_NO.sub(r"\1\2", text)           # bỏ số thứ tự ASR tự thêm: "1. omo" -> "1 omo"
    items = []
    for sent in filter(str.strip, SENT_END.split(text)):
        for qty, words, price in scan_segments(sent):
            if qty is None or price is None:
                continue
            res = catalog.match(words)
            if res["conf"] < MIN_MATCH:
                continue
            need = res["conf"] < 0.85 or qty == 0 or qty > 200 or price_suspect(price)
            items.append({
                "raw": " ".join(words), "qty": qty, "qty_assumed": False,
                "price": price, "price_missing": False, **res, "need_confirm": need,
            })
    return items


def _make_order(items: list[dict], after: str, source: str) -> dict:
    confirm, evidence = detect_customer_confirm(after)
    return {
        "closing_text": "; ".join(f'{i["qty"]} {i["raw"]} {i["price"]}' for i in items),
        "items": items,
        "customer_confirm": confirm,
        "customer_evidence": evidence,
        "confirm_source": source,
        "needs_review": any(i["need_confirm"] for i in items),
        "missing_price": False,
    }


def _orders_from_turns(turns: list[dict], catalog: Catalog) -> list[dict]:
    """Mỗi lượt SA có dòng hàng -> 1 đơn; phản hồi lấy từ lượt KHÁCH ngay sau đó.
    Không có lượt khách liền sau -> "chưa rõ" (lời SA như "dạ ok em" KHÔNG được tính là khách đồng ý)."""
    orders = []
    for k, t in enumerate(turns):
        if t.get("speaker") != "sa":
            continue
        items = _extract_items(normalize(t.get("text", "")), catalog)
        if not items:
            continue
        cust, j = [], k + 1
        while j < len(turns) and turns[j].get("speaker") == "customer":
            cust.append(turns[j].get("text", ""))
            j += 1
        cust_norm = normalize(" ".join(cust))
        orders.append(_make_order(items, cust_norm, "customer_turn" if cust_norm else "no_customer_turn"))
    return orders


def parse_transcript(text: str, catalog: Catalog, turns: list[dict] | None = None) -> dict:
    orders = _orders_from_turns(turns, catalog) if turns else []
    if not orders:  # chưa tách người nói -> quét toàn văn, gom thành 1 đơn
        items = _extract_items(normalize(text), catalog)
        if items:
            orders = [_make_order(items, "", "text")]
    return {"closing_detected": bool(orders), "orders": orders}