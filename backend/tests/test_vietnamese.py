"""Model tiếng Việt (PhoWhisper) viết brand theo âm, giá và dung tích bằng chữ: parser vẫn phải ra đúng SKU / số lượng / giá."""
import pytest
from app.parser import Catalog, parse_transcript
from app.parser.normalize import normalize
from app.parser.numbers import parse_number
from app.parser.brands import num_to_vi, vi_text, asr_prompt, SCRIPT, BRAND_VI, _ALIAS_RULES
from app.parser.phonetics import fold, surface_variants
from app.parser.normalize import strip_accents
from app.asr import _resolve_model

CAT = Catalog()
CLEAR_MEN = "clear-men-dau-goi-nuoc-hoa-warm-forest-350g"
SUNSILK = "sunsilk-dau-goi-mem-muot-dieu-ky-170g"
LIFEBUOY = "lifebuoy-sua-tam-than-hoat-tinh-cam-gao-270g"
HAZELINE_900G = "HAZELINE-SUATAM-GAO-900G"


def one(text):
    orders = parse_transcript(text, CAT)["orders"]
    assert len(orders) == 1, orders
    return [(i["sku_id"], i["qty"], i["price"]) for i in orders[0]["items"]], orders[0]


def test_normalize_khong_sua_chu_thuong():
    """Brand đọc theo âm KHÔNG được thay trong transcript: 'do', 'bon', 'lạc', 'ác' là từ thường (do/đồ, bốn, lạc, ác)."""
    assert normalize("do đó bốn lạc ác ét lia") == "do do bon lac ac et lia"


def _spoken(name: str, reading: str) -> str:
    """Tên SKU (chuẩn hóa) với brand Latin được thay bằng cách đọc `reading` -> câu chốt đơn."""
    n = normalize(name)
    for rx, _ in _ALIAS_RULES:
        if rx.search(n):
            return f"hai {rx.sub(reading, n, count=1)} giá năm mươi nghìn đồng. Dạ ok em."
    raise AssertionError(f"không thấy brand trong {name}")


def _sku(prefix: str) -> str:
    return next(s["sku_id"] for s in CAT.skus.values() if s["name"].startswith(prefix))


# Các cách đọc người dùng nêu ra, mỗi cái một SKU thật trong catalog
@pytest.mark.parametrize("reading,name", [
    ("o mo", "OMO BG đỏ 9kg"),
    ("be et", "P/S KĐR Ngừa Sâu Răng Vượt Trội 230g"), ("pe et", "P/S KĐR Ngừa Sâu Răng Vượt Trội 230g"),
    ("bi et", "P/S KĐR Ngừa Sâu Răng Vượt Trội 230g"), ("pi et", "P/S KĐR Ngừa Sâu Răng Vượt Trội 230g"),
    ("lo sap", "CLOSEUP KĐR Bạc Hà Thơm Mát 140g"), ("lo sup", "CLOSEUP KĐR Bạc Hà Thơm Mát 140g"),
    ("co lo sap", "CLOSEUP KĐR Bạc Hà Thơm Mát 140g"), ("co lo sup", "CLOSEUP KĐR Bạc Hà Thơm Mát 140g"),
    ("lai boi", "LIFEBUOY Sữa Tắm Than Hoạt Tính"), ("do", "DOVE Dầu Gội CERAMIDE"), ("do vo", "DOVE Dầu Gội CERAMIDE"),
    ("san lai", "SUNLIGHT Nước Rửa Chén Chanh 9.5kg"), ("com pho", "COMFORT NXV Chuyên Dụng HNH Quyến Rũ 4.2L"),
    ("lia", "CLEAR Dầu Gội DERMA Kiểm Soát Dầu Nhờn 300G"), ("co lia", "CLEAR Dầu Gội DERMA Kiểm Soát Dầu Nhờn 300G"),
    ("san siu", "SUNSILK Dầu Gội Mềm Mượt Diệu Kỳ 170G"), ("tre se me", "TRESEMME dầu xả vào nếp mượt mà 340g"),
    ("ha gio lin", "Hazeline sữa dưỡng thể matcha"), ("ha do lin", "Hazeline sữa dưỡng thể matcha"), ("ha so lin", "Hazeline sữa dưỡng thể matcha"),
    ("va so lin", "VASELINE SDT Gluta-Hya"), ("va gio lin", "VASELINE SDT Gluta-Hya"),
    ("lut", "LUX Sữa Tắm Peaceful Galaxy 470G"), ("lac", "LUX Sữa Tắm Peaceful Galaxy 470G"),
    ("sop", "SURF Nước Giặt Chuyên Dụng Hương Nước Xả 9kg"), ("xop", "SURF Nước Giặt Chuyên Dụng Hương Nước Xả 9kg"),
])
def test_cach_doc_nguoi_dung_neu(reading, name):
    sku = next(s for s in CAT.skus.values() if s["name"].startswith(name))
    orders = parse_transcript(_spoken(sku["name"], reading), CAT)["orders"]
    assert [(i["sku_id"], i["qty"], i["price"]) for o in orders for i in o["items"]] == [(sku["sku_id"], 2, 50000)]


