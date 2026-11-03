"""Nạp dữ liệu tổ chức (SR, cửa hàng, SA/BA) từ file headcount Excel vào database.

Chạy:  DATABASE_URL=postgresql://... python -m scripts.import_headcount /đường/dẫn/file.xlsx
(chạy trong thư mục backend/). Chạy lại nhiều lần an toàn (upsert).
Cố ý BỎ QUA: CCCD, ngày sinh, SĐT, email, địa chỉ, MST, BHXH, lương.
"""
import sys
import warnings
from datetime import date, datetime

import openpyxl

from app import db

SHEET = "Danh Sách Nhân Viên"
warnings.filterwarnings("ignore")


def s(v):
    v = None if v is None else str(v).replace("\xa0", " ").strip()
    return v or None


def d(v):
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    return None


def main(path: str):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows = list(wb[SHEET].iter_rows(values_only=True))
    hdr = [(h or "").strip() for h in rows[3]]
    col = {h: i for i, h in enumerate(hdr)}  # header trùng tên: lấy cột đầu tiên
    for h in reversed(hdr):
        col[h] = hdr.index(h)

    def g(r, name):
        return r[col[name]] if name in col and col[name] < len(r) else None

    db.init()
    now = db.now_str()
    n_sr = n_store = n_staff = skipped = 0
    for r in rows[4:]:
        ess, name = s(g(r, "ESS CODE")), s(g(r, "NAME"))
        sr, store = s(g(r, "ESS CODE SR")), s(g(r, "ESS STORE CODE"))
        region = s(g(r, "REGION"))
        if sr:
            db.execute(
                "INSERT INTO supervisors(ess_code,name,om_code,om_name,fc_name,region) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(ess_code) DO UPDATE SET name=excluded.name, om_code=excluded.om_code, "
                "om_name=excluded.om_name, fc_name=excluded.fc_name, region=excluded.region",
                (sr, s(g(r, "SR")), s(g(r, "OM CODE")), s(g(r, "OM")), s(g(r, "FC")), region))
            n_sr += 1
        if store:
            db.execute(
                "INSERT INTO stores(ess_store_code,name,region,province,key_account,customer,sr_ess_code) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(ess_store_code) DO UPDATE SET name=excluded.name, "
                "region=excluded.region, province=excluded.province, key_account=excluded.key_account, "
                "customer=excluded.customer, sr_ess_code=excluded.sr_ess_code",
                (store, s(g(r, "STORE NAME")), region, s(g(r, "PROVINCE")), s(g(r, "KA")),
                 s(g(r, "CUSTOMER")), sr))
            n_store += 1
        if not (ess and name):
            skipped += 1
            continue
        db.execute(
            "INSERT INTO staff(ess_code,ba_code,name,position,level,bu,category,contract_status,work_status,"
            "joined_at,left_at,store_code,sr_ess_code,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(ess_code) DO UPDATE SET ba_code=excluded.ba_code, name=excluded.name, "
            "position=excluded.position, level=excluded.level, bu=excluded.bu, category=excluded.category, "
            "contract_status=excluded.contract_status, work_status=excluded.work_status, "
            "joined_at=excluded.joined_at, left_at=excluded.left_at, store_code=excluded.store_code, "
            "sr_ess_code=excluded.sr_ess_code, updated_at=excluded.updated_at",
            (ess, s(g(r, "BA CODE")), name, s(g(r, "POSITION")), s(g(r, "LEVEL")), s(g(r, "BU")),
             s(g(r, "CAT NAME")), s(g(r, "STATUS")), s(g(r, "TÌNH TRẠNG")),
             d(g(r, "NGÀY VÀO AN HÒA")) or d(g(r, "NGÀY VÀO UNI")), d(g(r, "NGÀY NGHỈ VIỆC")),
             store, sr, now))
        n_staff += 1
    print(f"OK: {n_staff} nhân viên, {n_store} dòng cửa hàng, {n_sr} dòng SR (bỏ qua {skipped} dòng thiếu mã/tên)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
