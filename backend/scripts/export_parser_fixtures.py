"""Xuất chỉ mục catalog + bộ transcript mẫu + kết quả parser Python -> JSON, để app (TypeScript) kiểm tra kết quả trùng server.

Chạy:  cd backend && python scripts/export_parser_fixtures.py ../mobile/app/scripts/fixtures
Rồi:   cd mobile/app && npm run test:parser
Bộ transcript = mọi chuỗi trong tests/*.py trông giống câu nói + các biến thể ghép/cắt ngẫu nhiên (seed cố định).
"""
import ast
import glob
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.parser import Catalog, parse_transcript  # noqa: E402


def harvest() -> list[str]:
    out: set[str] = set()
    for f in glob.glob(os.path.join(os.path.dirname(__file__), "..", "tests", "*.py")):
        for node in ast.walk(ast.parse(open(f, encoding="utf-8").read())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) > 12 and " " in node.value and "\n" not in node.value:
                out.add(node.value)
    return sorted(out)


def mutate(base: list[str], n: int) -> list[str]:
    rnd = random.Random(42)
    res: list[str] = []
    for _ in range(n):
        a, b = rnd.choice(base), rnd.choice(base)
        wa, wb = a.split(), b.split()
        k = rnd.random()
        if k < 0.35:      # ghép hai câu
            res.append(a + rnd.choice([". ", ", ", " "]) + b)
        elif k < 0.6:     # cắt đầu/đuôi
            res.append(" ".join(wa[rnd.randint(0, len(wa) // 3):len(wa) - rnd.randint(0, len(wa) // 3)]) or a)
        elif k < 0.8:     # bỏ dấu phẩy / chấm (giọng nói không có dấu câu)
            res.append(a.replace(",", "").replace(".", ""))
        else:             # chèn từ đệm
            i = rnd.randint(0, len(wa))
            res.append(" ".join(wa[:i] + rnd.choice(["dạ", "ờ", "à", "vâng", "thì"]).split() + wa[i:]))
    return res


def main(out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    cat = Catalog()
    base = harvest()
    texts = base + mutate(base, 1500)
    cases = [{"text": t, "expected": parse_transcript(t, cat)} for t in texts]
    json.dump(cat.export_payload(), open(os.path.join(out_dir, "catalog.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(cases, open(os.path.join(out_dir, "cases.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(f"{len(base)} câu gốc, {len(cases)} ca, {sum(1 for c in cases if c['expected']['orders'])} ca có đơn")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "fixtures")
