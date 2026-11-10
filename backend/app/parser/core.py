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
AMBIGUOUS = {"nam", "sau", "bon", "bun"}  # vừa là số vừa là từ thường (clear nam, bồn cầu, Pond's đọc "bon", ...)
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
    if k > j and parse_price(toks, k, kg_as_k=True):
        return k
    return j


def _price_follows(toks: list[str], j: int) -> bool:
    """Sau toks[j-1] có một mức giá riêng không? Có dấu phẩy ("..., dạm 86k") hoặc chữ dẫn giá không dấu phẩy
    ("bảo vệ 123 giá 48 nghìn")."""
    if j >= len(toks):
        return False
    comma = toks[j] in {",", ";"}
    k = _skip_price_lead(toks, j + 1 if comma else j)
    if not comma and k == j:   # không dấu phẩy và không có "giá/dạ" -> không đủ chắc
        return False
    return parse_price(toks, k, kg_as_k=True) is not None


def _starts_item(toks: list[str], i: int) -> bool:
    """toks[i] là 'va'/'voi': sau nó có phải số lượng của một dòng hàng mới không?"""
    j = i + 1
    while j < len(toks) and toks[j] in LEAD_STRIP:
        j += 1
    return j < len(toks) and parse_number(toks, j) is not None


KG_PRICE_RE = re.compile(r"\d{1,3}(?:kg|ky|ki)")


def _has_size(name: list[str]) -> bool:
    return any(SIZE_RE.match(w) for w in name)


def _kg_is_price(toks: list[str], k: int, name: list[str], after_comma: bool) -> bool:
    """toks[k] dạng "92kg": ASR nghe "92k" (giá) thành "92Kg" hay đây là dung tích thật ("Sữa tắm 1kg")?
    Là GIÁ khi: (1) ngay sau nó KHÔNG còn một mức giá khác (nếu còn thì nó là dung tích: "Omo, 3kg, giá 100k"), và
    (2) tên SKU đã "đủ": đã có dung tích, hoặc ngay trước là chữ "giá/dạ", hoặc (sau dấu phẩy) tên kết thúc bằng số
    ("Rửa chén 14 trong 1, 86Kg")."""
    if k >= len(toks) or not KG_PRICE_RE.fullmatch(toks[k]) or not name:
        return False
    j = k + 1
    if j < len(toks) and toks[j] in {",", ";"}:
        j += 1
    j = _skip_price_lead(toks, j)
    if j < len(toks) and parse_price(toks, j, kg_as_k=True):
        return False
    return _has_size(name) or name[-1] in PRICE_LEAD or (after_comma and name[-1].isdigit())


def _comma_in_name(toks: list[str], i: int, name: list[str]) -> bool:
    """ASR chèn dấu phẩy giữa tên SKU ("2 Hazeln, Sữa Tắm, Sữa Gạo Hoa Nhài 1kg, 80k"): tên chưa có dung tích và sau
    dấu phẩy là chữ (không phải số lượng/giá) -> đây không phải ranh giới dòng hàng, bỏ dấu phẩy, giữ tên + số lượng."""
    j = i + 1
    return (j < len(toks) and not _has_size(name)
            and toks[j] not in SEPARATORS and parse_number(toks, j) is None)