def _plain_of(v: str) -> str:
    return " ".join(strip_accents(v.lower()).split())


def test_moi_sku_x_moi_cach_doc_khop_nhu_viet_latin():
    """Với MỌI SKU trong catalog và MỌI cách đọc của brand đó: kết quả giống hệt khi đọc bằng tên Latin (bắt lỗi vỡ số lượng/tên do từ trùng số, liên từ, đơn vị...)."""
    bad, tested = [], 0
    for row in CAT.rows:
        n = normalize(row["name"])
        for rx, variants in _ALIAS_RULES:
            if not rx.search(n):
                continue
            exp = [(row["sku_id"], 2, 50000)]
            if _items(f"hai {n} giá năm mươi nghìn đồng. Dạ ok em.", CAT) != exp:
                continue    # tên SKU có số/chữ gây nhầm sẵn (vd "Từ Thịt", "RE0216"): lỗi có từ trước, không thuộc brand
            # Mọi cách nói lệch vùng miền SINH TỰ ĐỘNG từ cách đọc gốc (không phải danh sách viết tay)
            for v in dict.fromkeys(sv for base in variants for sv in surface_variants(_plain_of(base), limit=60)):
                if v.split()[0] in _NUMBER_WORDS:
                    continue    # "hai ba so lin" (Vaseline nói lệch v->b): "ba" là số 3 nên câu vốn mơ hồ, không phải lỗi khớp tên
                tested += 1
                got = _items(f"hai {rx.sub(v, n, count=1)} giá năm mươi nghìn đồng. Dạ ok em.", CAT)
                if got != exp:
                    bad.append((row["name"], v, got))
    assert tested > 250 and not bad, bad[:5]


_NUMBER_WORDS = {"khong", "mot", "hai", "ba", "bon", "nam", "sau", "bay", "tam", "chin", "muoi", "lam", "tu"}


def _items(text, cat):
    return [(i["sku_id"], i["qty"], i["price"]) for o in parse_transcript(text, cat)["orders"] for i in o["items"]]


@pytest.mark.parametrize("a,b", [
    ("xăn nai", "săn lai"), ("săn nai", "săn lai"), ("ha xo lin", "ha giô lin"), ("ha đô lin", "ha zo lin"),
    ("bê ét", "pê ét"), ("bi ét", "pi ét"), ("tre se mê", "che xe mê"), ("re xô na", "đê sô na"), ("bim", "vim"),
    ("com bo", "com phô"), ("xốp", "sốp"), ("bong", "pon"), ("quan", "oan"), ("lia", "lia"), ("lúc", "lút"),
])
def test_fold_gop_cac_cach_noi_vung_mien(a, b):
    assert fold(a) == fold(b)


@pytest.mark.parametrize("a,b", [("lai bôi", "săn lai"), ("sốp", "síp"), ("dầu gội", "dầu xả"), ("cờ lia", "clo súp")])
def test_fold_khong_gop_nham_tu_khac_nhau(a, b):
    assert fold(a) != fold(b)


