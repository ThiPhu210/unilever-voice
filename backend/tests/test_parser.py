import pytest
from app.parser import Catalog, parse_transcript
from app.parser.numbers import parse_number

CAT = Catalog()

# SKU còn trong sku_catalog.csv (sku_id trống trong CSV -> parser tự sinh slug từ tên)
OMO = "omo-bg-do-9kg"                                            # OMO BG đỏ 9kg
CLEAR_MEN = "clear-men-dau-goi-nuoc-hoa-warm-forest-350g"        # CLEAR MEN Dầu Gội Nước Hoa Warm Forest 350G
SUNSILK = "sunsilk-dau-goi-mem-muot-dieu-ky-170g"                # SUNSILK Dầu Gội Mềm Mượt Diệu Kỳ 170G
LIFEBUOY = "lifebuoy-sua-tam-than-hoat-tinh-cam-gao-270g"        # LIFEBUOY Sữa Tắm Than Hoạt Tính & Cám Gạo 270G
LUX = "lux-sua-tam-peaceful-galaxy-470g"                         # LUX Sữa Tắm Peaceful Galaxy 470G
KNORR_CKR = "knorr-gvhc-ca-kho-rieng-28g"                        # KNORR GVHC cá kho riềng 28g
HAZELINE_900G = "HAZELINE-SUATAM-GAO-900G"                       # sku_id khai báo sẵn trong CSV


def run(text):
    return parse_transcript(text, CAT)


def items(text, k=0):
    return [(i["sku_id"], i["qty"]) for i in run(text)["orders"][k]["items"]]


@pytest.mark.parametrize("words,expected", [
    ("muoi hai", 12), ("hai muoi lam", 25), ("hai muoi mot", 21),
    ("mot tram le nam", 105), ("ba muoi", 30), ("muoi", 10), ("7", 7),
])
def test_numbers(words, expected):
    toks = words.split()
    assert parse_number(toks, 0) == (expected, len(toks))


def test_template_chuan():
    r = run("Dạ em xin cảm ơn anh chị, vậy mình chốt 2 OMO bột giặt đỏ 9kg, 1 Clear Men nước hoa warm forest 350g. Dạ đúng rồi em.")
    assert r["closing_detected"]
    o = r["orders"][0]
    assert [(i["sku_id"], i["qty"]) for i in o["items"]] == [(OMO, 2), (CLEAR_MEN, 1)]
    assert o["customer_confirm"] == "yes"
    assert not o["needs_review"]


def test_so_bang_chu():
    assert items("Dạ em xin cảm ơn anh chị, vậy mình chốt hai omo bột giặt đỏ 9kg, ba sunsilk mềm mượt diệu kỳ 170g.") == [
        (OMO, 2), (SUNSILK, 3)]


def test_hai_muoi_lam():
    assert items("vậy mình chốt hai mươi lăm gói knorr cá kho riềng 28g.") == [(KNORR_CKR, 25)]


def test_loi_asr_chot_va_ten():
    assert items("Dạ em cảm ơn anh chị vậy mình chót 1 ô mô bột giặt đỏ 9kg") == [(OMO, 1)]


def test_khong_dau_khong_phay():
    assert items("vay minh chot 2 omo bot giat do 9kg 1 clear men nuoc hoa warm forest 350g 3 sunsilk mem muot dieu ky 170g") == [
        (OMO, 2), (CLEAR_MEN, 1), (SUNSILK, 3)]


def test_size_bang_chu():
    assert items("vậy mình chốt hai hazeline sữa gạo chín trăm gam, một comfort một phẩy hai lít.")[0] == (HAZELINE_900G, 2)


def test_nam_la_ten_khong_phai_so():
    # "năm" ở đây là số lượng 5. (Catalog mới không còn alias "clear nam", nên chỉ còn kiểm tra phần số.)
    assert items("vậy mình chốt hai dầu gội clear men nước hoa warm forest 350g, năm sunsilk mềm mượt diệu kỳ 170g.") == [
        (CLEAR_MEN, 2), (SUNSILK, 5)]


def test_khach_tu_choi():
    o = run("vậy mình chốt 1 sunsilk mềm mượt diệu kỳ 170g. Thôi để chị suy nghĩ thêm.")["orders"][0]
    assert o["customer_confirm"] == "no"


def test_khach_im_lang():
    assert run("vậy mình chốt 1 sunsilk mềm mượt diệu kỳ 170g.")["orders"][0]["customer_confirm"] == "none"


def test_khong_co_chot():
    assert run("Chào anh chị, bên em đang có khuyến mãi omo đỏ 9kg ạ")["closing_detected"] is False