def scan_segments(text: str) -> list[tuple[int | None, list[str], int | None]]:
    toks = TOKEN_RE.findall(text)
    segs, qty, name, price = [], None, [], None

    def flush():
        nonlocal qty, name, price
        # Từ đệm ("dạ", "nhé", "giá"...) chỉ bỏ ở HAI ĐẦU tên: chữ "la" giữa "ga la si" (Galaxy) là một âm tiết của tên hàng.
        words = list(name)
        while words and words[0] in STOP_NAME:
            words.pop(0)
        while words and words[-1] in STOP_NAME:
            words.pop()
        if words:
            segs.append((qty, words, price))
        qty, name, price = None, [], None

    i, n = 0, len(toks)
    while i < n:
        t = toks[i]
        if price is not None and t not in SEPARATORS and parse_number(toks, i) is None:
            flush()   # đã có giá -> kết thúc dòng hàng, chữ lan man phía sau không thuộc tên SKU
        if t in SEPARATORS:
            if t in {",", ";"} and not name and qty is not None:
                i += 1; continue  # "1 .2L, COMFORT ...": dấu phẩy ngay sau số lượng (+ rác) -> GIỮ số lượng, đừng flush
            if t in {",", ";"} and name and price is None:
                k = _skip_price_lead(toks, i + 1)  # "800g, giá 65k đồng": ASR chèn dấu phẩy giữa tên SKU và giá
                pr = parse_price(toks, k, kg_as_k=(k > i + 1 or _kg_is_price(toks, k, name, True)))  # "..., 92Kg" = 92k
                if pr:
                    price, i = pr
                    continue
                if _comma_in_name(toks, i, name):
                    i += 1; continue
            if t in {"va", "voi"} and not name and qty is not None:
                name.append(t); i += 1; continue  # "2 va so lin ...": ngay sau số lượng là tên hàng (brand "Vaseline" đọc "va so lin"), không phải liên từ "và"
            if t in {"va", "voi"} and name and price is None and not _starts_item(toks, i):
                name.append(t); i += 1; continue  # "và" nằm trong tên SKU, không phải ranh giới
            flush(); i += 1; continue
        m = SIZE_RE.match(t)
        if m:
            nxt = toks[i + 1] if i + 1 < n else None
            if qty is not None and not name and nxt in {",", ";", None}:
                i += 1; continue  # "2 .2L, HAZERLIN": dung tích rác ASR chèn ngay sau số lượng -> bỏ
            if price is None and name and _kg_is_price(toks, i, name, False):
                pr = parse_price(toks, i, kg_as_k=True)  # "... 28g 7Kg 2 ...": ASR bỏ mất dấu phẩy, "7Kg" = 7k
                if pr:
                    price, i = pr
                    continue
            name.append(size_norm(m.group(1), m.group(2))); i += 1; continue
        if t in LEAD_STRIP and not name and qty is None:
            i += 1; continue
        if (name and price is None and re.fullmatch(r"\d+", t) and i + 2 < n
                and toks[i + 1] == "trong" and re.fullmatch(r"\d+", toks[i + 2])):
            name.extend([t, "trong", toks[i + 2]]); i += 3; continue  # "rửa chén 14 trong 1": số nằm trong TÊN, không phải số lượng
        if name and price is None and re.fullmatch(r"\d+", t) and _price_follows(toks, i + 1):
            name.append(t); i += 1; continue  # "bảo vệ 123, giá 48k" / "viên rửa chén 1401, giá 86k": số đứng cuối TÊN, giá nằm sau dấu phẩy
        if not name and qty is None and segs and segs[-1][2] is None:
            k = _skip_price_lead(toks, i)  # giá "mồ côi" ngay sau một dòng đã đóng: gắn lại vào dòng trước, không tạo dòng mới
            pr = parse_price(toks, k, kg_as_k=k > i) if (k > i or not re.fullmatch(r"\d+", t)) else None
            if pr:
                segs[-1] = (segs[-1][0], segs[-1][1], pr[0]); i = pr[1]
                continue
        if name and price is None:
            pr = parse_price(toks, i)  # "... 65 nghìn đồng" ngay sau tên SKU
            if pr:
                price, i = pr
                continue
        if t == "tam" and name and (
                name[-1] in BATH_PREV   # "sữa/dầu tắm"
                # ASR nghe sai chữ đứng trước ("Sỡ Tắm Gạo"): tên chưa có giá, token trước là chữ -> "tắm" là một phần của tên.
                # Giữ nguyên "tám trăm gam" / "tám mươi" (số đọc thành chữ).
                or (price is None and not SIZE_RE.match(name[-1])
                    and not (i + 1 < n and (toks[i + 1] in {"tram", "muoi", "chuc"} or toks[i + 1] in SIZE_UNIT_MAP)))):
            name.append(t); i += 1; continue
        # Từ nhập nhằng KHÔNG phải số khi đang dở tên hàng, hoặc đứng ngay sau số lượng ("hai bon kem ..." = 2 x Pond's). Đã có giá -> dòng đã đóng, đây là số lượng dòng kế.
        # ...trừ khi ngay sau là "trăm/mươi/chục": "bốn trăm bảy mươi gam" là số (470), còn "bon kem" mới là brand Pond's.
        if not (t in AMBIGUOUS and price is None and (name or qty is not None)
                and not (i + 1 < n and toks[i + 1] in {"tram", "muoi", "chuc"})):
            p = parse_number(toks, i)
            if p:
                v, j = p
                if name and price is None and j + 1 < n and toks[j] == "trong" and parse_number(toks, j + 1):
                    v2, j2 = parse_number(toks, j + 1)   # "rửa chén mười bốn trong một": số đọc bằng chữ nằm trong TÊN SKU
                    name.extend([str(v), "trong", str(v2)]); i = j2; continue
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


