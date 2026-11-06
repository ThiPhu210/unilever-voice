// Cùng bảng màu với web Coach (logo An Hòa – Art Home): khung cam, đỏ nhấn, nâu đậm.
export const C = {
  bg: "#FBF7F2", card: "#FFFFFF", ink: "#3A2316", muted: "#7A6454", line: "#EADFD3",
  tint: "#FFF1DD", brand: "#E07804", red: "#CE0C0B", redBg: "#FDECEA",
  green: "#2E7D4F", greenBg: "#E8F4EC", amber: "#B35900", amberBg: "#FFF4E0",
  /** Màu hành động chính (nút, tab đang chọn, liên kết). Đỏ #CE0C0B đạt tương phản 5.9:1 với chữ trắng. */
  primary: "#CE0C0B",
};

export const R = { card: 16, input: 12, pill: 99 };

/** Khoảng cách dùng chung: 4-8-12-16-24-32, lề trang 20. */
export const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, page: 20 };

/** Đổ bóng nhẹ cho thẻ (iOS dùng shadow*, Android dùng elevation). */
export const shadow = {
  shadowColor: "#3A2316", shadowOpacity: 0.07, shadowRadius: 10,
  shadowOffset: { width: 0, height: 3 }, elevation: 2,
};
