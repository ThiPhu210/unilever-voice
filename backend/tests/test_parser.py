import pytest
from app.parser import Catalog, parse_transcript
from app.parser.numbers import parse_number

CAT = Catalog()


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
    r = run("Dạ em xin cảm ơn anh chị, vậy mình chốt 2 OMO bột giặt 800g, 1 Clear Men 650ml. Dạ đúng rồi em.")
    assert r["closing_detected"]
    o = r["orders"][0]
    assert [(i["sku_id"], i["qty"]) for i in o["items"]] == [("OMO-BOT-800G", 2), ("CLEAR-MEN-650ML", 1)]
    assert o["customer_confirm"] == "yes"
    assert not o["needs_review"]


def test_so_bang_chu():
    assert items("Dạ em xin cảm ơn anh chị, vậy mình chốt hai omo 800g, ba sunsilk 650ml.") == [
        ("OMO-BOT-800G", 2), ("SUNSILK-650ML", 3)]


def test_hai_muoi_lam():
    assert items("vậy mình chốt hai mươi lăm gói hạt nêm knorr 400g.") == [("KNORR-HATNEM-400G", 25)]


def test_loi_asr_chot_va_ten():
    assert items("Dạ em cảm ơn anh chị vậy mình chót 1 ô mô 3kg") == [("OMO-BOT-3KG", 1)]


def test_khong_dau_khong_phay():
    assert items("vay minh chot 2 omo 800g 1 clear men 650ml 3 sunlight 750g") == [
        ("OMO-BOT-800G", 2), ("CLEAR-MEN-650ML", 1), ("SUNLIGHT-CHEN-750G", 3)]


def test_size_bang_chu():
    assert items("vậy mình chốt hai omo tám trăm gam, một comfort một phẩy sáu lít.")[0] == ("OMO-BOT-800G", 2)


def test_nam_la_ten_khong_phai_so():
    assert items("vậy mình chốt hai dầu gội clear nam 650ml, năm sunsilk 650ml.") == [
        ("CLEAR-MEN-650ML", 2), ("SUNSILK-650ML", 5)]


def test_khach_tu_choi():
    o = run("vậy mình chốt 1 comfort 1.6l. Thôi để chị suy nghĩ thêm.")["orders"][0]
    assert o["customer_confirm"] == "no"


def test_khach_im_lang():
    assert run("vậy mình chốt 1 comfort 1.6l.")["orders"][0]["customer_confirm"] == "none"


def test_khong_co_chot():
    assert run("Chào anh chị, bên em đang có khuyến mãi omo 800g ạ")["closing_detected"] is False


def test_mo_ho_can_xac_nhan():
    o = run("vậy mình chốt 2 omo.")["orders"][0]
    assert o["needs_review"] and o["items"][0]["need_confirm"]
    assert len(o["items"][0]["candidates"]) == 3


def test_thieu_so_luong():
    i = run("vậy mình chốt Lifebuoy 90g.")["orders"][0]["items"][0]
    assert i["qty"] == 1 and i["qty_assumed"] and i["need_confirm"]


def test_nhieu_don_trong_mot_cuoc():
    r = run("vậy mình chốt 2 omo 800g. Dạ ok em. ... Dạ em cảm ơn chị, vậy mình chốt 1 dove 640ml. Thôi chị ơi.")
    assert len(r["orders"]) == 2
    assert r["orders"][0]["customer_confirm"] == "yes"
    assert r["orders"][1]["customer_confirm"] == "no"
    assert r["orders"][1]["items"][0]["sku_id"] == "DOVE-640ML"
