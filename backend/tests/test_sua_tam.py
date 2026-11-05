from app.parser import Catalog, parse_transcript

CAT = Catalog()


def items(text):
    return [(i["sku_id"], i["qty"]) for i in parse_transcript(text, CAT)["orders"][0]["items"]]


def test_sua_tam_khong_bi_doc_la_so_tam():
    assert items("vậy mình chốt 3 sữa tắm Hazeline sữa gạo hoa nhài 900g 90 nghìn, 2 sữa tắm hazeline 1kg 100 nghìn.") == [
        ("HAZELINE-SUATAM-GAO-900G", 3), ("HAZELINE-SUATAM-GAO-1KG", 2)]


def test_sua_tam_cu_van_dung():
    assert items("vậy mình chốt 2 sữa tắm lifebuoy than hoạt tính cám gạo 270g 85 nghìn, 1 sữa tắm lux peaceful galaxy 470g 99 nghìn.") == [
        ("lifebuoy-sua-tam-than-hoat-tinh-cam-gao-270g", 2), ("lux-sua-tam-peaceful-galaxy-470g", 1)]


def test_tam_tram_gam_van_la_800g():
    # "tám trăm năm mươi gam" = 850g; "tám" (8) không được lẫn với "tắm" (bỏ dấu cùng thành "tam")
    assert items("vậy mình chốt hai sunsilk mềm mượt diệu kỳ tám trăm năm mươi gam 80 nghìn.")[0] == (
        "sunsilk-dau-goi-mem-muot-dieu-ky-850g", 2)


def test_hazeline_duong_the():
    assert items("vậy mình chốt 2 Hazeline sữa dưỡng thể matcha lựu đỏ 370ml 110 nghìn, 1 hazeline matcha 230ml 70 nghìn.") == [
        ("HAZELINE-DUONGTHE-MATCHA-370ML", 2), ("HAZELINE-DUONGTHE-MATCHA-230ML", 1)]
