from app.parser import Catalog, parse_transcript

CAT = Catalog()


def items(text):
    return [(i["sku_id"], i["qty"]) for i in parse_transcript(text, CAT)["orders"][0]["items"]]


def test_sua_tam_khong_bi_doc_la_so_tam():
    assert items("vậy mình chốt 3 sữa tắm Hazeline sữa gạo hoa nhài 900g, 2 sữa tắm hazeline 1kg.") == [
        ("HAZELINE-SUATAM-GAO-900G", 3), ("HAZELINE-SUATAM-GAO-1KG", 2)]


def test_sua_tam_cu_van_dung():
    assert items("vậy mình chốt 2 sữa tắm lifebuoy 850g, 1 sữa tắm lux 850g.") == [
        ("LIFEBUOY-SG-850G", 2), ("LUX-SG-850G", 1)]


def test_tam_tram_gam_van_la_800g():
    assert items("vậy mình chốt hai omo tám trăm gam.")[0] == ("OMO-BOT-800G", 2)


def test_hazeline_duong_the():
    assert items("vậy mình chốt 2 Hazeline sữa dưỡng thể matcha lựu đỏ 370ml, 1 hazeline matcha 230ml.") == [
        ("HAZELINE-DUONGTHE-MATCHA-370ML", 2), ("HAZELINE-DUONGTHE-MATCHA-230ML", 1)]
