"""Brand Unilever đọc theo TIẾNG VIỆT (có cả giọng vùng miền) + dung tích/giá đọc bằng chữ.

Model tiếng Việt (PhoWhisper) viết theo âm: "Clear" -> "cờ lia", "Surf" -> "sốp", "9kg" -> "chín ki lô gam"; người Việt còn đọc lệch
b/p, gi/d/r, x/s, l/n, tr/ch ("Surf" -> "xốp", "Hazeline" -> "ha xo lin", "Sunlight" -> "săn nai")...
  1) BRAND_VI + brand_variants(): mỗi alias SKU có chứa tên brand chuẩn được nhân thêm một bản cho MỖI cách đọc (Catalog dùng).
     Cố ý KHÔNG thay chữ trong transcript: nhiều cách đọc trùng từ thường khi bỏ dấu ("do", "bon" = bốn, "lac" = lạc, "ac" = ác),
     thay toàn văn sẽ làm hỏng câu nói bình thường. Làm ở alias thì chỉ ảnh hưởng đoạn có {số lượng} {sản phẩm} {giá}.
  2) canon_units(): đơn vị đọc thành chữ ('ki lô gam' -> 'kg', 'ba phẩy tám' -> '3.8kg'), gọi trong normalize().
  3) asr_prompt()/vi_text(): sinh "script" gợi ý cho ASR bằng tiếng Việt (brand theo âm, dung tích/giá bằng chữ).
Thêm brand / cách đọc mới: sửa BRAND_VI (+ BRAND_LATIN nếu brand mới). Gõ có dấu hay không dấu đều nhận. Phần tử ĐẦU TIÊN
của mỗi danh sách là cách đọc chuẩn, dùng để viết prompt cho ASR.
"""
import re
from .normalize import strip_accents

# tên brand chuẩn (viết thường, không dấu, đúng như catalog) -> các cách đọc tiếng Việt
BRAND_VI: dict[str, list[str]] = {
    "omo": ["ô mô"],
    "ps": ["pi ét", "pe ét", "bi ét", "bê ét"],                        # P/S: b/p lẫn nhau
    "closeup": ["clo súp", "clo sáp", "cờ lo súp", "cờ lo sáp", "lo súp", "lo sáp", "cờ lo xúp", "lo xúp"],
    "dove": ["đô vơ", "đô", "đô ve", "giô vơ"],                         # gi/d lẫn nhau
    "sunlight": ["săn lai", "xăn lai", "săn nai", "xăn nai"],           # s/x, l/n
    "comfort": ["com phót", "com pho", "com po", "com bo"],             # ph/p/b
    "clear": ["cờ lia", "lia", "kờ lia", "clia"],
    "sunsilk": ["săn siu", "xăn siu", "săn xiu", "xăn xiu"],
    "tresemme": ["tre se mê", "tre xe mê", "che se mê", "che xe mê", "tri se mê"],   # s/x, tr/ch
    "hazeline": ["ha giô lin", "ha đô lin", "ha ze lin", "ha so lin", "ha xo lin", "ha de lin", "ha zo lin"],
    "lifebuoy": ["lai bôi", "lai pôi"],
    "vaseline": ["va so lin", "va giô lin", "va xo lin", "va đô lin", "va ze lin", "va de lin"],
    "lux": ["lút", "lắc"],
    "rexona": ["re xô na", "re sô na", "đê xô na", "đê sô na"],        # r/d, s/x
    "axe": ["ét", "éc", "ắc"],
    "surf": ["sốp", "xốp"],
    "vim": ["vim", "vin", "bim"],
    "cif": ["síp", "xíp", "cíp"],
    "ponds": ["pon", "bon", "pong", "bong"],
    "knorr": ["cờ nor", "cờ nô", "ca nô", "nor"],                       # ĐOÁN, chưa có dữ liệu thật: kiểm tra lại
    "walls": ["oan", "oao", "goa", "quan"],                             # ĐOÁN, chưa có dữ liệu thật: kiểm tra lại
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


def brand_variants(alias: str) -> list[str]:
    """Alias SKU (đã normalize, không dấu) có tên brand Latin -> các bản thay brand bằng từng cách đọc tiếng Việt."""
    out = []
    for rx, vs in _ALIAS_RULES:
        if rx.search(alias):
            out += [rx.sub(v, alias, count=1) for v in vs]
    return out


# Đơn vị đọc thành chữ -> đơn vị chuẩn. Chạy trên chữ đã bỏ dấu.
_UNIT_FIX = [
    (re.compile(_NB + r"ki\s*lo\s*gr?am" + _NE), "kg"),
    (re.compile(_NB + r"ki\s*lo" + _NE), "kg"),
    (re.compile(_NB + r"mi\s*li\s*lit" + _NE), "ml"),
    (re.compile(_NB + r"go\s*ram" + _NE), "gam"),
]
_DIG = {"khong": "0", "mot": "1", "hai": "2", "ba": "3", "bon": "4", "nam": "5", "lam": "5",
        "sau": "6", "bay": "7", "tam": "8", "chin": "9"}
_NUM = r"(\d+|" + "|".join(_DIG) + r")"
# "ba phẩy tám ki lô gam" -> "3.8kg" (số thập phân đọc bằng chữ; dung tích đã nối liền như parser mong đợi)
_DEC = re.compile(_NB + _NUM + r"\s+(?:phay|cham)\s+" + _NUM + r"\s*(kg|ky|ki|g|gr|gam|gram|ml|l|lit|lt)" + _NE)


def _dec_sub(m: re.Match) -> str:
    return f"{_DIG.get(m.group(1), m.group(1))}.{_DIG.get(m.group(2), m.group(2))}{m.group(3)}"


def canon_units(t: str) -> str:
    """t: chữ thường, đã bỏ dấu. 'ki lô gam' -> 'kg'; 'mi li lít' -> 'ml'; 'ba phẩy tám ki' -> '3.8kg'."""
    for rx, rep in _UNIT_FIX:
        t = rx.sub(rep, t)
    return _DEC.sub(_dec_sub, t)


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
