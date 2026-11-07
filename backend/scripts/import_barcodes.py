"""Nạp BARCODE từ file Excel danh mục (cột PRODUCT_NAME_VN, BARCODE) vào data/sku_catalog.csv (cột `barcode`).

Chạy (trong thư mục backend/):
    python -m scripts.import_barcodes /đường/dẫn/96sku.xlsx            # xem trước, KHÔNG ghi file
    python -m scripts.import_barcodes /đường/dẫn/96sku.xlsx --write    # ghi vào data/sku_catalog.csv
Chạy lại nhiều lần an toàn. Khởi động lại API để db.sync_skus đẩy barcode vào bảng skus.

Ghép Excel <-> catalog 1-1: bước 1 trùng tên (bỏ phần quy cách "/12 Chai" cuối tên Excel), bước 2 cùng dung tích + tên
gần giống nhất. Dòng không ghép được / barcode sai chuẩn EAN-13 / barcode trùng được liệt kê rõ và KHÔNG tự đoán.
"""
import csv
import re
import sys

import openpyxl
from rapidfuzz import fuzz

from app.parser.normalize import strip_accents

CSV_PATH = "data/sku_catalog.csv"
FUZZY_MIN = 90


def clean_barcode(v) -> str:
    """Excel lưu barcode lúc dạng số, lúc dạng chữ ("8934...", 8934868192985.0): đưa về chuỗi chữ số."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"\s+", "", str(v))


def ean13_ok(b: str) -> bool:
    if not re.fullmatch(r"\d{13}", b):
        return False
    return (10 - sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(b[:12]))) % 10 == int(b[12])


def _key(s: str) -> str:
    s = strip_accents(str(s).lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9. ]+", " ", s)).strip()


def _sizes(s: str) -> frozenset:
    return frozenset(re.findall(r"\d+(?:\.\d+)?(?:kg|g|ml|l)\b", _key(s).replace(" ", "")))


PACK_WORDS = {"chai", "tuyp", "ong", "goi", "tui", "hop", "cay", "bo", "vi", "day", "lo", "can", "thung", "loc", "hu", "lon", "cai"}


def strip_pack(name: str) -> str:
    """"OMO BG đỏ 9kg/1 gói" -> "OMO BG đỏ 9kg"; "SIMPLE ... 50ml/Chai" -> "SIMPLE ... 50ml".
    Chỉ cắt phần quy cách Ở CUỐI (bắt đầu bằng số, hoặc là từ quy cách như chai/tuýp/gói) nên "P/S ..." giữ nguyên."""
    name = name.strip()
    head, sep, tail = name.rpartition("/")
    if not sep:
        return name
    first = _key(tail).split(" ")[0] if _key(tail) else ""
    return head.strip() if first[:1].isdigit() or first in PACK_WORDS else name


def read_excel(path: str) -> list[dict]:
    rows = list(openpyxl.load_workbook(path, read_only=True, data_only=True).active.iter_rows(values_only=True))
    hdr = [str(h or "").strip() for h in rows[0]]
    need = ("PRODUCT_NAME_VN", "BARCODE")
    if any(n not in hdr for n in need):
        sys.exit(f"File Excel thiếu cột {need}; header hiện có: {hdr}")
    out = []
    for r in rows[1:]:
        d = dict(zip(hdr, r))
        if d.get("PRODUCT_NAME_VN"):
            out.append({"name": strip_pack(str(d["PRODUCT_NAME_VN"])), "full": str(d["PRODUCT_NAME_VN"]).strip(),
                        "barcode": clean_barcode(d["BARCODE"])})
    return out


def match(cat: list[dict], xl: list[dict]):
    """Trả về ({chỉ số catalog: dòng Excel}, [(chỉ số catalog, điểm, dòng Excel) ghép mờ để người xem lại])."""
    pairs, fuzzy = {}, []
    free_x = set(range(len(xl)))
    by_key: dict[str, list[int]] = {}
    for j, x in enumerate(xl):
        by_key.setdefault(_key(x["name"]), []).append(j)
    for i, c in enumerate(cat):
        js = [j for j in by_key.get(_key(c["name"]), []) if j in free_x]
        if len(js) == 1:
            pairs[i] = xl[js[0]]; free_x.discard(js[0])
    cand = []
    for i, c in enumerate(cat):
        if i in pairs:
            continue
        for j in free_x:
            if _sizes(c["name"]) == _sizes(xl[j]["name"]):
                a, b = _key(c["name"]), _key(xl[j]["name"])
                # so cả khi Excel viết dính chữ ("NướcGiặt", "CửaTrước"): bỏ hết khoảng trắng rồi so lại
                cand.append((max(fuzz.token_sort_ratio(a, b), fuzz.ratio(a.replace(" ", ""), b.replace(" ", ""))), i, j))
    for score, i, j in sorted(cand, reverse=True):
        if score >= FUZZY_MIN and i not in pairs and j in free_x:
            pairs[i] = xl[j]; free_x.discard(j); fuzzy.append((i, score, xl[j]))
    return pairs, fuzzy, [xl[j] for j in sorted(free_x)]


def main(xlsx: str, write: bool):
    with open(CSV_PATH, encoding="utf-8", newline="") as f:
        rd = csv.DictReader(f)
        cols, cat = list(rd.fieldnames), list(rd)
    xl = read_excel(xlsx)
    pairs, fuzzy, left_x = match(cat, xl)
    problems = []
    seen: dict[str, str] = {}
    for i, x in pairs.items():
        b = x["barcode"]
        if not ean13_ok(b):
            problems.append(f"Barcode sai chuẩn EAN-13: {b!r} ({x['full']})")
        elif b in seen:
            problems.append(f"Barcode trùng {b}: {seen[b]} / {cat[i]['name']}")
        seen[b] = cat[i]["name"]
    print(f"Excel {len(xl)} dòng, catalog {len(cat)} SKU: ghép được {len(pairs)} "
          f"({len(pairs) - len(fuzzy)} trùng tên, {len(fuzzy)} ghép theo dung tích + tên gần giống)")
    for i, score, x in fuzzy:
        print(f"  [xem lại {score:.0f}] {cat[i]['name']}  <->  {x['full']}  -> {x['barcode']}")
    for i, c in enumerate(cat):
        if i not in pairs:
            print(f"  [KHÔNG GHÉP ĐƯỢC] catalog: {c['name']}")
    for x in left_x:
        print(f"  [EXCEL THỪA] {x['full']} ({x['barcode']})")
    for p in problems:
        print("  [LỖI DỮ LIỆU]", p)
    if not write:
        print("Chạy lại với --write để ghi vào", CSV_PATH)
        return 1 if problems or len(pairs) < len(cat) else 0
    if problems:
        sys.exit("Có lỗi dữ liệu ở trên, chưa ghi file. Sửa file Excel rồi chạy lại.")
    if "barcode" not in cols:
        cols.append("barcode")
    for i, c in enumerate(cat):
        c["barcode"] = pairs[i]["barcode"] if i in pairs else (c.get("barcode") or "")
    with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(cat)
    print(f"Đã ghi barcode cho {sum(1 for c in cat if c['barcode'])}/{len(cat)} SKU vào {CSV_PATH}")
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    sys.exit(main(args[0], "--write" in sys.argv))
