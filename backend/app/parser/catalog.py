import csv
import os
from rapidfuzz import fuzz
from .tokens import canon_tokens, SIZE_RE


class Catalog:
    def __init__(self, path: str | None = None):
        path = path or os.getenv(
            "SKU_CATALOG",
            os.path.join(os.path.dirname(__file__), "..", "..", "data", "sku_catalog.csv"),
        )
        self.skus: dict[str, dict] = {}
        self.index: list[tuple[str, str, str | None]] = []  # (sku_id, alias_words, alias_size)
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                self.skus[row["sku_id"]] = {
                    "sku_id": row["sku_id"], "name": row["name"], "unit": row["unit"],
                }
                aliases = [a for a in row["aliases"].split("|") if a.strip()] + [row["name"]]
                for a in aliases:
                    toks = canon_tokens(a)
                    size = next((t for t in toks if SIZE_RE.match(t)), None)
                    words = " ".join(t for t in toks if not SIZE_RE.match(t))
                    self.index.append((row["sku_id"], words, size))

    def hotwords(self) -> str:
        """Chuỗi gợi ý cho ASR (initial_prompt) để nghe đúng tên SKU."""
        return ", ".join(s["name"] for s in self.skus.values())

    def match(self, words: list[str]) -> dict:
        size = next((w for w in words if SIZE_RE.match(w)), None)
        plain = [w for w in words if not SIZE_RE.match(w)]
        ordered = " ".join(plain)
        sorted_ = " ".join(sorted(plain))
        compact = ordered.replace(" ", "")

        best: dict[str, float] = {}
        for sku_id, a_words, a_size in self.index:
            a_sorted = " ".join(sorted(a_words.split()))
            s = 0.6 * fuzz.token_set_ratio(sorted_, a_sorted) + 0.4 * fuzz.token_sort_ratio(sorted_, a_sorted)
            s = max(s, fuzz.ratio(compact, a_words.replace(" ", "")))
            if size:
                if a_size is None:
                    s *= 0.9
                elif a_size != size:
                    s *= 0.6
            best[sku_id] = max(best.get(sku_id, 0.0), s)

        ranked = sorted(best.items(), key=lambda x: -x[1])
        top, top_s = ranked[0]
        second_s = ranked[1][1] if len(ranked) > 1 else 0.0
        conf = top_s / 100.0
        if top_s - second_s < 4:  # hai SKU quá sát nhau => mơ hồ
            conf = min(conf, 0.6)
        return {
            "sku_id": top,
            "sku_name": self.skus[top]["name"],
            "conf": round(conf, 3),
            "candidates": [
                {"sku_id": k, "name": self.skus[k]["name"], "score": round(v, 1)}
                for k, v in ranked[:3]
            ],
        }
