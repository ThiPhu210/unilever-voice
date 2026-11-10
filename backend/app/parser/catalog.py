import csv
import os
from rapidfuzz import fuzz
from .normalize import strip_accents
from .tokens import canon_tokens, SIZE_RE
from .brands import vi_text, brand_variants
from .phonetics import fold
from .normalize import normalize
import re


def make_sku_id(name: str) -> str:
    """Tạo mã SKU ổn định từ tên: bỏ dấu, chữ thường, nối bằng dấu gạch ngang."""
    return re.sub(r"[^a-z0-9.]+", "-", strip_accents(name.lower())).strip("-")


def _size_near(a: str, b: str) -> bool:
    """Cùng đơn vị, cùng các chữ số có nghĩa, chỉ lệch bậc 10: 500ml ~ 50ml, 3.9kg ~ 39kg."""
    ma, mb = SIZE_RE.match(a), SIZE_RE.match(b)
    if not (ma and mb) or ma.group(2) != mb.group(2):
        return False
    sig = lambda x: x.replace(".", "").replace(",", "").strip("0")
    return sig(ma.group(1)) == sig(mb.group(1))


class Catalog:
    def __init__(self, path: str | None = None):
        path = path or os.getenv(
            "SKU_CATALOG",
            os.path.join(os.path.dirname(__file__), "..", "..", "data", "sku_catalog.csv"),
        )
        self.skus: dict[str, dict] = {}
        barcodes: dict[str, str] = {}
        self.rows: list[dict] = []
        # (sku_id, alias_words, alias_size). alias_words là KHOÁ ÂM (phonetics.fold), không phải chữ gốc: "xăn nai" và "săn lai" cùng khoá.
        self.index: list[tuple[str, str, str | None]] = []
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                # CSV chỉ cần 2 cột: name, aliases. sku_id (nếu có) được giữ; không có thì sinh từ tên. Cột barcode là tuỳ chọn.
                row["name"] = row["name"].strip()
                row["sku_id"] = (row.get("sku_id") or "").strip() or make_sku_id(row["name"])
                row["unit"] = row.get("unit") or ""
                row["aliases"] = row.get("aliases") or ""
                row["barcode"] = (row.get("barcode") or "").strip()
                if row["sku_id"] in self.skus:
                    raise ValueError(f"Trùng SKU trong catalog: {row['name']}")
                if row["barcode"]:
                    if row["barcode"] in barcodes:
                        raise ValueError(f"Trùng barcode {row['barcode']}: {barcodes[row['barcode']]} / {row['name']}")
                    barcodes[row["barcode"]] = row["name"]
                self.rows.append(row)
                self.skus[row["sku_id"]] = {
                    "sku_id": row["sku_id"], "name": row["name"], "unit": row["unit"], "barcode": row["barcode"],
                }
                aliases = [a for a in row["aliases"].split("|") if a.strip()] + [row["name"]]
                seen: set[tuple[str, str | None]] = set()
                for a in aliases:
                    # Mỗi alias có tên brand Latin được nhân thêm bản theo cách đọc gốc tiếng Việt ("clear" -> "co lia"); giọng vùng miền
                    # không nhân thêm mà do fold() gộp lúc lập chỉ mục + lúc so khớp, nên nhiều bản trùng khoá và bị bỏ ở `seen`.
                    for text in [a, *brand_variants(normalize(a))]:
                        toks = canon_tokens(text)
                        size = next((t for t in toks if SIZE_RE.match(t)), None)
                        words = " ".join(fold([t for t in toks if not SIZE_RE.match(t)]))
                        if (words, size) not in seen:
                            seen.add((words, size))
                            self.index.append((row["sku_id"], words, size))

    def hotwords(self) -> str:
        """Chuỗi gợi ý cho ASR (initial_prompt) để nghe đúng tên SKU, viết theo cách đọc tiếng Việt (brand theo âm, dung tích bằng chữ)."""
        return ", ".join(vi_text(s["name"]) for s in self.skus.values())

    def match(self, words: list[str]) -> dict:
        # Có thể có NHIỀU "size" trong một dòng khi ASR chèn rác ("1 .5Kg BS ngừa sâu răng 100g"): chỉ cần MỘT size
        # khớp với alias là đủ (không phạt); chỉ phạt khi KHÔNG size nào khớp. Trước đây chỉ lấy size đầu tiên -> rác thắng.
        sizes = [w for w in words if SIZE_RE.match(w)]
        size = sizes[-1] if sizes else None   # size "chính" = size cuối (mẫu câu: số lượng, tên, dung tích)
        plain = fold([w for w in words if not SIZE_RE.match(w)])   # cùng khoá âm với chỉ mục: bất kể giọng vùng miền
        ordered = " ".join(plain)
        sorted_ = " ".join(sorted(plain))
        compact = ordered.replace(" ", "")

        best: dict[str, float] = {}
        near: set[str] = set()   # SKU đang được chấm điểm với dung tích chỉ 'gần đúng' (lệch bậc 10)
        for sku_id, a_words, a_size in self.index:
            a_sorted = " ".join(sorted(a_words.split()))
            s = 0.6 * fuzz.token_set_ratio(sorted_, a_sorted) + 0.4 * fuzz.token_sort_ratio(sorted_, a_sorted)
            s = max(s, fuzz.ratio(compact, a_words.replace(" ", "")))
            if sizes:
                if a_size is None:
                    s *= 0.9
                elif a_size not in sizes:
                    # ASR hay đọc lệch đúng một bậc 10 ("năm trăm" thay "năm mươi": 500ml/50ml) -> phạt nhẹ, vẫn bị đánh dấu cần xác nhận
                    is_near = any(_size_near(a_size, z) for z in sizes)
                    s *= 0.85 if is_near else 0.6
            if s > best.get(sku_id, -1.0):
                best[sku_id] = s
                (near.add if sizes and a_size is not None and a_size not in sizes and is_near else near.discard)(sku_id)

        ranked = sorted(best.items(), key=lambda x: -x[1])
        top, top_s = ranked[0]
        second_s = ranked[1][1] if len(ranked) > 1 else 0.0
        conf = top_s / 100.0
        if top_s - second_s < 4:  # hai SKU quá sát nhau => mơ hồ
            conf = min(conf, 0.6)
        if top in near:           # dung tích nghe lệch bậc 10 (500ml/50ml): luôn để người xác nhận
            conf = min(conf, 0.8)
        return {
            "sku_id": top,
            "sku_name": self.skus[top]["name"],
            "conf": round(conf, 3),
            "candidates": [
                {"sku_id": k, "name": self.skus[k]["name"], "score": round(v, 1)}
                for k, v in ranked[:3]
            ],
        }