def test_nguoi_noi_giong_vung_mien_van_ra_dung_sku():
    """Cách nói lệch CHƯA từng được ghi ở đâu (tự nghĩ ra theo quy luật vùng miền) vẫn ra đúng SKU."""
    gia = "giá năm mươi nghìn đồng. Dạ ok em."
    cases = [
        (f"hai xăn xiu dầu gội mềm mượt diệu kỳ một trăm bảy mươi gam {gia}", SUNSILK),
        (f"hai lăn lai nước rửa chén chanh chín phẩy năm ki lô gam {gia}", "sunlight-nuoc-rua-chen-chanh-9.5kg"),
        (f"hai nai bôi sữa tắm than hoạt tính cám gạo hai trăm bảy mươi gam {gia}", LIFEBUOY),
        (f"hai sữa tắm ha xô lình fragrance hương sữa gạo hoa nhài chín trăm gam {gia}", HAZELINE_900G),
    ]
    for text, sku in cases:
        assert [i[0] for i in _items_flat(text)] == [sku], text


def _items_flat(text):
    return [(i["sku_id"], i["qty"], i["price"]) for o in parse_transcript(text, CAT)["orders"] for i in o["items"]]


def test_brand_chua_co_trong_catalog(tmp_path):
    """Axe, Pond's, Rexona, Cif, Vim, Wall's chưa có SKU thật: dùng catalog tạm. Gồm 'pi ét' (P/S) khác 'ét' (Axe) và 'bon' (Pond's) không bị đọc thành số 4."""
    f = tmp_path / "c.csv"
    f.write_text("name,aliases\n" + "\n".join(f"{n}," for n in [
        "AXE Xịt Toàn Thân Dark Temptation 150ml", "P/S KĐR Ngừa Sâu Răng 150g", "Pond's Kem Dưỡng Trắng Da Ban Đêm 50g",
        "Rexona Lăn Khử Mùi Nam 50ml", "Cif Kem Tẩy Rửa Đa Năng 690g", "Vim Nước Tẩy Bồn Cầu 880ml", "Wall's Kem Cornetto 60g"]) + "\n", encoding="utf-8")
    cat = Catalog(str(f))
    ten = lambda t: [(i["sku_name"].split()[0], i["qty"], i["price"]) for o in parse_transcript(t, cat)["orders"] for i in o["items"]]
    gia = "giá năm mươi nghìn đồng. Dạ ok em."
    assert ten(f"hai ét xịt toàn thân dark temptation 150ml {gia}") == [("AXE", 2, 50000)]
    assert ten(f"hai pi ét kđr ngừa sâu răng 150g {gia}") == [("P/S", 2, 50000)]
    assert ten(f"hai bon kem dưỡng trắng da ban đêm 50g {gia}") == [("Pond's", 2, 50000)]
    assert ten(f"ba re xo na lăn khử mùi nam 50ml {gia}")[0][0] == "Rexona"
    assert ten(f"một xíp kem tẩy rửa đa năng 690g {gia}")[0][0] == "Cif"
    assert ten(f"một vim nước tẩy bồn cầu 880ml {gia}") == [("Vim", 1, 50000)]   # "bồn" không bị đọc thành số 4
    assert ten(f"hai oan kem cornetto 60g {gia}")[0][0] == "Wall's"


def test_va_sau_so_luong_la_ten_hang():
    items, _ = one("Mình chốt hai va so lin sdt gluta hya dưỡng da sáng rạng rỡ ba trăm mi li lít giá một trăm nghìn đồng. Ok.")
    assert items[0][1] == 2          # "va" không phải liên từ "và" làm rớt số lượng


@pytest.mark.parametrize("spoken,expected", [
    ("chín ki lô gam", "chin kg"),
    ("ba phẩy tám ki lô gam", "3.8kg"),
    ("bốn phẩy hai lít", "4.2lit"),
    ("ba trăm bảy mươi mi li lít", "ba tram bay muoi ml"),
    ("một ki lô", "mot kg"),
])
def test_don_vi_bang_chu(spoken, expected):
    assert normalize(spoken) == expected


