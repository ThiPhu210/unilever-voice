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
from .numbers import DIGITS
from .confirm_words import YES_START_RE, WEAK_YES, STRONG_NO_RE, QUESTION_RE, YES_RE, NO_RE, YES_OVERRIDE_RE

SEPARATORS = {",", ";", "va", "voi", "cong", "them"}
QTY_UNITS = {"chai", "goi", "lon", "hop", "thung", "tuyp", "tui", "loc", "cai",
             "bich", "hu", "bo", "lo", "can", "bao", "vi"}
STOP_NAME = {"a", "nhe", "nha", "ha", "da", "vang", "di", "cua", "loai", "hang",
             "cai", "x", "la", "don", "gia", "moi", "tien", "dong", "vnd", "d"}
# Lời mở đầu / xã giao ("dạ em xin cảm ơn chị vậy mình chốt bốn kem ..."): không phải tên hàng. Bỏ ở hai đầu tên, và khi tên mới chỉ có
# toàn từ này thì "bốn/sáu/năm" vẫn là SỐ LƯỢNG (không bị coi là brand Pond's / "sâu răng").
OPENERS = {"em", "xin", "cam", "on", "chi", "anh", "chot", "minh", "vay", "oi", "ok", "roi", "gom", "luon", "len", "lay", "them", "dat", "mua",
           "cho", "vang", "da", "a", "nhe", "nha", "ha", "la", "don", "va", "thi", "xong",
           "day", "gio", "hang", "vao", "bo"}   # "dậy" = "vậy" giọng Nam; "bỏ (vào) giỏ hàng"
def _trim_openers(words: list[str]) -> list[str]:
    """Bỏ lời mở đầu / từ đệm ở hai đầu tên. "...giỏ hàng" là cụm xã giao rõ nghĩa: bỏ luôn mọi thứ đứng trước nó."""
    words = list(words)
    for k in range(min(len(words) - 1, 6)):
        if words[k] == "gio" and words[k + 1] == "hang":
            words = words[k + 2:]
            break
    skip = lambda w: w in STOP_NAME or w in OPENERS
    while words and (skip(words[0]) or (words[0] == "o" and len(words) > 1 and skip(words[1]))):   # "ờ dậy em ..."; "o mo" (Omo) thì giữ
        words.pop(0)
    while words and skip(words[-1]):
        words.pop()
    return words


LEAD_STRIP = {"don", "luon", "cho", "nhe", "la", "gom", "vay"}
AMBIGUOUS = {"nam", "sau", "bon", "bun", "tu"}  # vừa là số vừa là từ thường (clear nam, bồn cầu, Pond's đọc "bon", ...)
BATH_PREV = {"sua", "phong", "dau", "bon", "gel"}  # "sữa/xà phòng/dầu tắm": 'tam' ở đây là TẮM, không phải số TÁM
SENT_END = re.compile(r"[.?!](?=\s|$)")
MIN_MATCH = 0.6   # độ khớp SKU tối thiểu, dưới mức này coi là câu nói thường, bỏ qua

# Số thứ tự đầu dòng do ASR tự thêm: "Omo 800g, 2. Clear ..." -> dấu chấm sau "2" KHÔNG phải hết câu.
LIST_NO = re.compile(r"(^|[,;]\s*)(\d{1,2})\.(?=\s)")


def detect_customer_confirm(after: str) -> tuple[str, str | None]:
    after = " ".join(after.split()[:25])
    after = YES_OVERRIDE_RE.sub("ok", after)  # "không sao", "thôi được", "cũng được"... = đồng ý
    after = QUESTION_RE.sub(" hoi ", after)    # câu hỏi "có ... không" / "được không": bỏ ra khỏi việc dò yes/no
    y, n = YES_RE.search(after), NO_RE.search(after)
    ys = YES_START_RE.match(after)             # "chốt", "dạ chốt", "rồi em"... ở đầu phản hồi
    if ys and (not y or ys.start() <= y.start() or y.group() in WEAK_YES) and not (n and n.start() < ys.end() and not YES_START_RE.match(after[n.start():])):
        y = ys
    if y and n and y.group() in WEAK_YES and y.start() < n.start():
        sn = STRONG_NO_RE.search(after, y.end())    # "ừ... thôi để lần sau": 'ừ' chỉ là đệm
        if sn:
            return "no", sn.group()
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