def _items_in(sentence: str, catalog: Catalog) -> list[dict]:
    """Trong một câu, chỉ giữ dòng có ĐỦ số lượng + sản phẩm khớp catalog + giá."""
    items = []
    for qty, words, price in scan_segments(sentence):
        if price is None:       # bắt buộc có giá
            continue
        res = catalog.match(words)
        if res["conf"] < MIN_MATCH:
            continue
        assumed = qty is None   # ASR rơi mất số lượng ("3 .1KG, COMFORT ... GIA 92K") -> giả định 1, đánh dấu cần xác nhận
        q = 1 if assumed else qty
        need = res["conf"] < 0.85 or assumed or q == 0 or q > 200 or price_suspect(price)
        items.append({
            "raw": " ".join(words), "qty": q, "qty_assumed": assumed,
            "price": price, "price_missing": False, **res, "need_confirm": need,
        })
    return items


def _item_groups(text: str, catalog: Catalog) -> list[tuple[list[dict], str]]:
    """Chia toàn văn thành các nhóm: mỗi câu có dòng hàng mở một nhóm mới; các câu liền sau
    (đến câu có hàng kế tiếp) là 'phản hồi' của nhóm đó. Trả về [(items, after_text)]."""
    text = LIST_NO.sub(r"\1\2", text)           # bỏ số thứ tự ASR tự thêm: "1. omo" -> "1 omo"
    groups: list[list] = []
    for sent in filter(str.strip, SENT_END.split(text)):
        items = _items_in(sent, catalog)
        if items:
            groups.append([items, []])
        elif groups:
            groups[-1][1].append(sent.strip())
    return [(items, " ".join(after)) for items, after in groups]


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
    """Dòng hàng chỉ tìm trong lượt SA; phản hồi lấy từ lượt KHÁCH ngay sau đó.
    Không có lượt khách liền sau -> "chưa rõ" (lời SA như "dạ ok em" KHÔNG được tính là khách đồng ý)."""
    orders = []
    for k, t in enumerate(turns):
        if t.get("speaker") != "sa":
            continue
        groups = _item_groups(normalize(t.get("text", "")), catalog)
        if not groups:
            continue
        cust, j = [], k + 1
        while j < len(turns) and turns[j].get("speaker") == "customer":
            cust.append(turns[j].get("text", ""))
            j += 1
        cust_norm = normalize(" ".join(cust))
        for idx, (items, _sa_tail) in enumerate(groups):   # phần đuôi là lời SA -> bỏ, không dùng để đoán khách
            if idx == len(groups) - 1 and cust_norm:
                orders.append(_make_order(items, cust_norm, "customer_turn"))
            else:
                orders.append(_make_order(items, "", "no_customer_turn"))
    return orders


def parse_transcript(text: str, catalog: Catalog, turns: list[dict] | None = None) -> dict:
    orders = _orders_from_turns(turns, catalog) if turns else []
    if not orders:  # chưa tách người nói (hoặc không thấy dòng hàng trong lời SA) -> quét toàn văn
        for items, after in _item_groups(normalize(text), catalog):
            orders.append(_make_order(items, after, "text"))
    return {"closing_detected": bool(orders), "orders": orders}