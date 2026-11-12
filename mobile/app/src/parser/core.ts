/**
 * Port của parser/core.py — tách đơn hàng từ transcript theo mẫu {số lượng} {sản phẩm} {giá} + dò phản hồi khách.
 * Không dùng LLM: chỉ regex + fuzzy matching. Giữ nguyên logic từng nhánh của bản Python; muốn sửa luật thì sửa ở cả hai nơi
 * rồi chạy `npm run test:parser` (so sánh với server trên bộ transcript mẫu).
 * (Bản này bỏ phần tách người nói `turns`: app không còn tách SA/khách.)
 */
import { Catalog } from "./catalog";
import {
  QUESTION_RE, STRONG_NO_RE, WEAK_YES, YES_OVERRIDE_RE, YES_RE, YES_START_RE, NO_RE,
} from "./confirmWords";
import { DIGITS, isDigitWord, parseNumber } from "./numbers";
import { normalize } from "./normalize";
import { parsePrice, priceSuspect } from "./prices";
import { SIZE_RE, SIZE_UNIT_MAP, isSizeUnit, sizeNorm, tokenize } from "./tokens";
import { ratio } from "./fuzz";

export const PARSER_VERSION = "ts-1";

const SEPARATORS = new Set([",", ";", "va", "voi", "cong", "them"]);
const QTY_UNITS = new Set(["chai", "goi", "lon", "hop", "thung", "tuyp", "tui", "loc", "cai", "bich", "hu", "bo", "lo", "can", "bao", "vi"]);
const STOP_NAME = new Set(["a", "nhe", "nha", "ha", "da", "vang", "di", "cua", "loai", "hang", "cai", "x", "la", "don", "gia", "moi", "tien", "dong", "vnd", "d"]);
const OPENERS = new Set(["em", "xin", "cam", "on", "chi", "anh", "chot", "minh", "vay", "oi", "ok", "roi", "gom", "luon", "len", "lay", "them", "dat", "mua",
  "cho", "vang", "da", "a", "nhe", "nha", "ha", "la", "don", "va", "thi", "xong", "day", "gio", "hang", "vao", "bo"]);
const LEAD_STRIP = new Set(["don", "luon", "cho", "nhe", "la", "gom", "vay"]);
const AMBIGUOUS = new Set(["nam", "sau", "bon", "bun", "tu"]);
const BATH_PREV = new Set(["sua", "phong", "dau", "bon", "gel"]);
const PRICE_LEAD = new Set(["gia", "da", "don", "la"]);
const SENT_END = /[.?!](?=\s|$)/;
export const MIN_MATCH = 0.6;
const LIST_NO = /(^|[,;]\s*)(\d{1,2})\.(?=\s)/g;
const KG_PRICE_RE = /^\d{1,3}(?:kg|ky|ki)$/;
const isInt = (t: string) => /^\d+$/.test(t);

export type Seg = [number | null, string[], number | null];   // [số lượng, tên (list từ), giá]
export type Item = {
  raw: string; qty: number; qty_assumed: boolean; price: number; price_missing: boolean;
  sku_id: string; sku_name: string; conf: number; candidates: { sku_id: string; name: string; score: number }[]; need_confirm: boolean;
};
export type Order = {
  closing_text: string; items: Item[]; customer_confirm: "yes" | "no" | "none"; customer_evidence: string | null;
  confirm_source: string; needs_review: boolean; missing_price: boolean;
};
export type Parsed = { closing_detected: boolean; orders: Order[] };

/** Bỏ lời mở đầu / từ đệm ở hai đầu tên ("dạ em xin cảm ơn chị vậy mình chốt bốn kem ..."). */
function trimOpeners(wordsIn: string[]): string[] {
  const words = [...wordsIn];
  for (let k = 0; k < Math.min(words.length - 1, 6); k++) {
    if (words[k] === "gio" && words[k + 1] === "hang") { words.splice(0, k + 2); break; }   // "...giỏ hàng": bỏ mọi thứ trước nó
  }
  const skip = (w: string) => STOP_NAME.has(w) || OPENERS.has(w);
  while (words.length && (skip(words[0]) || (words[0] === "o" && words.length > 1 && skip(words[1])))) words.shift();
  while (words.length && skip(words[words.length - 1])) words.pop();
  return words;
}