@pytest.mark.parametrize("n", range(1, 1000))
def test_num_to_vi_doc_nguoc_lai_dung(n):
    toks = normalize(num_to_vi(n)).split()
    assert parse_number(toks, 0) == (n, len(toks))


def test_cau_chot_don_bang_chu_clear():
    items, o = one("Dạ em xin cảm ơn anh chị, vậy mình chốt hai chai dầu gội cờ lia men nước hoa warm forest "
                   "ba trăm năm mươi gam giá một trăm hai mươi nghìn đồng. Dạ đúng rồi em.")
    assert items == [(CLEAR_MEN, 2, 120000)]
    assert o["customer_confirm"] == "yes"


def test_cau_chot_don_surf_chin_ki_lo_gam():
    items, _ = one("Vậy mình chốt một can nước giặt sốp chuyên dụng hương nước xả chín ki lô gam giá sáu mươi lăm nghìn đồng. Ok em.")
    assert [(q, p) for _, q, p in items] == [(1, 65000)] and items[0][0].startswith("surf-nuoc-giat-chuyen-dung")


def test_cau_chot_don_nhieu_dong_nhieu_brand():
    items, _ = one("Dạ mình chốt ba chai sữa tắm lai bôi than hoạt tính cám gạo hai trăm bảy mươi gam giá bốn mươi lăm nghìn đồng, "
                   "một chai dầu gội săn siu mềm mượt diệu kỳ một trăm bảy mươi gam giá năm mươi lăm nghìn đồng. Dạ được em.")
    assert items == [(LIFEBUOY, 3, 45000), (SUNSILK, 1, 55000)]


def test_hazeline_chin_tram_gam():
    items, _ = one("Mình chốt hai sữa tắm ha giô lin fragrance hương sữa gạo hoa nhài chín trăm gam giá chín mươi nghìn đồng. Ok.")
    assert items[0][:2] == (HAZELINE_900G, 2) and items[0][2] == 90000


def test_van_nhan_kieu_cu_chu_so_va_brand_latin():
    items, _ = one("Dạ em xin cảm ơn anh chị, vậy mình chốt 2 Clear Men nước hoa warm forest 350g 120 nghìn đồng. Dạ đúng rồi em.")
    assert items == [(CLEAR_MEN, 2, 120000)]


def test_hotwords_va_prompt_bang_tieng_viet():
    hw = CAT.hotwords()
    assert "cờ lia" in hw and "lai bôi" in hw and "pi ét" in hw and "CLEAR" not in hw and "LIFEBUOY" not in hw and "P/S" not in hw
    assert "gam" in hw and "350G" not in hw
    p = asr_prompt(hw)
    assert p.endswith(SCRIPT)                       # Whisper giữ phần CUỐI của prompt -> câu mẫu phải nằm cuối
    assert all(v[0] in p for v in BRAND_VI.values())
    assert len(p) < 800


def test_vi_text_khong_dong_vao_ma_hang():
    assert vi_text("SURF BG HNXV ngát hương xuân RE0216 18X800G") == "sốp BG HNXV ngát hương xuân RE0216 18X800G"
    assert vi_text("CLEAR 300G, Hazeline 370ml, COMFORT 1LX 1.2L") == \
        "cờ lia ba trăm gam, ha giô lin ba trăm bảy mươi mi li lít, com phót 1LX một phẩy hai lít"
    assert vi_text("P/S KĐR 230g; CLOSEUP 140g; Pond's 50g") == "pi ét KĐR hai trăm ba mươi gam; clo súp một trăm bốn mươi gam; pon năm mươi gam"


@pytest.mark.parametrize("env,expected", [
    ("medium", "nunu-willump/PhoWhisper-medium-ct2"), ("large-v3", "kiendt/PhoWhisper-large-ct2"),
    ("Systran/faster-whisper-medium", "Systran/faster-whisper-medium"),
])
def test_alias_model_cu(env, expected):
    assert _resolve_model(env) == expected