def test_mo_ho_can_xac_nhan():
    # Thiếu dung tích: Sunsilk "mềm mượt diệu kỳ" có nhiều SKU (gội 170g/600g/850g, xả 600g) gần như hoà điểm
    o = run("vậy mình chốt 2 sunsilk mềm mượt diệu kỳ.")["orders"][0]
    assert o["needs_review"] and o["items"][0]["need_confirm"]
    assert len(o["items"][0]["candidates"]) == 3


def test_thieu_so_luong():
    i = run("vậy mình chốt Lifebuoy than hoạt tính cám gạo 270g.")["orders"][0]["items"][0]
    assert i["qty"] == 1 and i["qty_assumed"] and i["need_confirm"]


def test_nhieu_don_trong_mot_cuoc():
    r = run("vậy mình chốt 2 omo bột giặt đỏ 9kg. Dạ ok em. ... Dạ em cảm ơn chị, vậy mình chốt 1 sunsilk mềm mượt diệu kỳ 170g. Thôi chị ơi.")
    assert len(r["orders"]) == 2
    assert r["orders"][0]["customer_confirm"] == "yes"
    assert r["orders"][1]["customer_confirm"] == "no"
    assert r["orders"][1]["items"][0]["sku_id"] == SUNSILK


# ---------- giá SKU ({gia_sku} nghìn đồng) ----------
def prices(text, k=0):
    return [(i["sku_id"], i["qty"], i["price"]) for i in run(text)["orders"][k]["items"]]


def test_gia_mau_chuan():
    t = ("Dạ em xin cảm ơn anh chị, vậy mình chốt 2 OMO bột giặt đỏ 9kg 65 nghìn đồng, "
         "1 Clear Men nước hoa warm forest 350g 120 nghìn đồng. Dạ ok em.")
    assert prices(t) == [(OMO, 2, 65000), (CLEAR_MEN, 1, 120000)]
    o = run(t)["orders"][0]
    assert not o["missing_price"] and not o["needs_review"] and o["customer_confirm"] == "yes"


def test_gia_bang_chu():
    t = ("vậy mình chốt hai omo bột giặt đỏ 9kg sáu mươi lăm nghìn đồng, "
         "một clear men nước hoa warm forest 350g một trăm hai mươi nghìn đồng.")
    assert prices(t) == [(OMO, 2, 65000), (CLEAR_MEN, 1, 120000)]


def test_gia_dang_k_va_dau_cham():
    t = ("vậy mình chốt 3 sunsilk mềm mượt diệu kỳ 170g 65.000đ, "
         "2 lifebuoy than hoạt tính cám gạo 270g 85k, 1 lux peaceful galaxy 470g 99,000 đồng")
    assert prices(t) == [(SUNSILK, 3, 65000), (LIFEBUOY, 2, 85000), (LUX, 1, 99000)]


def test_gia_ruoi_va_le():
    assert prices("vậy mình chốt 2 omo bột giặt đỏ 9kg 65 nghìn rưỡi, 1 lux peaceful galaxy 470g sáu mươi nghìn hai trăm năm mươi") == [
        (OMO, 2, 65500), (LUX, 1, 60250)]


def test_quen_gia():
    r = run("vậy mình chốt 2 omo bột giặt đỏ 9kg, 1 clear men nước hoa warm forest 350g 120 nghìn đồng")["orders"][0]
    assert [i["price"] for i in r["items"]] == [None, 120000]
    assert r["missing_price"] and not r["needs_review"]


def test_gia_khong_nham_voi_so_luong():
    # "1" sau dấu phẩy là số lượng, "9"/"350" là dung tích sản phẩm, không có đơn vị tiền nên không bị coi là giá
    assert prices("vậy mình chốt 2 omo bột giặt đỏ 9kg, 1 clear men nước hoa warm forest 350g") == [
        (OMO, 2, None), (CLEAR_MEN, 1, None)]


def test_gia_co_chu_gia_va_khong_phay():
    t = "vậy mình chốt 2 omo bột giặt đỏ 9kg giá 65 nghìn đồng 1 clear men nước hoa warm forest 350g giá 120 nghìn đồng. Ok em"
    assert prices(t) == [(OMO, 2, 65000), (CLEAR_MEN, 1, 120000)]


def test_gia_la_dau_nam_van_la_ten():
    # "năm mươi nghìn" là giá 50.000, "năm sunsilk" là số lượng 5
    assert prices("vậy mình chốt hai dầu gội clear men nước hoa warm forest 350g năm mươi nghìn, năm sunsilk mềm mượt diệu kỳ 170g 40 nghìn") == [
        (CLEAR_MEN, 2, 50000), (SUNSILK, 5, 40000)]