export function detectCustomerConfirm(afterIn: string): ["yes" | "no" | "none", string | null] {
  let after = afterIn.split(/\s+/).filter(Boolean).slice(0, 25).join(" ");
  after = after.replace(YES_OVERRIDE_RE, "ok");   // "không sao", "thôi được", "cũng được"... = đồng ý
  after = after.replace(QUESTION_RE, " hoi ");      // câu hỏi "có ... không": bỏ khỏi việc dò yes/no
  let y: { index: number; text: string; end: number } | null = null;
  const ym = YES_RE.exec(after);
  if (ym) y = { index: ym.index, text: ym[0], end: ym.index + ym[0].length };
  const nm = NO_RE.exec(after);
  const n = nm ? { index: nm.index, text: nm[0] } : null;
  const sm = YES_START_RE.exec(after);
  const ys = sm ? { index: sm.index, text: sm[0], end: sm.index + sm[0].length } : null;   // "chốt", "dạ chốt", "rồi em"... ở đầu phản hồi
  if (ys && (!y || ys.index <= y.index || WEAK_YES.has(y.text)) && !(n && n.index < ys.end && !YES_START_RE.test(after.slice(n.index)))) y = ys;
  if (y && n && WEAK_YES.has(y.text) && y.index < n.index) {   // "ừ... thôi để lần sau": 'ừ' chỉ là đệm
    STRONG_NO_RE.lastIndex = y.end;
    const sn = STRONG_NO_RE.exec(after);
    if (sn) return ["no", sn[0]];
  }
  if (y && (!n || y.index < n.index)) return ["yes", y.text];
  if (n) return ["no", n.text];
  return ["none", null];
}

/** ASR nghe 'giá' thành 'dạ', 'dạm', 'dả', 'giạ'... */
function likeGia(t: string): boolean {
  return /^[a-z]+$/.test(t) && t.length <= 4 && Math.max(ratio(t, "gia"), ratio(t, "da")) >= 66;
}

function skipPriceLead(toks: string[], jIn: number): number {
  let j = jIn;
  while (j < toks.length && PRICE_LEAD.has(toks[j])) j += 1;
  let k = j;   // tiền tố nghe sai ("dạm 103k"): chỉ bỏ khi NGAY SAU đó thật sự là một mức giá
  while (k < toks.length && k - j < 2 && likeGia(toks[k])) k += 1;
  if (k > j && parsePrice(toks, k, true)) return k;
  return j;
}

/** Sau toks[j-1] có một mức giá riêng không? Có dấu phẩy ("..., dạm 86k") hoặc chữ dẫn giá không dấu phẩy. */
function priceFollows(toks: string[], j: number): boolean {
  if (j >= toks.length) return false;
  const comma = toks[j] === "," || toks[j] === ";";
  const k = skipPriceLead(toks, comma ? j + 1 : j);
  if (!comma && k === j) return false;
  return parsePrice(toks, k, true) !== null;
}

/** toks[i] là 'va'/'voi': sau nó có phải số lượng của một dòng hàng mới không? */
function startsItem(toks: string[], i: number): boolean {
  let j = i + 1;
  while (j < toks.length && LEAD_STRIP.has(toks[j])) j += 1;
  return j < toks.length && parseNumber(toks, j) !== null;
}

const hasSize = (name: string[]) => name.some((w) => SIZE_RE.test(w));

/** toks[k] dạng "92kg": ASR nghe "92k" (giá) thành "92Kg" hay đây là dung tích thật? */
function kgIsPrice(toks: string[], k: number, name: string[], afterComma: boolean): boolean {
  if (k >= toks.length || !KG_PRICE_RE.test(toks[k]) || !name.length) return false;
  let j = k + 1;
  if (j < toks.length && (toks[j] === "," || toks[j] === ";")) j += 1;
  j = skipPriceLead(toks, j);
  if (j < toks.length && parsePrice(toks, j, true)) return false;
  const last = name[name.length - 1];
  return hasSize(name) || PRICE_LEAD.has(last) || (afterComma && /^\d+$/.test(last));
}

/** ASR chèn dấu phẩy giữa tên SKU: tên chưa có dung tích và sau dấu phẩy là chữ -> không phải ranh giới dòng hàng. */
function commaInName(toks: string[], i: number, name: string[]): boolean {
  const j = i + 1;
  return j < toks.length && !hasSize(name) && !SEPARATORS.has(toks[j]) && parseNumber(toks, j) === null;
}

/** toks[i] là "bốn/năm/sáu" mơ hồ: thử CẢ HAI cách hiểu (số lượng / chữ trong tên) rồi để catalog quyết. */
function isNewItemStart(toks: string[], i: number, name: string[], catalog: Catalog): boolean {
  const look: string[] = [];
  for (const t of toks.slice(i + 1, i + 12)) {
    if (SEPARATORS.has(t) || t === "gia") break;
    look.push(t);
  }
  if (!look.length || isDigitWord(toks[i + 1])) return false;
  const top = (w: string[]) => catalog.match(w).candidates[0].score;
  const scoreA = top(look);
  return scoreA >= 100 * MIN_MATCH && scoreA + 0.5 >= top([...trimOpeners(name), toks[i], ...look]);
}

