// Định dạng tiền / giờ không phụ thuộc Intl (Hermes trên một số máy Android thiếu locale vi-VN).
export const thousands = (n: number) => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
export const vnd = (n: number) => `${thousands(n)}đ`;

const p2 = (n: number) => String(n).padStart(2, "0");
/** created_at từ server là UTC "YYYY-MM-DD HH:MM:SS" */
export function fmtTime(ts: string): string {
  const d = new Date(ts.replace(" ", "T") + "Z");
  return `${p2(d.getDate())}/${p2(d.getMonth() + 1)} ${p2(d.getHours())}:${p2(d.getMinutes())}`;
}
export function isToday(ts: string): boolean {
  const d = new Date(ts.replace(" ", "T") + "Z"), n = new Date();
  return d.getFullYear() === n.getFullYear() && d.getMonth() === n.getMonth() && d.getDate() === n.getDate();
}
export const mmss = (ms: number) => {
  const s = Math.floor(ms / 1000);
  return `${p2(Math.floor(s / 60))}:${p2(s % 60)}`;
};

/** Giá hiển thị trong ô nhập, đơn vị NGHÌN đồng (SA/BA quen nói "65 nghìn"): 65000 -> "65", 65500 -> "65,5" */
export function priceToInput(price: number | null | undefined): string {
  if (price == null) return "";
  const k = price / 1000;
  return Number.isInteger(k) ? String(k) : String(k).replace(".", ",");
}
/** "65" -> 65000, "65,5" -> 65500, "65000" -> 65000 (đã là đồng), "" -> null */
export function inputToPrice(txt: string): number | null {
  const t = txt.trim().replace(/\s/g, "").replace(/\./g, "").replace(",", ".");
  if (!t) return null;
  const v = Number(t);
  if (!isFinite(v) || v < 0) return null;
  return Math.round(v >= 1000 ? v : v * 1000);
}

/** So khớp tìm kiếm không dấu */
export const plain = (s: string) =>
  s.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();