# ---------- Transcript thật (PhoWhisper, giọng lệch): từng lỗi phát hiện ở đây đều có test riêng ----------
REAL_1 = ("bún kem đánh răng bê ép ngừa sâu răng vượt trội một trăm gam giá sáu chục ngàn một lia dầu gội đề mang đặc trị rào hai trăm gam "
          "giá tám mươi ba ngàn ba nước lau sàng sơn lai tinh dầu phảo mộc viên vĩ bạch đèn một ký giá một trăm hai mươi sáu ngàn hai sữa tấm "
          "lúa gà la si bốn trăm bảy mươi gam giá bảy bảy ngàn một sữa duyên thể hazard mắt da liu đỏ hai trăm ba mươi miu giá một trăm lẻ ba ngàn.")


def test_transcript_that_du_5_dong():
    got = [(i["sku_name"].split()[0], i["qty"], i["price"]) for o in parse_transcript(REAL_1, CAT)["orders"] for i in o["items"]]
    assert got == [("P/S", 4, 60000), ("CLEAR", 1, 83000), ("SUNLIGHT", 3, 126000), ("LUX", 2, 77000), ("Hazeline", 1, 103000)]
    sizes = [i["sku_name"].split()[-1].lower() for o in parse_transcript(REAL_1, CAT)["orders"] for i in o["items"]]
    assert sizes == ["100g", "200g", "1kg", "470g", "230ml"]


@pytest.mark.parametrize("spoken,vnd", [
    ("bảy bảy ngàn", 77000), ("bảy bảy nghìn đồng", 77000), ("tám ba ngàn", 83000), ("một trăm hai sáu ngàn", 126000),
    ("sáu chục ngàn", 60000), ("sáu chục nghìn", 60000), ("sáu mươi ngàn", 60000), ("một trăm lẻ ba ngàn", 103000),
    ("bảy mươi bảy nghìn", 77000), ("chín chục nghìn đồng", 90000),
])
def test_gia_doc_nhieu_kieu(spoken, vnd):
    from app.parser.prices import parse_price
    toks = normalize(spoken).split()
    assert parse_price(toks, 0)[0] == vnd


@pytest.mark.parametrize("spoken", ["hai trăm ba mươi mi li lít", "hai trăm ba mươi miu", "hai trăm ba mươi mi li", "hai trăm ba mươi ml"])
def test_ml_doc_nhieu_kieu(spoken):
    assert normalize(spoken) == "hai tram ba muoi ml"


def test_bon_tram_la_so_con_bon_kem_la_brand():
    items, _ = one("Dạ mình chốt hai sữa tắm lúa galaxy bốn trăm bảy mươi gam giá bảy bảy ngàn. Ok em.")
    assert items[0][0].startswith("lux-") and items[0][1:] == (2, 77000)


REAL_2 = ("một ô môn nước giặt cửa trên ba ký chính giá chín lăm ngàn một nước súc miệng bê ép ăc tiêu đi phen năm trăm miêu giá bảy mươi ba ngàn "
          "một kem đánh răng cờ lô súp thơ mát lộc đề một trăm bốn mươi gam giá ba chín ngàn một kem dưỡng phục hồi sim bồ bồ sê ra mai năm trăm miêu "
          "giá một trăm bốn mươi ngàn hai sen lai viên rửa chén mười bốn trong một giá bốn hai ngàn.")


def test_transcript_that_so_2():
    items = [i for o in parse_transcript(REAL_2, CAT)["orders"] for i in o["items"]]
    assert [(i["sku_name"].split()[0], i["qty"], i["price"]) for i in items] == [
        ("OMO", 1, 95000), ("NSM", 1, 73000), ("KĐR", 1, 39000), ("SIMPLE", 1, 140000), ("SUNLIGHT", 2, 42000)]
    assert items[0]["sku_name"].endswith("3.9kg")
    assert items[3]["need_confirm"]            # "năm trăm miêu" nhưng SKU là 50ml: lệch bậc 10 -> phải để người xác nhận
    assert not items[0]["need_confirm"]


