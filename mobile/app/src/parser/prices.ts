/**
 * Port của parser/prices.py — đọc giá SKU: "65 nghìn đồng", "65k", "65.000đ", "sáu mươi lăm nghìn", "một trăm hai mươi nghìn"...
 * Trả về VND (số nguyên). Chỉ nhận là giá khi có đơn vị tiền hoặc là số >= 1000 để không nhầm với số lượng.
 */
import { DIGITS, isDigitWord, parseNumber } from "./numbers";

const THOUSAND = new Set(["nghin", "ngan", "ng", "k", "nghìn", "ngàn"]);
const MILLION = new Set(["trieu", "tr"]);
const CURRENCY = new Set(["dong", "d", "vnd", "viet nam dong"]);
const UNITS = new Set([...THOUSAND, ...MILLION, ...CURRENCY]);
const NUM_TOKEN = /^(\d+(?:[.,]\d+)?)([a-z]*)$/;
const GROUPED = /^\d{1,3}(?:[.,]\d{3})+$/;
const KG_AS_K = new Set(["kg", "ky", "ki"]);
export const PRICE_MIN = 500, PRICE_MAX = 50_000_000;

const isThousandOrMillion = (t: string | undefined): boolean => t !== undefined && (THOUSAND.has(t) || MILLION.has(t));

/** Python round(): làm tròn về số chẵn khi đúng .5 */
function pyRound(x: number): number {
  const f = Math.floor(x), d = x - f;
  if (d < 0.5) return f;
  if (d > 0.5) return f + 1;
  return f % 2 === 0 ? f : f + 1;
}

function skipCurrency(toks: string[], j: number): number {
  while (j < toks.length && CURRENCY.has(toks[j])) j += 1;
  return j;
}

/** Phần lẻ sau 'nghìn': 'rưỡi' (+500) hoặc 'hai trăm năm mươi' (+250). */
function tailAfterThousand(toks: string[], j: number): [number, number] {
  if (j < toks.length && toks[j] === "ruoi") return [500, j + 1];
  if (j < toks.length) {
    const p = parseNumber(toks, j);
    if (p && p[0] >= 100 && p[0] < 1000 && p[0] % 10 === 0) return [p[0], p[1]];
  }
  return [0, j];
}

/** Giá đọc từng chữ số, không có "mươi": "bảy bảy ngàn" = 77k, "một trăm hai sáu ngàn" = 126k. */
function spokenDigits(toks: string[], i: number): [number, number] | null {
  const n = toks.length;
  let j = i, hund = 0;
  if (j + 1 < n && isDigitWord(toks[j]) && toks[j + 1] === "tram") { hund = DIGITS[toks[j]] * 100; j += 2; }
  if (j + 2 < n && isDigitWord(toks[j]) && isDigitWord(toks[j + 1]) && toks[j] !== "khong" && isThousandOrMillion(toks[j + 2])) {
    return [hund + DIGITS[toks[j]] * 10 + DIGITS[toks[j + 1]], j + 2];
  }
  return null;
}

/** ASR nghe "trăm" thành "tăm" (-> 'tam' = tám): "hai tăm mười bảy ngàn" = 217k. Trả về CHÍNH mảng cũ nếu không có cụm giá. */
function tamLaTram(toks: string[], i: number): string[] {
  const n = toks.length;
  let end = -1;
  for (let k = i; k < Math.min(n, i + 8); k++) if (isThousandOrMillion(toks[k])) { end = k; break; }
  if (end < 0) return toks;
  const out = toks.slice();
  for (let k = i + 1; k < end; k++) {
    const nx = toks[k + 1];
    if (toks[k] === "tam" && isDigitWord(toks[k - 1]) && (nx === "muoi" || nx === "chuc" || nx === "le" || nx === "linh" || isDigitWord(nx))) out[k] = "tram";
  }
  return out;
}

/** Thử đọc giá tại vị trí i. Trả về [vnd, vị_trí_kế_tiếp] hoặc null. kgAsK: coi "92Kg" là "92k". */
export function parsePrice(toks: string[], i: number, kgAsK = false): [number, number] | null {
  const n = toks.length;
  if (i >= n) return null;
  const t = toks[i];
  const m = NUM_TOKEN.exec(t);
  let value: number, j: number;
  if (m) {
    const num = m[1], suffix = m[2];
    j = i + 1;
    let unit: string | null = suffix || null;
    if (kgAsK && unit !== null && KG_AS_K.has(unit) && /^\d{1,3}$/.test(num)) unit = "k";
    if (unit !== null && !UNITS.has(unit)) return null;
    if (unit === null && j < n && UNITS.has(toks[j])) { unit = toks[j]; j += 1; }
    if (GROUPED.test(num)) {
      if (unit !== null && (THOUSAND.has(unit) || MILLION.has(unit))) return null;
      value = parseInt(num.replace(/[.,]/g, ""), 10);
    } else {
      const f = parseFloat(num.replace(",", "."));
      value = f;
      if (unit !== null && THOUSAND.has(unit)) {
        value *= 1000;
        if (Number.isInteger(f)) {   // "65 nghìn rưỡi" / "65 nghìn 500"
          const [extra, j2] = tailAfterThousand(toks, j);
          value += extra; j = j2;
        }
      } else if (unit !== null && MILLION.has(unit)) {
        value *= 1_000_000;
      } else if (value < 1000) {
        return null;   // "65" hoặc "65 đồng": không đủ chắc là giá
      }
    }
    value = pyRound(value);
  } else {
    let v: number;
    const p = parseNumber(toks, i);
    let fixed: string[];
    let p2: [number, number] | null;
    if (p && p[1] < n && isThousandOrMillion(toks[p[1]])) {
      [v, j] = p;
    } else if ((fixed = tamLaTram(toks, i)) !== toks && (p2 = parseNumber(fixed, i)) && p2[1] < n && isThousandOrMillion(fixed[p2[1]])) {
      [v, j] = p2;
    } else {
      const sd = spokenDigits(toks, i);
      if (!sd) return null;
      [v, j] = sd;
    }
    const unit = toks[j]; j += 1;
    if (THOUSAND.has(unit)) {
      value = v * 1000;
      const [extra, j2] = tailAfterThousand(toks, j);
      value += extra; j = j2;
    } else {
      value = v * 1_000_000;
    }
  }
  j = skipCurrency(toks, j);
  return [value, j];
}

export const priceSuspect = (price: number | null): boolean => price !== null && !(price >= PRICE_MIN && price <= PRICE_MAX);