export function scanSegments(text: string, catalog: Catalog | null = null): Seg[] {
  const toks = tokenize(text);
  const segs: Seg[] = [];
  let qty: number | null = null;
  let name: string[] = [];
  let price: number | null = null;

  const flush = () => {
    // Từ đệm chỉ bỏ ở HAI ĐẦU tên: chữ "la" giữa "ga la si" (Galaxy) là một âm tiết của tên hàng.
    const words = trimOpeners(name);
    if (words.length) segs.push([qty, words, price]);
    qty = null; name = []; price = null;
  };

  let i = 0;
  const n = toks.length;
  while (i < n) {
    const t = toks[i];
    if (price !== null && !SEPARATORS.has(t) && parseNumber(toks, i) === null) flush();   // đã có giá -> kết thúc dòng hàng

    if (SEPARATORS.has(t)) {
      const isComma = t === "," || t === ";";
      if (isComma && !name.length && qty !== null) { i += 1; continue; }   // dấu phẩy ngay sau số lượng: GIỮ số lượng
      if (isComma && name.length && price === null) {
        const k = skipPriceLead(toks, i + 1);   // "800g, giá 65k đồng": ASR chèn dấu phẩy giữa tên SKU và giá
        const pr = parsePrice(toks, k, k > i + 1 || kgIsPrice(toks, k, name, true));
        if (pr) { [price, i] = pr; continue; }
        if (commaInName(toks, i, name)) { i += 1; continue; }
      }
      if ((t === "va" || t === "voi") && !name.length && qty !== null) { name.push(t); i += 1; continue; }   // "2 va so lin ..." = Vaseline
      if ((t === "va" || t === "voi") && name.length && price === null && !startsItem(toks, i)) { name.push(t); i += 1; continue; }
      flush(); i += 1; continue;
    }

    const m = SIZE_RE.exec(t);
    if (m) {
      const nxt = i + 1 < n ? toks[i + 1] : null;
      if (qty !== null && !name.length && (nxt === "," || nxt === ";" || nxt === null)) { i += 1; continue; }   // dung tích rác sau số lượng
      if (price === null && name.length && kgIsPrice(toks, i, name, false)) {
        const pr = parsePrice(toks, i, true);   // "... 28g 7Kg 2 ...": ASR bỏ mất dấu phẩy, "7Kg" = 7k
        if (pr) { [price, i] = pr; continue; }
      }
      name.push(sizeNorm(m[1], m[2])); i += 1; continue;
    }
    if (LEAD_STRIP.has(t) && !name.length && qty === null) { i += 1; continue; }
    if (name.length && price === null && isInt(t) && i + 2 < n && toks[i + 1] === "trong" && isInt(toks[i + 2])) {
      name.push(t, "trong", toks[i + 2]); i += 3; continue;   // "rửa chén 14 trong 1"
    }
    if (name.length && price === null && isInt(t) && priceFollows(toks, i + 1)) { name.push(t); i += 1; continue; }   // "bảo vệ 123, giá 48k"
    if (!name.length && qty === null && segs.length && segs[segs.length - 1][2] === null) {
      const k = skipPriceLead(toks, i);   // giá "mồ côi" ngay sau một dòng đã đóng: gắn lại vào dòng trước
      const pr = (k > i || !isInt(t)) ? parsePrice(toks, k, k > i) : null;
      if (pr) { const last = segs[segs.length - 1]; segs[segs.length - 1] = [last[0], last[1], pr[0]]; i = pr[1]; continue; }
    }
    if (name.length && price === null) {
      const pr = parsePrice(toks, i);   // "... 65 nghìn đồng" ngay sau tên SKU
      if (pr) { [price, i] = pr; continue; }
    }
    if (t === "tam" && name.length && (
      BATH_PREV.has(name[name.length - 1])   // "sữa/dầu tắm"
      || (price === null && !SIZE_RE.test(name[name.length - 1])
        && !(i + 1 < n && (toks[i + 1] === "tram" || toks[i + 1] === "muoi" || toks[i + 1] === "chuc" || isSizeUnit(toks[i + 1])))))) {
      name.push(t); i += 1; continue;
    }
    // Từ nhập nhằng KHÔNG phải số khi đang dở tên hàng, hoặc ngay sau số lượng ("hai bon kem ..." = 2 x Pond's).
    let ambInName = AMBIGUOUS.has(t) && price === null && (trimOpeners(name).length > 0 || qty !== null)
      && !(i + 1 < n && (toks[i + 1] === "tram" || toks[i + 1] === "muoi" || toks[i + 1] === "chuc"));
    if (ambInName && qty === null && catalog !== null && isNewItemStart(toks, i, name, catalog)) ambInName = false;
    if (!ambInName) {
      const p = parseNumber(toks, i);
      if (p) {
        const [v, j] = p;
        if (name.length && price === null && j + 1 < n && toks[j] === "trong" && parseNumber(toks, j + 1)) {
          const [v2, j2] = parseNumber(toks, j + 1)!;   // "rửa chén mười bốn trong một"
          name.push(String(v), "trong", String(v2)); i = j2; continue;
        }
        if (j < n && isSizeUnit(toks[j])) { name.push(sizeNorm(String(v), toks[j])); i = j + 1; continue; }   // "tam tram gam" = 800g
        if (name.length || qty !== null) flush();
        qty = v; i = j;
        if (i < n && QTY_UNITS.has(toks[i])) i += 1;
        continue;
      }
    }
    name.push(t); i += 1;
  }
  flush();
  return segs;
}