@pytest.mark.parametrize("spoken,out", [
    ("ba ký chín", "3.9kg"), ("ba ký chính", "3.9kg"), ("ba ki lô chín", "3.9kg"), ("hai ký rưỡi chai", None),
    ("một ký chín mươi nghìn", None), ("ba ký chín giá", "3.9kg gia"), ("năm trăm miêu", "nam tram ml"), ("năm trăm miu", "nam tram ml"),
])
def test_ky_la_dau_phay_va_mieu(spoken, out):
    got = normalize(spoken)
    if out is None:
        assert "3.9" not in got and "9kg" not in got
    else:
        assert got == out


def test_so_chu_nam_trong_ten_sku():
    items, _ = one("hai sen lai viên rửa chén mười bốn trong một giá bốn hai ngàn. Ok.")
    assert items[0][0].startswith("sunlight-vien-rua-chen") and items[0][1:] == (2, 42000)


def test_dove_dau_xa_tam_la_tram_va_mi_mit():
    """'hai tăm mười bảy ngàn' = 217k ('tăm' = trăm, không phải tám); 'mi mít' = ml; catalog ghi 610g nhưng khách nói ml."""
    items, o = one("Một dầu xả đô mắc cha hoa anh đào sáu trăm mười mi mít giá hai tăm mười bảy ngàn")
    assert items == [("dove-dau-xa-matcha-hoa-anh-dao-610g", 1, 217000)] or items[0][1:] == (1, 217000)
    assert items[0][0].startswith("dove-dau-xa-matcha")


@pytest.mark.parametrize("spoken,vnd", [
    ("hai tăm mười bảy ngàn", 217000), ("hai tăm ba mươi nghìn", 230000), ("một tăm lẻ ba ngàn", 103000),
    ("hai trăm mười bảy ngàn", 217000), ("tám mươi bảy ngàn", 87000),
])
def test_gia_tam_la_tram(spoken, vnd):
    from app.parser.prices import parse_price
    assert parse_price(normalize(spoken).split(), 0)[0] == vnd


def test_tam_muoi_van_la_80():
    """Không phá cách đọc thường: 'tám mươi' (80) và 'hai tám mươi' không bị đổi nếu không đủ ngữ cảnh giá."""
    assert parse_number(normalize("tám mươi bảy").split(), 0) == (87, 3)


REAL_3 = ("dạ em xin cám ơn chị vậy mình chốt bốn kem đánh răng bề ngôi sau răng vượt trội một trăm gam giá sáu chục ngàn một dâu gội lia đê ma đặc trị gàu "
          "hai trăm gam giá năm mươi ba ngàn ba sinh lai nước lau sàng tinh dầu thảo mộc viên vị bạch đàn một ký giá một trăm hai mươi sáu ngàn hai sữa tấm lắc "
          "gà la xi bốn trăm báy mươi gam giá báy mươi bảy ngàn và một hazard sữa dưỡng thểy mắt da lụi đỏ hai trăm ba mươi lít giá một trăm lẻ ba ngàn")


def test_transcript_that_so_3_loi_mo_dau_va_hazard():
    items = [i for o in parse_transcript(REAL_3, CAT)["orders"] for i in o["items"]]
    assert [(i["sku_name"].split()[0], i["qty"], i["price"]) for i in items] == [
        ("P/S", 4, 60000), ("CLEAR", 1, 53000), ("SUNLIGHT", 3, 126000), ("LUX", 2, 77000), ("Hazeline", 1, 103000)]
    assert not items[0]["need_confirm"]
    assert items[4]["need_confirm"]            # "230 lít" cho SKU 230ml: lệch đơn vị 1000 lần -> để người xác nhận


