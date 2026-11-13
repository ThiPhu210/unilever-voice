"""Brand Unilever đọc theo TIẾNG VIỆT + dung tích/giá đọc bằng chữ.

Model tiếng Việt (PhoWhisper) viết theo âm: "Clear" -> "cờ lia", "Surf" -> "sốp", "9kg" -> "chín ki lô gam"; người Việt còn đọc lệch
theo vùng miền (b/p, gi/d/r, x/s, l/n, tr/ch, -t/-c, -n/-ng...: "Surf" -> "xốp", "Hazeline" -> "ha xo lin", "Sunlight" -> "săn nai").
  1) BRAND_VI chỉ giữ cách đọc GỐC của brand (phiên âm từ tiếng Anh: "clear" -> "cờ lia" / "clia"). KHÔNG liệt kê giọng vùng miền:
     phần đó do phonetics.fold() lo, cả alias SKU lẫn transcript đều được gấp về cùng khoá âm lúc so khớp (xem Catalog.match),
     nên "xăn nai", "săn lai", "xăn lai"... tự khớp mà không cần ghi từng cái. Brand mới chỉ cần thêm 1-2 cách đọc gốc.
     Brand_variants(): mỗi alias SKU có tên brand Latin được nhân thêm một bản cho MỖI cách đọc gốc (Catalog dùng).
     Cố ý KHÔNG thay chữ trong transcript: nhiều cách đọc trùng từ thường khi bỏ dấu ("do", "bon" = bốn, "lac" = lạc, "ac" = ác),
     thay toàn văn sẽ làm hỏng câu nói bình thường. Làm ở alias thì chỉ ảnh hưởng đoạn có {số lượng} {sản phẩm} {giá}.
  2) canon_units(): đơn vị đọc thành chữ ('ki lô gam' -> 'kg', 'ba phẩy tám' -> '3.8kg'), gọi trong normalize().
  3) asr_prompt()/vi_text(): sinh "script" gợi ý cho ASR bằng tiếng Việt (brand theo âm, dung tích/giá bằng chữ).
Thêm brand / cách đọc mới: sửa BRAND_VI (+ BRAND_LATIN nếu brand mới). Gõ có dấu hay không dấu đều nhận. Phần tử ĐẦU TIÊN
của mỗi danh sách là cách đọc chuẩn, dùng để viết prompt cho ASR. Muốn kiểm tra một cách nói lệch có được nhận không:
phonetics.fold("xăn nai") == phonetics.fold("săn lai").
"""
import re
from .normalize import strip_accents

# tên brand chuẩn (viết thường, không dấu, đúng như catalog) -> cách đọc GỐC (phiên âm). Giọng vùng miền KHÔNG ghi ở đây.
# Chỉ thêm cách đọc thứ hai khi nó khác về nguyên âm/số âm tiết (vd "cờ lo súp" vs "clo súp", "pi ét" vs "pê ét"),
# vì những chỗ đó phonetics.fold() không gộp được.
BRAND_VI: dict[str, list[str]] = {
    "omo": ["ô mô"],
    "ps": ["pi ét", "pê ét"],                       # đọc chữ P kiểu Anh / kiểu Việt (b/p lẫn nhau do fold lo)
    "closeup": ["clo súp", "cờ lo súp"],
    "dove": ["đô vơ"],
    "sunlight": ["săn lai"],
    "comfort": ["com phót"],
    "clear": ["cờ lia", "clia", "cái ly"],           # "cái ly": Google/Siri nghe "một clear" thành "một cái ly" (gặp thật ở bản ghi trên Android)
    "sunsilk": ["săn siu"],
    "tresemme": ["tre se mê"],
    "hazeline": ["ha giô lin", "ha ze lin", "hazard"],   # "hazard": Whisper hay viết thẳng chữ Latin sai này (không phải lệch vùng miền)
    "lifebuoy": ["lai bôi"],
    "vaseline": ["va so lin", "va ze lin"],
    "lux": ["lút", "lắc"],
    "rexona": ["re xô na"],
    "axe": ["ét", "ắc"],
    "surf": ["sốp"],
    "vim": ["vim"],
    "cif": ["síp", "cíp"],
    "ponds": ["pon"],
    "knorr": ["cờ nor", "ca nô"],                   # ĐOÁN, chưa có dữ liệu thật: kiểm tra lại
    "simple": ["sim bồ"],
    "walls": ["oan"],                               # ĐOÁN, chưa có dữ liệu thật: kiểm tra lại ("quan"/"goa" đã được fold gộp về "oan")
}

# Cách viết Latin của brand TRONG alias/tên SKU sau normalize() (bỏ dấu, ký tự lạ thành khoảng trắng: "P/S" -> "p s", "Pond's" -> "pond s")
BRAND_LATIN: dict[str, list[str]] = {
    "ps": ["p s", "ps"], "closeup": ["closeup", "close up"], "ponds": ["ponds", "pond s"], "walls": ["walls", "wall s"],
}
# Cách viết brand trong TÊN SKU gốc (để vi_text đổi sang tiếng Việt); mặc định là chính tên brand
_NAME_RE = {"ps": r"P/S", "closeup": r"CLOSE-?\s?UP", "tresemme": r"TRESEMM[EÉ]", "ponds": r"POND'?S", "walls": r"WALL'?S"}

