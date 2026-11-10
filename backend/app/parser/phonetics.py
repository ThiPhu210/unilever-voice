"""Gấp âm tiếng Việt: đưa mọi cách phát âm vùng miền / nói lệch về CÙNG MỘT "khoá âm", thay cho việc liệt kê từng cách đọc.

Vấn đề: PhoWhisper viết theo âm người nói nên cùng một brand có thể ra "ha giô lin", "ha đô lin", "ha xo lin", "ha zo lin"...
(giọng Bắc / Nam / Trung lẫn lộn s-x, d-gi-r, l-n, b-p-ph-v, tr-ch, -t/-c, -n/-ng/-nh). Liệt kê hết thì không bao giờ đủ,
và mỗi brand mới lại phải liệt kê lại. Ở đây ta làm ngược lại: cả hai phía (chữ trong transcript và alias SKU) đều được gấp về
khoá âm, nên các cách nói lệch có chung một khoá thì tự khớp nhau, kể cả cách nói chưa ai nghĩ tới.

Thanh điệu và dấu mũ (ơ/ô/o, ă/â/a, ê/e...) đã mất sẵn ở bước strip_accents nên không cần xử lý.

Lớp âm đầu (viết HOA để không lẫn với chữ thường):
  S = s x d gi r z j      (Bắc: x=s, d=gi=r; Nam: d/gi/r/v hay lẫn; chữ Latin z, j)
  B = b p ph f v          (b/p lẫn nhau, ph/f, v nói thành b ở vài vùng)
  L = l n nh              (l/n lẫn ở Bắc-nông thôn & Tây Nam Bộ)
  C = tr ch
  K = c k q               (chính tả khác nhau, cùng âm)
  G = g gh ; N = ng ngh ; X = kh ; T = th
  qu / w / g trước oa,oe -> o (Nam: "quan" ~ "oan")
Âm cuối: p t c ch -> k ; n ng nh -> n (miền Nam gộp, và ASR hay nghe lẫn) ; m giữ nguyên.
Nguyên âm: y -> i, ay -> ai, au -> ao.

fold(text)            -> list khoá âm của từng âm tiết (dùng để so khớp mờ)
surface_variants(r)   -> sinh ngược các cách phát âm có thể của một cách đọc (dùng cho test / kiểm tra, KHÔNG dùng khi chạy thật)
"""
import itertools
import re
from .normalize import strip_accents

_ONSET = [
    (re.compile(r"ngh?"), "N"),
    (re.compile(r"nh"), "L"),
    (re.compile(r"tr|ch"), "C"),
    (re.compile(r"kh"), "X"),
    (re.compile(r"th"), "T"),
    (re.compile(r"ph|[bpfv]"), "B"),
    (re.compile(r"qu"), "o"),                       # "quan" ~ "oan"
    (re.compile(r"w"), "o"),
    (re.compile(r"g(?=o[ae])"), ""),                # "goa" ~ "oa"
    (re.compile(r"gh|g(?!i)"), "G"),
    (re.compile(r"gi(?=[aeou])"), "S"),             # gia, gio...: i là phần của âm đầu
    (re.compile(r"gi|[drzjsx]"), "S"),              # "gi" (gì): giữ nguyên nguyên âm i
    (re.compile(r"[ckq]"), "K"),
    (re.compile(r"[ln]"), "L"),
]
_VOWELS = "aeiouy"
_SYL = re.compile(r"[^aeiouy]*[aeiouy]+(?:[^aeiouy]+(?![aeiouy]))?|[^aeiouy]+$")
_RIME = re.compile(r"([aeiouy]+)(ch|ng|nh|[tcpnm])?$")
_CODA = {"ch": "k", "t": "k", "c": "k", "p": "k", "ng": "n", "nh": "n", "n": "n", "m": "m"}


def _syllable_key(s: str) -> str:
    if not s.isalpha():          # số, dấu câu, mã hàng ("247", ",") giữ nguyên
        return s
    onset = ""
    for rx, cls in _ONSET:
        m = rx.match(s)
        if m:
            onset, s = cls, s[m.end():]
            if cls == "S" and m.group().startswith("gi") and len(m.group()) == 2 and not s[:1] in _VOWELS:
                s = "i" + s
            break
    m = _RIME.fullmatch(s)
    if m:
        v = m.group(1).replace("y", "i")
        v = re.sub(r"ay$", "ai", v) if not m.group(2) else v
        v = re.sub(r"au$", "ao", v) if not m.group(2) else v
        s = v + _CODA.get(m.group(2) or "", "")
    return re.sub(r"(.)\1+", r"\1", onset + s)


def fold(text: str | list[str]) -> list[str]:
    """Chữ (hoặc list token) -> list khoá âm, mỗi âm tiết một phần tử. Từ Latin dài (brand) được tách âm tiết trước."""
    toks = text.split() if isinstance(text, str) else text
    out: list[str] = []
    for t in toks:
        t = strip_accents(t.lower())
        out += [_syllable_key(s) for s in (_SYL.findall(t) if t.isalpha() else [t])]
    return out


# ---------- Sinh ngược các cách phát âm (chỉ dùng để kiểm thử) ----------
_ONSET_MEMBERS = {"S": ["s", "x", "d", "gi", "r"], "B": ["b", "p", "ph", "v"], "L": ["l", "n"], "C": ["ch", "tr"], "K": ["c", "k"]}
_CODA_MEMBERS = {"k": ["t", "c", "p"], "n": ["n", "ng", "nh"]}


def _syllable_variants(syl: str) -> list[str]:
    onset = ""
    for rx, cls in _ONSET:
        m = rx.match(syl)
        if m and cls in _ONSET_MEMBERS:
            onset, rest = cls, syl[m.end():]
            break
    else:
        return [syl]
    rm = _RIME.fullmatch(rest)
    if not rm:
        return [syl]
    nuc, coda = rm.group(1), rm.group(2) or ""
    front = nuc[0] in "eiy"
    ons = _ONSET_MEMBERS[onset]
    if onset == "K":
        ons = ["k"] if front else ["c"]
    ons = [o for o in ons if not (o == "gi" and nuc[0] == "i")]
    codas = [coda]
    key = _CODA.get(coda)
    if coda and key in _CODA_MEMBERS:
        codas = [c for c in _CODA_MEMBERS[key] if c != "nh" or nuc[-1] in "aei"]
    return [o + nuc + c for o in ons for c in codas]


def surface_variants(reading: str, limit: int = 300) -> list[str]:
    """'ha so lin' -> ['ha so lin', 'ha xo lin', 'ha do lin', 'ha gio lin', ..., 'ha so ling']: mọi cách nói lệch theo lớp âm ở trên."""
    parts = [_syllable_variants(strip_accents(w.lower())) for w in reading.split()]
    out = []
    for combo in itertools.islice(itertools.product(*parts), limit):
        out.append(" ".join(combo))
    return list(dict.fromkeys(out))