def _is_new_item_start(toks: list[str], i: int, name: list[str], catalog: Catalog) -> bool:
    """toks[i] là "bốn/năm/sáu" mơ hồ (chữ trong tên hay số lượng?), `name` là chữ đã gom trước nó. Thử CẢ HAI cách hiểu rồi để catalog quyết:
      A) nó là số lượng, tên hàng bắt đầu từ chữ sau nó;  B) nó nằm trong tên: <chữ trước> + nó + <chữ sau>.
    Chọn A khi tên theo cách A khớp SKU không kém B (lời xã giao chen vào B luôn làm điểm B tụt). Không cần liệt kê lời mở đầu: câu xã giao nào đứng trước cũng chỉ làm B tệ đi.
    "kem đánh răng ps ngừa SÂU răng ...": A = "răng vượt trội" kém hơn B = cả cụm -> giữ là chữ."""
    look = []
    for t in toks[i + 1:i + 12]:
        if t in SEPARATORS or t == "gia":
            break
        look.append(t)
    if not look or toks[i + 1] in DIGITS:     # "...như SAU bốn kem...": "sau" là chữ thường, số lượng là "bốn" ngay sau nó
        return False
    top = lambda w: catalog.match(w)["candidates"][0]["score"]    # điểm thô của SKU đầu bảng (conf bị chặn 0.6 khi hai SKU sát nhau nên không dùng)
    score_a = top(look)
    return score_a >= 100 * MIN_MATCH and score_a + 0.5 >= top(_trim_openers(name) + [toks[i]] + look)


def scan_segments(text: str, catalog: Catalog | None = None) -> list[tuple[int | None, list[str], int | None]]:
    toks = TOKEN_RE.findall(text)
    segs, qty, name, price = [], None, [], None

    def flush():
        nonlocal qty, name, price
        # Từ đệm ("dạ", "nhé", "giá"...) chỉ bỏ ở HAI ĐẦU tên: chữ "la" giữa "ga la si" (Galaxy) là một âm tiết của tên hàng.
        words = _trim_openers(name)
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
        amb_in_name = (t in AMBIGUOUS and price is None and (bool(_trim_openers(name)) or qty is not None)
                       and not (i + 1 < n and toks[i + 1] in {"tram", "muoi", "chuc"}))
        if amb_in_name and qty is None and catalog is not None and _is_new_item_start(toks, i, name, catalog):
            amb_in_name = False   # phần trước KHÔNG có chữ nào là tên hàng (lời xã giao bất kỳ), phần sau là tên hàng -> đây là số lượng
        if not amb_in_name:
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


def _merge_broken(segs: list, catalog: Catalog) -> list:
    """ASR nghe sai một chữ trong tên thành SỐ ("tinh dầu hở MỘT viên vỉ bạch đàn": thảo mộc -> 'hở một') nên parser tách làm hai dòng,
    dòng đầu mất giá. Gộp lại khi dòng đầu không có giá và bản gộp khớp catalog TỐT HƠN dòng sau đứng riêng."""
    out: list = []
    k = 0
    while k < len(segs):
        qty, words, price = segs[k]
        if price is None and qty is not None and k + 1 < len(segs) and segs[k + 1][2] is not None:
            _, w2, p2 = segs[k + 1]
            merged = catalog.match(words + w2)["conf"]
            if merged >= MIN_MATCH and merged > catalog.match(w2)["conf"]:
                out.append((qty, words + w2, p2)); k += 2; continue
        out.append(segs[k]); k += 1
    return out


def _is_price_only(sentence: str) -> bool:
    """Câu chỉ là một mức giá ("giá một trăm lẻ ba nghìn"): ASR chèn dấu chấm giữa dòng hàng và giá của nó."""
    toks = TOKEN_RE.findall(sentence)
    j = _skip_price_lead(toks, 0)
    if j == 0 and not toks[:1] == ["gia"]:
        return False
    p = parse_price(toks, j, kg_as_k=True)
    return bool(p) and all(t in SEPARATORS or t in STOP_NAME or t in OPENERS for t in toks[p[1]:])


def _items_in(sentence: str, catalog: Catalog) -> list[dict]:
    """Trong một câu, chỉ giữ dòng có ĐỦ số lượng + sản phẩm khớp catalog + giá."""
    items = []
    for qty, words, price in _merge_broken(scan_segments(sentence, catalog), catalog):
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
    sents: list[str] = []
    for sent in filter(str.strip, SENT_END.split(text)):
        if sents and _is_price_only(sent) and scan_segments(sents[-1]) and scan_segments(sents[-1])[-1][2] is None:
            sents[-1] += " " + sent     # "… 230 ml. giá 103 nghìn": giá thuộc dòng hàng ngay trước
        else:
            sents.append(sent)
    for sent in sents:
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