_NB = r"(?<![a-z0-9])"      # đầu từ
_NE = r"(?![a-z0-9])"       # cuối từ


def _plain(v: str) -> str:
    return " ".join(strip_accents(v.lower()).split())


def _build_alias_rules():
    rules = []
    for brand, variants in BRAND_VI.items():
        forms = BRAND_LATIN.get(brand, [brand])
        rx = re.compile(_NB + "(?:" + "|".join(re.escape(f) for f in sorted(forms, key=len, reverse=True)) + ")" + _NE)
        latin = set(forms)
        vs = list(dict.fromkeys(p for p in map(_plain, variants) if p not in latin))   # bỏ trùng + bỏ cách đọc giống hệt chữ Latin
        rules.append((rx, vs))
    return rules


_ALIAS_RULES = _build_alias_rules()


# Từ vựng sản phẩm (không phải brand) hay gặp trong tên SKU và hay bị ASR viết theo âm. Chỉ dùng để nhân alias, không vào prompt ASR.
TERM_VI: dict[str, list[str]] = {
    r"ceramides?": ["sê ra mai", "xê ra mít"],
    "pro": ["bồ", "pờ rô"],
    "matcha": ["mát cha", "mắt da"],     # "mắt da"/"mắc cha": ASR nghe sai gặp lặp lại trong dữ liệu thật
    "serum": ["se rum", "xê rum"],
    "derma": ["đơ ma", "đe ma"],
}
_TERM_RULES = [(re.compile(_NB + k + _NE), [p for p in dict.fromkeys(map(_plain, v))]) for k, v in TERM_VI.items()]


def brand_variants(alias: str) -> list[str]:
    """Alias SKU (đã normalize, không dấu) có tên brand / từ vựng Latin -> các bản thay bằng cách đọc tiếng Việt.
    Các từ được thay ĐỘC LẬP rồi nhân tổ hợp ("simple ... pro ceramides" -> "sim bo ... bo se ra mai"), tối đa 40 bản."""
    rules = [(rx, vs) for rx, vs in _ALIAS_RULES + _TERM_RULES if rx.search(alias) and vs]
    out = [alias]
    for rx, vs in rules:
        out = out + [rx.sub(v, a, count=1) for a in out for v in vs]
        out = out[:40]
    return out[1:]


# Đơn vị đọc thành chữ -> đơn vị chuẩn. Chạy trên chữ đã bỏ dấu.
_UNIT_FIX = [
    (re.compile(_NB + r"ki\s*lo\s*gr?am" + _NE), "kg"),
    (re.compile(_NB + r"ki\s*lo" + _NE), "kg"),
    (re.compile(_NB + r"(?:mi\s*li\s*lit|mi\s*li|mi\s*lit|mie?u|mi\s*mit|mil)" + _NE), "ml"),   # "mi li lít" / "mi li" / "miu" / "miêu"
    (re.compile(_NB + r"go\s*ram" + _NE), "gam"),
]
_DIG = {"khong": "0", "mot": "1", "hai": "2", "ba": "3", "bon": "4", "nam": "5", "lam": "5",
        "sau": "6", "bay": "7", "tam": "8", "chin": "9"}
_NUM = r"(\d+|" + "|".join(_DIG) + r")"
# "ba phẩy tám ki lô gam" -> "3.8kg" (số thập phân đọc bằng chữ; dung tích đã nối liền như parser mong đợi)
_DEC = re.compile(_NB + _NUM + r"\s+(?:phay|cham)\s+" + _NUM + r"\s*(kg|ky|ki|g|gr|gam|gram|ml|l|lit|lt)" + _NE)


# "ba ký chín" = 3.9kg ("ký" đóng vai dấu phẩy; ASR còn viết "chín" thành "chính"). Chỉ nhận khi số sau KẾT THÚC cụm (hết câu / "giá"),
# để "một ký chín mươi nghìn" hay "một ký, 2 omo" không bị nối nhầm.
_DIG2 = {**_DIG, "chinh": "9", "rua": "5"}
_NUM2 = r"(\d|" + "|".join(k for k in _DIG2 if k != "rua") + r")"
_KY_DEC = re.compile(_NB + _NUM + r"\s+(?:ky|kg|ki\s*lo|ki)\s+" + _NUM2 + r"(?=\s*(?:gia\b|da\b|[,;.?!]|$))")


# ASR hay nghe "một ký" thành "một tí"/"một ty": số + "ti|ty" đứng NGAY TRƯỚC "giá" / dấu câu / hết câu là dung tích "ký".
# ("một ti vi ..." không bị đụng vì sau "ti" là một từ khác.)
_TI_KY = re.compile(_NB + _NUM + r"\s+(?:ti|ty)(?=\s*(?:gia\b|da\b|[,;.?!]|$))")


