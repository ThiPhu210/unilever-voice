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


def test_mot_ti_la_mot_ky():
    # ASR nghe "một ký" thành "một tí": không được tách thành một dòng hàng riêng khớp nhầm P/S Active Defense
    assert items("vậy mình chốt hai hazeline hương sữa gạo hoa nhài một tí giá 165.000") == [("HAZELINE-SUATAM-GAO-1KG", 2)]
    assert items("vậy mình chốt hai hazeline hương sữa gạo hoa nhài một tí giá 165 nghìn") == [("HAZELINE-SUATAM-GAO-1KG", 2)]


def test_gia_doc_lan_chu_so_va_chu():
    # Google/Siri trả "2 trăm lẻ 1 ngàn" (lẫn số và chữ) = 201.000đ, không phải 1.000đ
    def price(s):
        return parse_transcript("vậy mình chốt 1 sữa tắm hazeline 1kg " + s, CAT)["orders"][0]["items"][0]["price"]
    assert price("2 trăm lẻ 1 ngàn") == 201000
    assert price("2 trăm linh 1 ngàn") == 201000
    assert price("hai trăm lẻ 1 ngàn") == 201000
    assert price("3 trăm 50 nghìn") == 350000
    assert price("2 trăm mười ngàn") == 210000
    assert price("hai trăm lẻ một ngàn") == 201000   # cụm toàn chữ vẫn đúng như cũ


def test_google_viet_2010_000_la_201_nghin():
    # Siri/Google ghi "hai trăm lẻ một ngàn" thành "2010.000đ" (thừa số 0)
    t = ("dạ chị ơi em xin chốt cho mình một clear dầu gội gừng hoa cúc 350 g giá 75000đ hai clear dema ngăn gàu 300 g giá 273000đ "
         "một cái đề ma kiểm soát dầu 300 g giá 2010.000đ")
    prices = [i["price"] for i in parse_transcript(t, CAT)["orders"][0]["items"]]
    assert prices[-1] == 201000


def test_clear_bi_nghe_thanh_cai_ly():
    # Google nghe "một clear" thành "một cái ly": số lượng phải là 1, không lấy "9" trong "dầu gội 9 loại" làm số lượng
    t = "dạ chị ơi em xin chốt cho mình một cái ly dầu gội 9 loại thảo dược cổ truyền 350 g giá 185.000đ một clear dầu gội gừng hoa cúc 350 g giá 75000đ"
    r = [(i["sku_name"][:30], i["qty"], i["price"]) for i in parse_transcript(t, CAT)["orders"][0]["items"]]
    assert r[0][1:] == (1, 185000) and "9 Thảo Dược" in parse_transcript(t, CAT)["orders"][0]["items"][0]["sku_name"]
    assert r[1][1:] == (1, 75000)
