/**
 * Port của rapidfuzz.fuzz (ratio / token_sort_ratio / token_set_ratio) sang TypeScript.
 * Đúng thuật toán Indel (LCS) của rapidfuzz 3.x để điểm khớp SKU trên máy trùng với server Python
 * (ngưỡng MIN_MATCH, "hai SKU quá sát nhau"... đều dựa vào các điểm này). Chỉ dùng cho chuỗi ASCII.
 * LCS tính theo bit song song (Hyyrö) như rapidfuzz: mỗi so khớp tốn O(len * len/32) thay vì O(len^2),
 * cần thiết vì mỗi lần khớp SKU phải chấm điểm hàng nghìn alias trên Hermes (không có JIT).
 */

// bảng mặt nạ ký tự dùng chung (chỉ ASCII); chỉ xoá những ô đã dùng sau mỗi lần tính
const MAXW = 8;                                   // tối đa 8*32 = 256 ký tự cho chuỗi ngắn hơn
const masks = new Int32Array(128 * MAXW);

function popcount32(x: number): number {
  x = x - ((x >>> 1) & 0x55555555);
  x = (x & 0x33333333) + ((x >>> 2) & 0x33333333);
  return (((x + (x >>> 4)) & 0x0f0f0f0f) * 0x01010101) >>> 24;
}

/** LCS bằng DP thường — dùng khi có ký tự ngoài ASCII hoặc chuỗi quá dài. */
function lcsDp(a: string, b: string): number {
  if (a.length < b.length) { const t = a; a = b; b = t; }
  const m = b.length;
  if (m === 0) return 0;
  let prev = new Int32Array(m + 1);
  let cur = new Int32Array(m + 1);
  for (let i = 0; i < a.length; i++) {
    const ca = a.charCodeAt(i);
    for (let j = 0; j < m; j++) {
      cur[j + 1] = ca === b.charCodeAt(j) ? prev[j] + 1 : (prev[j + 1] > cur[j] ? prev[j + 1] : cur[j]);
    }
    const t = prev; prev = cur; cur = t;
  }
  return prev[m];
}

/** Độ dài dãy con chung dài nhất (LCS) của hai chuỗi. */
export function lcsLen(a: string, b: string): number {
  let pat = a, txt = b;
  if (pat.length > txt.length) { pat = b; txt = a; }          // mẫu = chuỗi ngắn hơn
  const m = pat.length;
  if (m === 0) return 0;
  const W = (m + 31) >>> 5;
  if (W > MAXW) return lcsDp(a, b);
  for (let i = 0; i < m; i++) if (pat.charCodeAt(i) >= 128) return lcsDp(a, b);
  for (let i = 0; i < txt.length; i++) if (txt.charCodeAt(i) >= 128) return lcsDp(a, b);

  for (let i = 0; i < m; i++) masks[(pat.charCodeAt(i) * MAXW) + (i >>> 5)] |= 1 << (i & 31);

  let lcs: number;
  if (W === 1) {
    let v = -1;                                                // toàn bit 1
    for (let i = 0; i < txt.length; i++) {
      const mk = masks[txt.charCodeAt(i) * MAXW];
      const u = v & mk;
      v = ((v >>> 0) + (u >>> 0)) | (v & ~u);                  // (v + u) | (v - u), tràn bit tự bỏ
    }
    lcs = popcount32(~v);
  } else {
    const S = new Int32Array(W).fill(-1);
    for (let i = 0; i < txt.length; i++) {
      const base = txt.charCodeAt(i) * MAXW;
      let carry = 0;
      for (let w = 0; w < W; w++) {
        const s = S[w];
        const u = s & masks[base + w];
        const sum = (s >>> 0) + (u >>> 0) + carry;
        carry = sum > 0xffffffff ? 1 : 0;
        S[w] = (sum | (s & ~u)) | 0;
      }
    }
    lcs = 0;
    for (let w = 0; w < W; w++) lcs += popcount32(~S[w]);
  }
  for (let i = 0; i < m; i++) masks[(pat.charCodeAt(i) * MAXW) + (i >>> 5)] = 0;
  return lcs;
}

/** Khoảng cách Indel = len(a) + len(b) - 2*LCS. */
function indel(a: string, b: string): number {
  return a.length + b.length - 2 * lcsLen(a, b);
}

// Hai công thức chuẩn hoá khác nhau ở bit cuối của số thực (rapidfuzz C++ dùng mỗi hàm một kiểu). Phải GIỐNG TỪNG BIT:
// khi hai SKU hoà điểm (vd 60 vs 60) thứ tự xếp hạng phụ thuộc vào chênh lệch 1e-15 đó.
const simRatio = (dist: number, lensum: number): number => (lensum ? 100 * (1 - dist / lensum) : 100);
const simSet = (dist: number, lensum: number): number => (lensum ? 100 - (100 * dist) / lensum : 100);

export function ratio(a: string, b: string): number {
  return simRatio(indel(a, b), a.length + b.length);
}

const splitWs = (s: string): string[] => s.split(/\s+/).filter(Boolean);

/** Chuỗi với các token đã sắp xếp (đầu vào của token_sort_ratio). */
export const sortTokens = (s: string): string => splitWs(s).sort().join(" ");

export function tokenSortRatio(a: string, b: string): number {
  return ratio(sortTokens(a), sortTokens(b));
}

/** Tập token duy nhất của một chuỗi (dùng cho token_set_ratio khi muốn tính trước một phía). */
export const tokenSet = (s: string): Set<string> => new Set(splitWs(s));

export function tokenSetRatioSets(A: Set<string>, B: Set<string>): number {
  if (A.size === 0 || B.size === 0) return 0;
  const inter: string[] = [], diffAB: string[] = [], diffBA: string[] = [];
  for (const t of A) (B.has(t) ? inter : diffAB).push(t);
  for (const t of B) if (!A.has(t)) diffBA.push(t);
  if (inter.length && (!diffAB.length || !diffBA.length)) return 100;

  const ab = diffAB.sort().join(" ");
  const ba = diffBA.sort().join(" ");
  const abLen = ab.length, baLen = ba.length;
  let sectLen = 0;
  if (inter.length) { for (const t of inter) sectLen += t.length; sectLen += inter.length - 1; }
  const sep = sectLen ? 1 : 0;
  const sectAbLen = sectLen + sep + abLen;
  const sectBaLen = sectLen + sep + baLen;

  const result = simSet(indel(ab, ba), sectAbLen + sectBaLen);
  if (!sectLen) return result;
  const r1 = simSet(sep + abLen, sectLen + sectAbLen);
  const r2 = simSet(sep + baLen, sectLen + sectBaLen);
  return Math.max(result, r1, r2);
}

export function tokenSetRatio(a: string, b: string): number {
  return tokenSetRatioSets(tokenSet(a), tokenSet(b));
}
