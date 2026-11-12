/**
 * Danh mục SKU + chấm điểm khớp. Port của Catalog.match (catalog.py).
 * Chỉ mục alias (đã gấp về khoá âm) do SERVER dựng sẵn và gửi xuống qua GET /api/catalog/index
 * (brands.py / canon_tokens / fold chạy ở server), nên app chỉ cần phần so khớp.
 */
import { fold } from "./phonetics";
import { ratio, sortTokens, tokenSet, tokenSetRatioSets } from "./fuzz";
import { SIZE_RE } from "./tokens";
import { pyRoundTo } from "./util";

export type Sku = { sku_id: string; name: string; unit: string; barcode?: string };
/** [sku_id, alias_words (khoá âm), alias_size | null] */
export type IndexRow = [string, string, string | null];
export type CatalogPayload = { version: string; skus: Sku[]; index: IndexRow[]; hotwords?: string[] };
export type Candidate = { sku_id: string; name: string; score: number };
export type MatchResult = { sku_id: string; sku_name: string; conf: number; candidates: Candidate[] };

const UNIT_GROUP: Record<string, string> = { g: "mass", ml: "mass", kg: "kilo", l: "kilo" };
const num = (x: string) => parseFloat(x.replace(",", "."));

/** Quan hệ giữa dung tích nghe được `b` và dung tích alias `a` khi KHÔNG bằng nhau: 'unit' | 'mag' | null. */
function sizeRel(a: string, b: string): "unit" | "mag" | null {
  const ma = SIZE_RE.exec(a), mb = SIZE_RE.exec(b);
  if (!(ma && mb)) return null;
  const sameGroup = UNIT_GROUP[ma[2]] === UNIT_GROUP[mb[2]];
  if (sameGroup && num(ma[1]) === num(mb[1])) return "unit";
  const sig = (x: string) => x.replace(/\./g, "").replace(/,/g, "").replace(/^0+|0+$/g, "");
  if (sig(ma[1]) === sig(mb[1]) && (sameGroup || sig(ma[1]).length >= 2)) return "mag";
  return null;
}

type Row = { sku: string; words: string; size: string | null; sorted: string; set: Set<string>; compact: string };

export class Catalog {
  skus: Record<string, Sku> = {};
  version: string;
  hotwords: string[];
  private rows: Row[] = [];

  constructor(payload: CatalogPayload) {
    this.version = payload.version;
    this.hotwords = payload.hotwords ?? [];
    for (const s of payload.skus) this.skus[s.sku_id] = s;
    // tính trước mọi thứ không phụ thuộc câu đang nghe: match() chạy qua ~2000 dòng mỗi lần gọi
    for (const [sku, words, size] of payload.index) {
      const sorted = sortTokens(words);
      this.rows.push({ sku, words, size, sorted, set: tokenSet(sorted), compact: words.replace(/ /g, "") });
    }
  }

  get size(): number { return Object.keys(this.skus).length; }

  match(wordsIn: string[]): MatchResult {
    // Có thể có NHIỀU "size" trong một dòng khi ASR chèn rác: chỉ cần MỘT size khớp là đủ (không phạt).
    const sizes = wordsIn.filter((w) => SIZE_RE.test(w));
    const plain = fold(wordsIn.filter((w) => !SIZE_RE.test(w)));
    const sortedQ = [...plain].sort().join(" ");
    const setQ = tokenSet(sortedQ);
    const compactQ = plain.join(" ").replace(/ /g, "");

    const best = new Map<string, number>();      // thứ tự chèn = thứ tự gặp đầu tiên (giống dict của Python)
    const order = new Map<string, number>();
    const near = new Set<string>();
    for (const row of this.rows) {
      let s = 0.6 * tokenSetRatioSets(setQ, row.set) + 0.4 * ratio(sortedQ, row.sorted);
      s = Math.max(s, ratio(compactQ, row.compact));
      let rel: "unit" | "mag" | null = null;
      if (sizes.length) {
        if (row.size === null) s *= 0.9;
        else if (!sizes.includes(row.size)) {
          const rels = new Set(sizes.map((z) => sizeRel(row.size!, z)));
          rel = rels.has("unit") ? "unit" : rels.has("mag") ? "mag" : null;
          s *= rel === "unit" ? 0.92 : rel === "mag" ? 0.85 : 0.6;
        }
      }
      if (!order.has(row.sku)) order.set(row.sku, order.size);
      if (s > (best.get(row.sku) ?? -1.0)) {
        best.set(row.sku, s);
        if (sizes.length && row.size !== null && !sizes.includes(row.size) && rel === "mag") near.add(row.sku);
        else near.delete(row.sku);
      }
    }

    // sort theo điểm giảm dần, hoà thì theo thứ tự gặp đầu (sort ổn định của Python) — viết tường minh để không phụ thuộc engine
    const ranked = [...best.entries()].sort((a, b) => (b[1] - a[1]) || (order.get(a[0])! - order.get(b[0])!));
    const [top, topS] = ranked[0];
    const secondS = ranked.length > 1 ? ranked[1][1] : 0.0;
    let conf = topS / 100.0;
    if (topS - secondS < 4) conf = Math.min(conf, 0.6);   // hai SKU quá sát nhau => mơ hồ
    if (near.has(top)) conf = Math.min(conf, 0.8);        // dung tích nghe lệch bậc 10: luôn để người xác nhận
    return {
      sku_id: top,
      sku_name: this.skus[top].name,
      conf: pyRoundTo(conf, 3),
      candidates: ranked.slice(0, 3).map(([k, v]) => ({ sku_id: k, name: this.skus[k].name, score: pyRoundTo(v, 1) })),
    };
  }
}
