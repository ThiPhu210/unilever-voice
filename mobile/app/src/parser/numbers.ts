/** Port của parser/numbers.py — đọc số tiếng Việt (không dấu) đến hàng trăm: 'hai muoi lam' -> 25. */

export const DIGITS: Record<string, number> = {
  khong: 0, mot: 1, hai: 2, ba: 3, bon: 4, tu: 4, nam: 5, lam: 5, sau: 6, bay: 7, tam: 8, chin: 9,
  bun: 4,   // ASR nghe "bốn" thành "bún"
};
const TENS = new Set(["muoi", "chuc"]);   // "sáu mươi" = "sáu chục" = 60
export const isDigitWord = (t: string | undefined): boolean => t !== undefined && Object.prototype.hasOwnProperty.call(DIGITS, t);

/** Trả về [giá_trị, vị_trí_token_kế_tiếp] hoặc null. */
export function parseNumber(tokens: string[], i: number): [number, number] | null {
  const t0 = tokens[i];
  if (/^\d+$/.test(t0)) return [parseInt(t0, 10), i + 1];
  if (!isDigitWord(t0) && !TENS.has(t0) && t0 !== "tram") return null;
  if (t0 === "tu" && !(i > 0 && TENS.has(tokens[i - 1]))) return null;   // "tư" chỉ là số khi đứng sau "mươi/chục"

  let value = 0;
  let pending: number | null = null;
  let canUnit = true, seenTens = false, seenHund = false;
  let consumed = false;
  let j = i;
  while (j < tokens.length) {
    const t = tokens[j];
    if (isDigitWord(t)) {
      if (pending !== null || !canUnit) break;
      pending = DIGITS[t]; canUnit = false;
    } else if (t === "tram") {
      if (pending === null || seenHund || seenTens) break;
      value += pending * 100;
      pending = null; seenHund = true; canUnit = true;
    } else if (TENS.has(t)) {
      if (seenTens) break;
      value += (pending || 1) * 10;
      pending = null; seenTens = true; canUnit = true;
    } else if ((t === "le" || t === "linh") && seenHund && pending === null && !seenTens) {
      canUnit = true;
    } else break;
    consumed = true;
    j += 1;
  }
  if (!consumed) return null;
  if (pending) value += pending;
  return [value, j];
}
