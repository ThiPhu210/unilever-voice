/** Port của parser/normalize.py + canon_units (brands.py). Giữ nguyên từng bước để kết quả trùng với server. */

export function stripAccents(s: string): string {
  return s.replace(/đ/g, "d").replace(/Đ/g, "D").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

const reEscape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// ---------- canon_units (brands.py): đơn vị đọc thành chữ -> đơn vị chuẩn ----------
const NB = "(?<![a-z0-9])";   // đầu từ
const NE = "(?![a-z0-9])";    // cuối từ
const UNIT_FIX: [RegExp, string][] = [
  [new RegExp(NB + "ki\\s*lo\\s*gr?am" + NE, "g"), "kg"],
  [new RegExp(NB + "ki\\s*lo" + NE, "g"), "kg"],
  [new RegExp(NB + "(?:mi\\s*li\\s*lit|mi\\s*li|mi\\s*lit|mie?u|mi\\s*mit|mil)" + NE, "g"), "ml"],
  [new RegExp(NB + "go\\s*ram" + NE, "g"), "gam"],
];
const DIG: Record<string, string> = {
  khong: "0", mot: "1", hai: "2", ba: "3", bon: "4", nam: "5", lam: "5", sau: "6", bay: "7", tam: "8", chin: "9",
};
const NUM = "(\\d+|" + Object.keys(DIG).join("|") + ")";
const DEC = new RegExp(NB + NUM + "\\s+(?:phay|cham)\\s+" + NUM + "\\s*(kg|ky|ki|g|gr|gam|gram|ml|l|lit|lt)" + NE, "g");
const DIG2: Record<string, string> = { ...DIG, chinh: "9", rua: "5" };
const NUM2 = "(\\d|" + Object.keys(DIG2).filter((k) => k !== "rua").join("|") + ")";
const KY_DEC = new RegExp(
  NB + NUM + "\\s+(?:ky|kg|ki\\s*lo|ki)\\s+" + NUM2 + "(?=\\s*(?:gia\\b|da\\b|[,;.?!]|$))", "g");

// ASR hay nghe "một ký" thành "một tí"/"một ty": số + "ti|ty" ngay trước "giá" / dấu câu / hết câu là dung tích "ký".
const TI_KY = new RegExp(NB + NUM + "\\s+(?:ti|ty)(?=\\s*(?:gia\\b|da\\b|[,;.?!]|$))", "g");

export function canonUnits(t: string): string {
  for (const [rx, rep] of UNIT_FIX) t = t.replace(rx, rep);
  t = t.replace(DEC, (_m, a: string, b: string, unit: string) => `${DIG[a] ?? a}.${DIG[b] ?? b}${unit}`);
  t = t.replace(TI_KY, (_m, a: string) => `${a} ky`);
  return t.replace(KY_DEC, (_m, a: string, b: string) => `${DIG[a] ?? a}.${DIG2[b] ?? b}kg`);
}

// ---------- normalize.py ----------
const SPLIT_SIZE = /(?<![\d.,])(\d+)\s+([.,])(\d+(?:kg|ky|ki|g|gr|gam|gram|ml|l|lit|lt))(?=\s*(?:[,;.?!]|$))/g;
// Phần văn bản đứng trước con số: đầu chuỗi, dấu câu, hoặc một token số (giá/dung tích) -> con số là SỐ LƯỢNG.
const QTY_CONTEXT = /(?:^|[,;.?!]\s*|(?<![a-z])\d[0-9.,]*[a-z]*\s+)$/;
const SPLIT_SIZE_SP = /(?<![\d.,])(\d+)\s*([.,])(\d+)\s+(kg|ky|ki|g|gr|gam|gram|ml|l|lit|lt)(?![a-z])/g;

/** Cùng dung tích "d.x<unit>" lặp lại phía sau TRONG CÙNG CÂU? (xem _repeats_later trong normalize.py) */
function repeatsLater(full: string, mEnd: number, d: string, x: string, unit: string): boolean {
  const tail = full.slice(mEnd);
  const cut = /(?<!\d)[?!]|\.(?=\s|$)/.exec(tail);
  const rest = cut ? tail.slice(0, cut.index) : tail;
  const u = unit === "kg" || unit === "ky" || unit === "ki" ? "(?:kg|ky|ki)" : reEscape(unit);
  const pat = new RegExp(`(?<![\\d.,])${reEscape(d)}\\s*[.,]\\s*${reEscape(x)}\\s*${u}(?![a-z])`, "g");
  for (const r of rest.matchAll(pat)) {
    if (!QTY_CONTEXT.test(full.slice(0, mEnd + (r.index ?? 0)))) return true;
  }
  return false;
}

export function normalize(text: string): string {
  let t = stripAccents(text.toLowerCase());
  // Nhãn người nói ở đầu câu ("SA: ..." / "Khách: ...") không phải tên hàng
  t = t.replace(/(^|[.?!]\s+)(?:sa|ba|khach|kh)\s*:\s*/gm, "$1");
  t = t.replace(/[^a-z0-9.,;?!\s]/g, " ");
  t = canonUnits(t);
  // ASR nghe "92k" thành "92Khz"/"92kz"
  t = t.replace(/(?<![\d.,])(\d{1,3})\s*(?:khz|kz)\b/g, "$1k");
  t = t.replace(/(\d)\s+([.,])\s*(\d{3})(?!\d)/g, "$1$2$3");
  t = t.replace(SPLIT_SIZE, (m: string, d: string, _s: string, g3: string, offset: number, full: string) => {
    const mm = /^(\d+)([a-z]+)$/.exec(g3)!;
    const x = mm[1], unit = mm[2];
    if (QTY_CONTEXT.test(full.slice(0, offset)) && !repeatsLater(full, offset + m.length, d, x, unit)) return m;
    return d + _s + g3;
  });
  t = t.replace(SPLIT_SIZE_SP, (m: string, d: string, _s: string, x: string, unit: string, offset: number, full: string) => {
    if (QTY_CONTEXT.test(full.slice(0, offset)) && !repeatsLater(full, offset + m.length, d, x, unit)) return m;
    return `${d}.${x}${unit}`;
  });
  return t.replace(/\s+/g, " ").trim();
}
