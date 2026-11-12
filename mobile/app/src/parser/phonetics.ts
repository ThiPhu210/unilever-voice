/**
 * Port của parser/phonetics.py (chỉ phần fold): gấp mọi cách phát âm vùng miền về CÙNG MỘT "khoá âm".
 * Xem docstring bản Python để biết các lớp âm đầu (S/B/L/C/K/G/N/X/T), âm cuối, nguyên âm.
 */
import { stripAccents } from "./normalize";

const ONSET: [RegExp, string][] = ([
  ["ngh?", "N"], ["nh", "L"], ["tr|ch", "C"], ["kh", "X"], ["th", "T"], ["ph|[bpfv]", "B"],
  ["qu", "o"], ["w", "o"], ["g(?=o[ae])", ""], ["gh|g(?!i)", "G"], ["gi(?=[aeou])", "S"],
  ["gi|[drzjsx]", "S"], ["[ckq]", "K"], ["[ln]", "L"],
] as [string, string][]).map(([src, cls]) => [new RegExp("^(?:" + src + ")"), cls]);

const VOWELS = "aeiouy";
const DIGRAPH_END = /(ngh|ng|nh|tr|ch|kh|th|ph|gh|gi|qu)$/;
const RIME = /^([aeiouy]+)(ch|ng|nh|[tcpnm])?$/;
const CODA: Record<string, string> = { ch: "k", t: "k", c: "k", p: "k", ng: "n", nh: "n", n: "n", m: "m" };
const ALPHA = /^[A-Za-z]+$/;

/** Tách từ Latin dài thành âm tiết: 'matcha' -> mat|cha, 'hazeline' -> ha|ze|li|ne. */
function syllabify(t: string): string[] {
  const parts = t.match(/[aeiouy]+|[^aeiouy]+/g) ?? [];
  if (!parts.some((p) => VOWELS.includes(p[0]))) return [t];
  const syls: string[] = [];
  let onset = "";
  parts.forEach((p, k) => {
    if (VOWELS.includes(p[0])) { syls.push(onset + p); onset = ""; }
    else if (!syls.length) onset = p;
    else if (k === parts.length - 1) syls[syls.length - 1] += p;
    else {
      const m = DIGRAPH_END.exec(p);
      const cut = m ? p.length - m[0].length : p.length - 1;
      syls[syls.length - 1] += p.slice(0, cut);
      onset = p.slice(cut);
    }
  });
  return syls;
}

function syllableKey(s: string): string {
  if (!ALPHA.test(s)) return s;   // số, dấu câu, mã hàng giữ nguyên
  let onset = "";
  for (const [rx, cls] of ONSET) {
    const m = rx.exec(s);
    if (m) {
      onset = cls; s = s.slice(m[0].length);
      if (cls === "S" && m[0].startsWith("gi") && m[0].length === 2 && !VOWELS.includes(s.slice(0, 1))) s = "i" + s;
      break;
    }
  }
  const m = RIME.exec(s);
  if (m) {
    let v = m[1].replace(/y/g, "i");
    if (!m[2]) { v = v.replace(/ay$/, "ai"); v = v.replace(/au$/, "ao"); }
    s = v + (CODA[m[2] ?? ""] ?? "");
  }
  return (onset + s).replace(/(.)\1+/g, "$1");
}

/** Chữ (hoặc list token) -> list khoá âm, mỗi âm tiết một phần tử. */
export function fold(text: string | string[]): string[] {
  const toks = typeof text === "string" ? text.split(/\s+/).filter(Boolean) : text;
  const out: string[] = [];
  for (let t of toks) {
    t = stripAccents(t.toLowerCase());
    for (const s of ALPHA.test(t) ? syllabify(t) : [t]) out.push(syllableKey(s));
  }
  return out;
}
