/** Port của parser/tokens.py */
import { normalize } from "./normalize";

export const TOKEN_RE = /\d+(?:[.,]\d+)?[a-z]*|[a-z]+|[,;]/g;
export const SIZE_RE = /^(\d+(?:[.,]\d+)?)(kg|ky|ki|g|gr|gam|gram|ml|l|lit|lt)$/;
export const SIZE_UNIT_MAP: Record<string, string> = {
  kg: "kg", ky: "kg", ki: "kg",
  g: "g", gr: "g", gam: "g", gram: "g",
  ml: "ml", l: "l", lit: "l", lt: "l",
};
const NUM_RE = /^\d+(?:[.,]\d+)?$/;

export const tokenize = (text: string): string[] => text.match(TOKEN_RE) ?? [];
export const isSizeUnit = (t: string | undefined): boolean => t !== undefined && Object.prototype.hasOwnProperty.call(SIZE_UNIT_MAP, t);

export function sizeNorm(num: string, unit: string): string {
  return `${String(num).replace(",", ".")}${SIZE_UNIT_MAP[unit]}`;
}

/** Token hóa + gộp 'số + đơn vị' thành size chuẩn (800g, 3.2kg, 1.6l). */
export function canonTokens(text: string): string[] {
  const toks = tokenize(normalize(text));
  const out: string[] = [];
  let i = 0;
  while (i < toks.length) {
    const t = toks[i];
    const m = SIZE_RE.exec(t);
    if (m) { out.push(sizeNorm(m[1], m[2])); i += 1; }
    else if (NUM_RE.test(t) && i + 1 < toks.length && isSizeUnit(toks[i + 1])) { out.push(sizeNorm(t, toks[i + 1])); i += 2; }
    else { out.push(t); i += 1; }
  }
  return out;
}
