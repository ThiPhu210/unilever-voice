"""Nạp danh sách SA/BA từ file 'Thông tin nhân viên Headcount SA' (Excel) vào Postgres.

Chỉ đọc các cột vận hành: COACH, REGION, PROVINCE, KA, CUSTOMER, ESS STORE CODE, STORE NAME,
BA CODE, ESS CODE, NAME, POSITION, BU, CAT NAME, TÌNH TRẠNG.
Các cột cá nhân (CCCD, ngày sinh, địa chỉ, SĐT, email, MST, BHXH, hợp đồng...) KHÔNG được đọc/lưu.
"""
import sys
import warnings

import openpyxl

from . import db

WANTED = ["COACH", "REGION", "PROVINCE", "KA", "CUSTOMER", "ESS STORE CODE", "STORE NAME",
          "BA CODE", "ESS CODE", "NAME", "POSITION", "BU", "CAT NAME", "TÌNH TRẠNG"]
LEFT = "NGHỈ VIỆC"


def _s(v) -> str | None:
    v = ("" if v is None else str(v)).strip()
    return v or None


def read_rows(path: str) -> list[dict]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = ws.iter_rows(values_only=True)
    header, idx = None, {}
    for r in rows:  # tìm dòng tiêu đề (có 'BA CODE' và 'NAME')
        names = [(_s(c) or "").upper() for c in r]
        if "BA CODE" in names and "NAME" in names:
            header = names
            idx = {n: names.index(n) for n in WANTED if n in names}
            break
    if header is None:
        raise ValueError("Không tìm thấy dòng tiêu đề (BA CODE, NAME) ở sheet đầu tiên")
    out = []
    for r in rows:
        d = {k: _s(r[i]) if i < len(r) else None for k, i in idx.items()}
        # Mã định danh = BA CODE (SA0247, BA0587); nhiều người trống BA CODE nên dùng ESS CODE thay thế.
        d["CODE"] = (d.get("BA CODE") or d.get("ESS CODE") or "").upper() or None
        if d["CODE"] and d.get("NAME"):  # bỏ vị trí trống (chưa tuyển) / dòng phụ
            out.append(d)
    return out


def import_headcount(path: str) -> dict:
    rows = read_rows(path)
    coaches: dict[str, int] = {}
    stores = staff = skipped = 0
    by_ess = sum(1 for d in rows if not d.get("BA CODE"))
    seen: set[str] = set()
    with db.tx() as c:
        def coach_id(name):
            if not name:
                return None
            name = name.upper()
            if name not in coaches:
                coaches[name] = c.execute(
                    "INSERT INTO coaches(name) VALUES (%s) ON CONFLICT (name) DO UPDATE SET name=EXCLUDED.name RETURNING id",
                    (name,)).fetchone()["id"]
            return coaches[name]

        for d in rows:
            code = d["CODE"]
            if code in seen:      # 1 người xuất hiện nhiều dòng (nhiều store): giữ dòng đầu
                skipped += 1
                continue
            seen.add(code)
            cid = coach_id(d.get("COACH"))
            scode = d.get("ESS STORE CODE")
            if scode:
                c.execute(
                    """INSERT INTO stores(code,name,customer,ka,region,province,coach_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, customer=EXCLUDED.customer,
                         ka=EXCLUDED.ka, region=EXCLUDED.region, province=EXCLUDED.province,
                         coach_id=COALESCE(EXCLUDED.coach_id, stores.coach_id)""",
                    (scode, d.get("STORE NAME") or scode, d.get("CUSTOMER"), d.get("KA"),
                     d.get("REGION"), d.get("PROVINCE"), cid))
                stores += 1
            c.execute(
                """INSERT INTO staff(code,ess_code,name,position,bu,category,store_code,coach_id,active)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (code) DO UPDATE SET ess_code=EXCLUDED.ess_code, name=EXCLUDED.name,
                     position=EXCLUDED.position, bu=EXCLUDED.bu, category=EXCLUDED.category,
                     store_code=EXCLUDED.store_code, coach_id=EXCLUDED.coach_id, active=EXCLUDED.active""",
                (code, d.get("ESS CODE"), d["NAME"].title(), d.get("POSITION"), d.get("BU"), d.get("CAT NAME"),
                 scode, cid, (d.get("TÌNH TRẠNG") or "").upper() != LEFT))
            staff += 1
    return {"staff": staff, "stores_rows": stores, "coaches": len(coaches), "duplicate_codes_skipped": skipped, "keyed_by_ess_code": by_ess}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Dùng: python -m app.importer <file.xlsx>")
    db.init()
    print(import_headcount(sys.argv[1]))
    db.close()
