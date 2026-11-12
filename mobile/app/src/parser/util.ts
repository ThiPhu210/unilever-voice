/**
 * Làm tròn giống round(x, digits) của Python: dựa trên giá trị nhị phân CHÍNH XÁC của số thực, hoà (đúng .5) thì về số chẵn.
 * (Math.round / toFixed làm tròn hoà lên nên có thể lệch 0.001 ở ngưỡng conf 0.85 / 0.6.)
 */
export function pyRoundTo(x: number, digits: number): number {
  const exact = x.toFixed(30);   // double gần 1e-16 nên 30 chữ số thập phân là khai triển chính xác
  const dot = exact.indexOf(".");
  const frac = exact.slice(dot + 1);
  const isTie = frac[digits] === "5" && /^0*$/.test(frac.slice(digits + 1));
  if (!isTie) return Number(x.toFixed(digits));
  const kept = exact.slice(0, dot + 1 + digits);            // phần giữ lại, bỏ chữ số "5" cuối
  const lastDigit = Number(kept[kept.length - 1] === "." ? kept[kept.length - 2] : kept[kept.length - 1]);
  const down = Number(kept);
  if (lastDigit % 2 === 0) return down;                     // chẵn -> giữ
  const step = Math.pow(10, -digits);
  return Number((down + (x < 0 ? -step : step)).toFixed(digits));
}
