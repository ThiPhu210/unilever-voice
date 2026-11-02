"""Test chạy trên PostgreSQL thật. Đặt TEST_DATABASE_URL (database RỖNG dùng riêng cho test, bị xoá sạch mỗi lần chạy).
Ví dụ: TEST_DATABASE_URL=postgresql://uv:uv@localhost:5432/uv_test pytest -q"""
import os
import tempfile

import pytest

URL = os.getenv("TEST_DATABASE_URL")
if not URL:
    pytest.exit("Cần đặt TEST_DATABASE_URL trỏ tới một database PostgreSQL dành riêng cho test", 2)
os.environ["DATABASE_URL"] = URL
os.environ["AUDIO_DIR"] = tempfile.mkdtemp()
os.environ.pop("API_KEY", None)

from app import db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    with db.pool().connection() as c:
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    from app import main
    main.startup()
    # 2 coach, 2 cửa hàng, 3 SA/BA mẫu
    with db.tx() as c:
        c.execute("INSERT INTO coaches(id,name) VALUES (1,'TRANG'),(2,'TƯỜNG LINH')")
        c.execute("""INSERT INTO stores(code,name,customer,coach_id) VALUES
            ('STR-A','Aeon Tan Phu','AEON',1),('STR-B','Coop Q7','COOP',2)""")
        c.execute("""INSERT INTO staff(code,name,position,store_code,coach_id) VALUES
            ('SA0001','Lan','SA BW','STR-A',1),('SA0002','Hoa','SA ORAL','STR-A',1),('SA0003','Minh','SA BPC','STR-B',2)""")
    yield
    db.close()
