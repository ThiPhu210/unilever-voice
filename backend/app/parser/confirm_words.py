"""Từ khoá khách xác nhận (YES) / từ chối (NO) sau câu chốt đơn.

Viết KHÔNG DẤU, chữ thường (text đã qua normalize: đ->d, bỏ dấu). Mỗi phần tử là một regex nhỏ;
cụm nhiều từ viết cách nhau bằng dấu cách. Muốn bổ sung chỉ cần thêm vào danh sách, rồi chạy `pytest tests/test_confirm.py`.

Quy tắc quyết định (core.detect_customer_confirm): từ khoá nào xuất hiện TRƯỚC thì thắng.
Lưu ý: bỏ dấu làm "đúng"/"dùng", "lấy"/"lẩy"... trùng nhau, nên các từ dễ trùng chỉ nhận khi đi kèm từ khác
(vd "dung roi", hoặc "dung" đứng cuối câu).
"""
import re

# Cụm "nghe như từ chối" nhưng thực ra là đồng ý -> đổi thành "ok" TRƯỚC khi dò YES/NO.
YES_OVERRIDES = [
    r"(khong|hong|ko|hem) (sao|van de|co gi|thanh van de|sai|nham|dat|mac)",
    r"thoi (duoc|cung duoc|lay|mua|ok|oke|vay di|cung ok)",
    r"cung (duoc|ok|oke|okay)",
]

YES = [
    # đồng ý trực tiếp
    r"dung roi", r"dung r", r"dung vay", r"dung do", r"dung a", r"dung nhu vay", r"dung het",
    r"dung(?=[.,!?;]|$)",                      # "Đúng." / "Đúng ạ" ("dung" đứng một mình, tránh "dùng")
    r"chinh xac", r"chuan roi", r"chuan luon", r"chuan",
    r"ok", r"oke", r"okay", r"okie", r"okela", r"o ke", r"o k", r"oc ke", r"o kay", r"au kay", r"o key", r"au ke", r"yes", r"yeah",
    r"dong y", r"nhat tri", r"hop ly",
    r"vang", r"vang a", r"u", r"uh", r"uhm", r"um", r"umm", r"uk", r"uh huh",
    r"duoc roi", r"duoc do", r"duoc luon", r"duoc a", r"duoc nhe", r"duoc nha", r"duoc",
    r"on roi", r"on ap", r"tot roi", r"tot qua",
    r"vay di", r"the di", r"nhu vay di", r"nhu vay nhe", r"nhu vay nha", r"vay nha",
    # chủ động mua / chốt
    r"lay", r"lay luon", r"lay di", r"mua", r"mua luon", r"mua di", r"chot luon", r"chot di",
    r"dat luon", r"dat hang", r"goi (giup|gium|lai|luon)", r"boc (di|luon)",
    # sang bước thanh toán
    r"thanh toan", r"tinh tien", r"tinh luon", r"xuat hoa don", r"lay hoa don",
]

NO = [
    # từ chối trực tiếp (cả giọng miền Nam: hổng/hông/hem/hok)
    r"khong", r"ko", r"khg", r"hong (can|lay|mua|co|phai|thich|duoc)", r"hong(?=[.,!?;]|$)",
    r"hem (can|lay|mua|co|duoc)", r"hok (can|lay|mua|co|duoc)",
    r"(hong|hem|hok|khong) (em|a|nha|nhe|ha|dau|chi|anh)\b",
    r"chua", r"thoi", r"khoi", r"khoan", r"cho (da|chut|xiu)", r"huy", r"huy don", r"bo bot", r"bot lai",
    r"khong phai", r"sai roi", r"nham roi", r"nham san pham", r"ghi sai", r"doc sai", r"nghe sai", r"bao nham",
    # hẹn lúc khác / để suy nghĩ
    r"de (anh |chi |co |chu |minh |em |bac |toi |tui |con |ba |me |cau |di )?(suy nghi|xem|xem lai|xem them|sau|lan sau|hom khac|khi khac|tinh|hoi|tham khao)",
    r"suy nghi", r"tham khao", r"xem lai", r"xem them", r"so sanh",
    r"lan sau", r"lan khac", r"hom sau", r"hom khac", r"bua khac", r"khi khac", r"tuan sau", r"thang sau",
    r"tinh sau", r"mai mot", r"hen (lai|hom khac|lan sau)",
    # hết tiền / không có nhu cầu
    r"het tien", r"het ngan sach", r"thieu tien", r"chua du tien", r"con (du|nhieu) o nha",
]


# "chốt" / "rồi" đứng đầu câu trả lời (có thể sau "dạ/ừ/ok") = khách chốt: "chốt", "chốt em", "dạ chốt", "ừ chốt đơn", "rồi em".
# Chỉ nhận ở ĐẦU phản hồi, vì "chốt đơn" ở giữa câu có thể là lời SA đọc lại đơn, không phải khách nói.
YES_START_RE = re.compile(r"^(?:(?:da|u|uh|um|uhm|o|vang|ok|oke|okay|vay|the|roi)\s+){0,2}(?:chot|roi)\b")

# Khách chỉ "ừ/vâng" cho có lệ rồi từ chối ngay ("ừ... thôi để lần sau", "vâng để em suy nghĩ"): các từ NO mạnh dưới đây thắng.
WEAK_YES = {"u", "uh", "uhm", "um", "umm", "uk", "uh huh", "vang", "vang a"}
STRONG_NO = [r"thoi", r"de (anh |chi |co |chu |minh |em |bac |toi |tui |con |ba |me |cau |di )?(suy nghi|xem|sau|lan sau|hom khac|khi khac|tinh|hoi|tham khao)",
             r"suy nghi", r"lan sau", r"lan khac", r"hom sau", r"hom khac", r"khoan", r"huy", r"chua can", r"khong can", r"khong lay", r"khong mua"]

# Câu HỎI kết thúc bằng "không" ("bên em có khuyến mãi không", "giảm thêm được không") không phải từ chối cũng không phải đồng ý.
QUESTION_RE = re.compile(r"\b(?:co|duoc|phai|dung|ok|oke|okay|nhi)\b(?:\s+\w+){0,6}\s+khong\b(?!\s+(?:lay|mua|can|duoc|co|phai|muon|thich|sao|van de))")


def _compile(patterns: list[str]) -> re.Pattern:
    alt = "|".join(sorted(patterns, key=len, reverse=True))
    return re.compile(r"\b(" + alt + r")\b")


STRONG_NO_RE = _compile(STRONG_NO)
YES_RE = _compile(YES)
NO_RE = _compile(NO)
YES_OVERRIDE_RE = re.compile(r"\b(" + "|".join(YES_OVERRIDES) + r")\b")

# Điểm cắt giữa phần liệt kê SKU và phản hồi của khách khi câu không có dấu chấm.
# Chỉ dùng cụm đủ đặc trưng để không cắt nhầm vào tên SKU.
CONFIRM_CUT = re.compile(
    r"\b(da dung|dung roi|duoc roi|ok|oke|okay|okie|o ke|thoi|vang|dong y|nhat tri|chuan roi|yes|"
    r"lay luon|lay di|mua luon|chot luon|chua can|khong can|khong lay|khong mua|ko lay|ko can|hong lay|hong can|"
    r"de (anh |chi |co |chu |minh |em |bac |toi |tui |con |ba |me |cau )?(suy nghi|xem)|xem lai|khoan|huy)\b"
)