@pytest.mark.parametrize("opener", ["dạ em xin cảm ơn chị vậy mình chốt", "dạ vâng", "ok em lấy", "dạ chị cho em"])
def test_loi_mo_dau_khong_nuot_so_luong_bon(opener):
    items, _ = one(f"{opener} bốn kem đánh răng ps ngừa sâu răng vượt trội một trăm gam giá sáu chục ngàn")
    assert items and items[0][1:] == (4, 60000)


def test_bon_van_la_brand_khi_dang_do_ten_hang():
    items, _ = one("hai bon kem dưỡng da một trăm gam giá bảy mươi ngàn")   # "bon" sau số lượng vẫn là Pond's, không bị ăn thành số
    assert items == [] or items[0][1] == 2


REAL_4 = ("ờ dậy em bỏ giỏ hàng bốn kem đánh răng ps ngừa sâu răng vượt trội một trăm gam giá sáu chục ngàn một dầu gội lia đê ma đặt chạy vào hai trăm gam "
          "giá tám mươi ba ngàn ba nước lau sàng sinh lai tinh dâu hở một viên vỉ bạch đà một ký giá một trăm hai mươi sáu ngàn hai sữa tắm lắc ga lơ xi bốn trăm "
          "bảy mươi gam giá bảy mươi bảy ngàn và một sữa diễn thể hazard mắc da lụi đỏ hai trăm ba mươi miu. giá một trăm lẻ ba nghìn. . cảm ơn và hẹn gặp lại.")


def test_transcript_that_so_4_mo_dau_gio_hang_gia_tach_cau_chu_vo():
    items = [i for o in parse_transcript(REAL_4, CAT)["orders"] for i in o["items"]]
    assert [(i["sku_name"].split()[0], i["qty"], i["price"]) for i in items] == [
        ("P/S", 4, 60000), ("CLEAR", 1, 83000), ("SUNLIGHT", 3, 126000), ("LUX", 2, 77000), ("Hazeline", 1, 103000)]
    assert items[0]["sku_name"].endswith("100g") and not items[0]["qty_assumed"]


def test_gia_nam_o_cau_rieng_sau_dau_cham():
    items, _ = one("hai sữa tắm lắc ga la xi bốn trăm bảy mươi gam. giá bảy mươi bảy ngàn. Ok em.")
    assert items[0][1:] == (2, 77000)


def test_gia_cau_rieng_khong_nuot_cau_khac():
    """Câu 'giá hơi cao' (không phải một mức giá) không bị dính vào dòng hàng."""
    r = parse_transcript("hai sữa tắm lắc ga la xi bốn trăm bảy mươi gam giá bảy mươi bảy ngàn. giá hơi cao đó em. ok em", CAT)
    assert r["orders"][0]["items"][0]["price"] == 77000 and r["orders"][0]["customer_confirm"] == "yes"


@pytest.mark.parametrize("reply", [
    "okay em", "lấy đi em", "ừ", "chốt", "chốt em", "dạ chốt", "ừ chốt đơn", "rồi em", "ờ rồi", "ô kê em", "vâng", "ừm lấy luôn", "đồng ý", "ốc kê em",
])
def test_khach_chot_don_dong_y(reply):
    r = parse_transcript(f"mình chốt hai sữa tắm lắc ga la xi bốn trăm bảy mươi gam giá bảy mươi bảy ngàn. {reply}", CAT)
    assert r["orders"][0]["customer_confirm"] == "yes", reply


@pytest.mark.parametrize("reply", ["không em", "hông em", "thôi em không lấy", "ừ thôi để lần sau", "vâng để em suy nghĩ", "chưa em", "khoan đã"])
def test_khach_tu_choi(reply):
    r = parse_transcript(f"mình chốt hai sữa tắm lắc ga la xi bốn trăm bảy mươi gam giá bảy mươi bảy ngàn. {reply}", CAT)
    assert r["orders"][0]["customer_confirm"] == "no", reply


@pytest.mark.parametrize("reply", ["bên em có khuyến mãi không", "giảm thêm được không em", "giá hơi cao đó em"])
def test_cau_hoi_khong_phai_chot_hay_tu_choi(reply):
    r = parse_transcript(f"mình chốt hai sữa tắm lắc ga la xi bốn trăm bảy mươi gam giá bảy mươi bảy ngàn. {reply}", CAT)
    assert r["orders"][0]["customer_confirm"] == "none", reply


