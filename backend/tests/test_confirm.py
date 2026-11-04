"""Kiểm tra từ khoá khách xác nhận / từ chối (app/parser/confirm_words.py)."""
import pytest
from app.parser.core import detect_customer_confirm, split_tail
from app.parser.normalize import normalize


def confirm(reply: str) -> str:
    return detect_customer_confirm(normalize(reply))[0]


YES_CASES = [
    "Dạ đúng rồi em", "Ok em", "Oke", "Ô kê em", "Okie nha", "Đồng ý", "Nhất trí", "Vâng ạ", "Ừ", "Ừm lấy đi",
    "Được rồi em", "Được đó", "Lấy luôn đi em", "Mua luôn", "Chốt luôn nha", "Đúng.", "Đúng ạ", "Chuẩn rồi",
    "Chính xác", "Ổn rồi em", "Vậy đi em", "Thế đi", "Gói giùm chị", "Tính tiền luôn đi em", "Thanh toán đi",
    "Không sao đâu em, lấy đi", "Hổng sao, lấy luôn", "Thôi được, lấy", "Cũng được em", "Đặt luôn nha",
    "Yes", "Dạ vâng chị lấy",
]
NO_CASES = [
    "Thôi để chị suy nghĩ thêm", "Chưa cần đâu em", "Không lấy đâu", "Hổng lấy đâu em", "Hông cần đâu",
    "Để anh xem lại", "Để em hỏi chồng đã", "Để lần sau nha", "Hôm khác đi em", "Mai mốt chị mua",
    "Khoan đã em", "Chờ đã", "Khỏi em ơi", "Hủy đi em", "Sai rồi em ơi", "Nhầm rồi, chị lấy cái khác",
    "Không phải loại đó", "Hết tiền rồi em", "Để tham khảo thêm", "Tính sau nha", "Hem lấy đâu em",
    "Hôm nay chưa mua", "Để chị so sánh đã",
]
NONE_CASES = ["", "Dạ em cảm ơn chị", "Chị ơi hôm nay trời nóng quá"]


@pytest.mark.parametrize("reply", YES_CASES)
def test_yes(reply):
    assert confirm(reply) == "yes", reply


@pytest.mark.parametrize("reply", NO_CASES)
def test_no(reply):
    assert confirm(reply) == "no", reply


@pytest.mark.parametrize("reply", NONE_CASES)
def test_none(reply):
    assert confirm(reply) == "none", reply


def test_dung_trong_dang_dung_khong_phai_dong_y():
    # "đang dùng" bỏ dấu thành "dang dung" - không được hiểu là "đúng"
    assert confirm("Chị đang dùng loại khác rồi") != "yes"


@pytest.mark.parametrize("tail,items", [
    ("2 omo 800g dong y", "2 omo 800g"),
    ("2 omo 800g chuan roi", "2 omo 800g"),
    ("1 dove 640ml lay luon", "1 dove 640ml"),
    ("1 dove 640ml chua can", "1 dove 640ml"),
])
def test_cat_phan_hoi_khong_dau_cham(tail, items):
    assert split_tail(tail)[0].strip() == items