/** ASR nghe sai một chữ trong tên thành SỐ nên parser tách làm hai dòng: gộp lại khi bản gộp khớp catalog TỐT HƠN. */
function mergeBroken(segs: Seg[], catalog: Catalog): Seg[] {
  const out: Seg[] = [];
  let k = 0;
  while (k < segs.length) {
    const [qty, words, price] = segs[k];
    if (price === null && qty !== null && k + 1 < segs.length && segs[k + 1][2] !== null) {
      const [, w2, p2] = segs[k + 1];
      const merged = catalog.match([...words, ...w2]).conf;
      if (merged >= MIN_MATCH && merged > catalog.match(w2).conf) { out.push([qty, [...words, ...w2], p2]); k += 2; continue; }
    }
    out.push(segs[k]); k += 1;
  }
  return out;
}

/** Câu chỉ là một mức giá ("giá một trăm lẻ ba nghìn"): ASR chèn dấu chấm giữa dòng hàng và giá của nó. */
function isPriceOnly(sentence: string): boolean {
  const toks = tokenize(sentence);
  const j = skipPriceLead(toks, 0);
  if (j === 0 && toks[0] !== "gia") return false;
  const p = parsePrice(toks, j, true);
  return !!p && toks.slice(p[1]).every((t) => SEPARATORS.has(t) || STOP_NAME.has(t) || OPENERS.has(t));
}

/** Trong một câu, chỉ giữ dòng có ĐỦ số lượng + sản phẩm khớp catalog + giá. */
function itemsIn(sentence: string, catalog: Catalog): Item[] {
  const items: Item[] = [];
  for (const [qty, words, price] of mergeBroken(scanSegments(sentence, catalog), catalog)) {
    if (price === null) continue;   // bắt buộc có giá
    const res = catalog.match(words);
    if (res.conf < MIN_MATCH) continue;
    const assumed = qty === null;   // ASR rơi mất số lượng -> giả định 1, đánh dấu cần xác nhận
    const q = assumed ? 1 : qty!;
    const need = res.conf < 0.85 || assumed || q === 0 || q > 200 || priceSuspect(price);
    items.push({ raw: words.join(" "), qty: q, qty_assumed: assumed, price, price_missing: false, ...res, need_confirm: need });
  }
  return items;
}

/** Chia toàn văn thành các nhóm: mỗi câu có dòng hàng mở một nhóm mới; các câu liền sau là 'phản hồi' của nhóm đó. */
function itemGroups(textIn: string, catalog: Catalog): [Item[], string][] {
  const text = textIn.replace(LIST_NO, "$1$2");   // bỏ số thứ tự ASR tự thêm: "1. omo" -> "1 omo"
  const groups: [Item[], string[]][] = [];
  const sents: string[] = [];
  for (const sent of text.split(SENT_END).filter((s) => s.trim())) {
    const prev = sents.length ? scanSegments(sents[sents.length - 1]) : [];
    if (sents.length && isPriceOnly(sent) && prev.length && prev[prev.length - 1][2] === null) sents[sents.length - 1] += " " + sent;
    else sents.push(sent);
  }
  for (const sent of sents) {
    const items = itemsIn(sent, catalog);
    if (items.length) groups.push([items, []]);
    else if (groups.length) groups[groups.length - 1][1].push(sent.trim());
  }
  return groups.map(([items, after]) => [items, after.join(" ")]);
}

function makeOrder(items: Item[], after: string, source: string): Order {
  const [confirm, evidence] = detectCustomerConfirm(after);
  return {
    closing_text: items.map((i) => `${i.qty} ${i.raw} ${i.price}`).join("; "),
    items,
    customer_confirm: confirm,
    customer_evidence: evidence,
    confirm_source: source,
    needs_review: items.some((i) => i.need_confirm),
    missing_price: false,
  };
}

export function parseTranscript(text: string, catalog: Catalog): Parsed {
  const orders = itemGroups(normalize(text), catalog).map(([items, after]) => makeOrder(items, after, "text"));
  return { closing_detected: orders.length > 0, orders };
}

export { DIGITS, SIZE_UNIT_MAP };