# ---------- Lời mở đầu / xã giao bất kỳ đứng trước dòng hàng đầu tiên: "bốn/năm/sáu" vẫn là SỐ LƯỢNG ----------
_OPENERS = [
    "ờ dậy em bỏ giỏ hàng cho chị", "dạ vậy mình chốt", "dạ em cảm ơn chị vậy em bỏ giỏ hàng cho mình", "dạ vâng em cảm ơn chị",
    "dạ vậy em xin phép chốt đơn cho chị nha", "ok vậy em lên đơn cho chị nhé", "vậy chị lấy giúp em", "dạ chị cho em đặt",
    "dạ vậy em ghi lại đơn của chị nha", "dạ vậy em lên đơn cho mình như sau", "dạ em xin xác nhận lại đơn hàng của chị", "dạ chị ơi em đọc lại đơn nha",
    "dạ thôi mình lấy", "vâng vâng em ghi nhận", "ờ thôi em chốt", "à dạ em hiểu rồi vậy chị lấy", "dạ em tư vấn xong rồi thì chị chốt giúp em",
    "dạ em cảm ơn chị đã ủng hộ bên em ạ vậy mình lên đơn nha", "vậy giờ em chốt cho chị món đầu tiên là", "dạ bên em ghi nhận đơn hàng của chị gồm có",
    "alo dạ em nghe ạ vâng vậy chị đặt", "dạ tổng đơn của chị em đọc lại như sau", "thế thì cho em chốt luôn cho chị nhé",
]
_BODIES = [
    ("bốn kem đánh răng ps ngừa sâu răng vượt trội một trăm gam giá sáu chục ngàn", "P/S", 4, 60000),
    ("năm sữa tắm lắc gà la xi bốn trăm bảy mươi gam giá bảy mươi bảy ngàn", "LUX", 5, 77000),
    ("sáu nước lau sàn sunlight tinh dầu thảo mộc hương bạch đàn một ký giá một trăm hai mươi sáu ngàn", "SUNLIGHT", 6, 126000),
]


@pytest.mark.parametrize("opener", _OPENERS)
@pytest.mark.parametrize("body,brand,qty,price", _BODIES)
def test_loi_mo_dau_bat_ky_khong_nuot_so_luong(opener, body, brand, qty, price):
    r = parse_transcript(f"{opener} {body}.", CAT)
    got = [(i["sku_name"].split()[0], i["qty"], i["price"]) for o in r["orders"] for i in o["items"]]
    assert got == [(brand, qty, price)], opener


@pytest.mark.parametrize("text,qty,assumed", [
    ("hai kem đánh răng ps ngừa sâu răng vượt trội một trăm gam giá sáu chục ngàn", 2, False),
    ("dạ em chốt một kem đánh răng ps ngừa sâu răng vượt trội một trăm gam giá sáu chục ngàn", 1, False),
    ("kem đánh răng ps ngừa sâu răng vượt trội một trăm gam giá sáu chục ngàn", 1, True),      # không nói số lượng -> giả định 1 + cần xác nhận
    ("hai dầu gội clear nam bạc hà hai trăm gam giá tám mươi ba ngàn", 2, False),
])
def test_bon_nam_sau_nam_trong_ten_hang_van_la_chu(text, qty, assumed):
    """'ngừa SÂU răng', 'clear NAM' nằm GIỮA tên hàng: không bị lời mở đầu logic cướp thành số lượng."""
    items = [i for o in parse_transcript(text + ".", CAT)["orders"] for i in o["items"]]
    assert len(items) == 1 and items[0]["qty"] == qty and items[0]["qty_assumed"] == assumed


def test_tu_chi_la_so_sau_muoi():
    assert parse_number(normalize("hai mươi tư").split(), 0) == (24, 3)
    assert parse_number(normalize("tư vấn").split(), 0) is None