def _ky_sub(m: re.Match) -> str:
    return f"{_DIG.get(m.group(1), m.group(1))}.{_DIG2.get(m.group(2), m.group(2))}kg"


def _dec_sub(m: re.Match) -> str:
    return f"{_DIG.get(m.group(1), m.group(1))}.{_DIG.get(m.group(2), m.group(2))}{m.group(3)}"


def canon_units(t: str) -> str:
    """t: chữ thường, đã bỏ dấu. 'ki lô gam' -> 'kg'; 'mi li lít' -> 'ml'; 'ba phẩy tám ki' -> '3.8kg'."""
    for rx, rep in _UNIT_FIX:
        t = rx.sub(rep, t)
    t = _DEC.sub(_dec_sub, t)
    t = _TI_KY.sub(lambda m: f"{m.group(1)} ky", t)
    return _KY_DEC.sub(_ky_sub, t)


# ---------- Sinh "script" tiếng Việt cho ASR ----------
_D = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]


def _tens(n: int) -> str:          # 1..99
    if n < 10:
        return _D[n]
    t, u = divmod(n, 10)
    head = "mười" if t == 1 else f"{_D[t]} mươi"
    if u == 0:
        return head
    return f"{head} " + {1: "một" if t == 1 else "mốt", 5: "lăm"}.get(u, _D[u])


def _hund(n: int) -> str:          # 1..999
    h, r = divmod(n, 100)
    if h == 0:
        return _tens(r)
    s = f"{_D[h]} trăm"
    if r == 0:
        return s
    return f"{s} linh {_D[r]}" if r < 10 else f"{s} {_tens(r)}"


def num_to_vi(n: int) -> str:
    """0..9999 -> chữ tiếng Việt ('một trăm hai mươi lăm', 'sáu mươi lăm nghìn' dùng thêm 'nghìn' cho giá)."""
    if n == 0:
        return "không"
    th, r = divmod(n, 1000)
    parts = []
    if th:
        parts.append(f"{_hund(th)} nghìn")
    if r:
        if th and r < 100:
            parts.append("không trăm " + (f"linh {_D[r]}" if r < 10 else _tens(r)))
        else:
            parts.append(_hund(r))
    return " ".join(parts)


_SIZE = re.compile(r"(?<![A-Za-z\d.,])(\d{1,4})(?:[.,](\d{1,2}))?\s*(kg|gr|g|ml|l)(?![A-Za-z0-9])", re.I)
_UNIT_VI = {"kg": "ki lô gam", "g": "gam", "gr": "gam", "ml": "mi li lít", "l": "lít"}
_NAME_PATS = [(re.compile(r"(?<![A-Za-z0-9])(?:" + _NAME_RE.get(b, re.escape(b)) + r")(?![A-Za-z0-9])", re.I), v[0]) for b, v in BRAND_VI.items()]


def _size_sub(m: re.Match) -> str:
    s = num_to_vi(int(m.group(1)))
    if m.group(2):
        s += " phẩy " + " ".join(_D[int(c)] for c in m.group(2))
    return f"{s} {_UNIT_VI[m.group(3).lower()]}"


def vi_text(name: str) -> str:
    """Tên SKU -> cách đọc tiếng Việt: brand theo âm, dung tích/khối lượng bằng chữ ('CLEAR ... 350G' -> 'cờ lia ... ba trăm năm mươi gam')."""
    for rx, spoken in _NAME_PATS:
        name = rx.sub(spoken, name)
    return _SIZE.sub(_size_sub, name)


# Câu mẫu đúng mẫu {số lượng} {sản phẩm} {dung tích} {giá}, toàn bằng chữ: để model viết giá/dung tích kiểu tiếng Việt.
SCRIPT = ("Dạ em xin cảm ơn anh chị, vậy mình chốt: hai chai dầu gội cờ lia ba trăm năm mươi gam giá một trăm hai mươi nghìn đồng, "
          "một can nước giặt sốp chín ki lô gam giá sáu mươi lăm nghìn đồng, ba chai sữa tắm lai bôi hai trăm bảy mươi gam giá bốn mươi lăm nghìn đồng.")


def asr_prompt(hotwords: str = "") -> str:
    """initial_prompt cho ASR. Whisper chỉ giữ ~223 token CUỐI của prompt nên xếp theo độ quan trọng tăng dần:
    gợi ý tên SKU (dễ bị cắt) -> danh sách brand -> câu mẫu (SCRIPT, luôn còn nguyên)."""
    brands = ", ".join(v[0] for v in BRAND_VI.values())
    hint = (hotwords[:150].rsplit(",", 1)[0] + ". ") if hotwords else ""
    return f"{hint}Nhãn hàng: {brands}. {SCRIPT}"
