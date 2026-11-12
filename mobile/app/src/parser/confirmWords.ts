/** Port của parser/confirm_words.py — từ khoá khách xác nhận (YES) / từ chối (NO). Chữ thường, không dấu. */

const YES_OVERRIDES = [
  "(khong|hong|ko|hem) (sao|van de|co gi|thanh van de|sai|nham|dat|mac)",
  "thoi (duoc|cung duoc|lay|mua|ok|oke|vay di|cung ok)",
  "cung (duoc|ok|oke|okay)",
];

const YES = [
  "dung roi", "dung r", "dung vay", "dung do", "dung a", "dung nhu vay", "dung het",
  "dung(?=[.,!?;]|$)",
  "chinh xac", "chuan roi", "chuan luon", "chuan",
  "ok", "oke", "okay", "okie", "okela", "o ke", "o k", "oc ke", "o kay", "au kay", "o key", "au ke", "yes", "yeah",
  "dong y", "nhat tri", "hop ly",
  "vang", "vang a", "u", "uh", "uhm", "um", "umm", "uk", "uh huh",
  "duoc roi", "duoc do", "duoc luon", "duoc a", "duoc nhe", "duoc nha", "duoc",
  "on roi", "on ap", "tot roi", "tot qua",
  "vay di", "the di", "nhu vay di", "nhu vay nhe", "nhu vay nha", "vay nha",
  "lay", "lay luon", "lay di", "mua", "mua luon", "mua di", "chot luon", "chot di",
  "dat luon", "dat hang", "goi (giup|gium|lai|luon)", "boc (di|luon)",
  "thanh toan", "tinh tien", "tinh luon", "xuat hoa don", "lay hoa don",
];

const NO = [
  "khong", "ko", "khg", "hong (can|lay|mua|co|phai|thich|duoc)", "hong(?=[.,!?;]|$)",
  "hem (can|lay|mua|co|duoc)", "hok (can|lay|mua|co|duoc)",
  "(hong|hem|hok|khong) (em|a|nha|nhe|ha|dau|chi|anh)\\b",
  "chua", "thoi", "khoi", "khoan", "cho (da|chut|xiu)", "huy", "huy don", "bo bot", "bot lai",
  "khong phai", "sai roi", "nham roi", "nham san pham", "ghi sai", "doc sai", "nghe sai", "bao nham",
  "de (anh |chi |co |chu |minh |em |bac |toi |tui |con |ba |me |cau |di )?(suy nghi|xem|xem lai|xem them|sau|lan sau|hom khac|khi khac|tinh|hoi|tham khao)",
  "suy nghi", "tham khao", "xem lai", "xem them", "so sanh",
  "lan sau", "lan khac", "hom sau", "hom khac", "bua khac", "khi khac", "tuan sau", "thang sau",
  "tinh sau", "mai mot", "hen (lai|hom khac|lan sau)",
  "het tien", "het ngan sach", "thieu tien", "chua du tien", "con (du|nhieu) o nha",
];

export const YES_START_RE = /^(?:(?:da|u|uh|um|uhm|o|vang|ok|oke|okay|vay|the|roi)\s+){0,2}(?:chot|roi)\b/;

// Khách chỉ "ừ/vâng" cho có lệ rồi từ chối ngay: các từ NO mạnh thắng.
export const WEAK_YES = new Set(["u", "uh", "uhm", "um", "umm", "uk", "uh huh", "vang", "vang a"]);
const STRONG_NO = [
  "thoi", "de (anh |chi |co |chu |minh |em |bac |toi |tui |con |ba |me |cau |di )?(suy nghi|xem|sau|lan sau|hom khac|khi khac|tinh|hoi|tham khao)",
  "suy nghi", "lan sau", "lan khac", "hom sau", "hom khac", "khoan", "huy", "chua can", "khong can", "khong lay", "khong mua",
];

// Câu HỎI kết thúc bằng "không" không phải từ chối cũng không phải đồng ý.
export const QUESTION_RE = /\b(?:co|duoc|phai|dung|ok|oke|okay|nhi)\b(?:\s+\w+){0,6}\s+khong\b(?!\s+(?:lay|mua|can|duoc|co|phai|muon|thich|sao|van de))/g;

function compile(patterns: string[], flags = ""): RegExp {
  const alt = [...patterns].sort((a, b) => b.length - a.length).join("|");   // sort ổn định: dài trước, bằng nhau giữ thứ tự
  return new RegExp("\\b(" + alt + ")\\b", flags);
}

export const STRONG_NO_RE = compile(STRONG_NO, "g");   // 'g' để dùng lastIndex (search từ vị trí pos)
export const YES_RE = compile(YES);
export const NO_RE = compile(NO);
export const YES_OVERRIDE_RE = new RegExp("\\b(" + YES_OVERRIDES.join("|") + ")\\b", "g");
