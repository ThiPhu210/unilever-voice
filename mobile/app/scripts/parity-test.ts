/**
 * So sánh parser TypeScript (chạy trên máy) với parser Python (server) trên cùng bộ transcript.
 * Sinh dữ liệu:  cd backend && python scripts/export_parser_fixtures.py ../mobile/app/scripts/fixtures
 * Chạy:          cd mobile/app && npm run test:parser
 */
import fs from "fs";
import path from "path";
import { Catalog, parseTranscript } from "../src/parser";

const dir = path.join(__dirname, "fixtures");
const catalog = new Catalog(JSON.parse(fs.readFileSync(path.join(dir, "catalog.json"), "utf8")));
const cases: { text: string; expected: any }[] = JSON.parse(fs.readFileSync(path.join(dir, "cases.json"), "utf8"));

// Chuẩn hoá để so: bỏ khác biệt vô hại của JSON (số float nhỏ do làm tròn hiển thị)
const canon = (v: any): any =>
  Array.isArray(v) ? v.map(canon)
  : v && typeof v === "object" ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, canon(v[k])]))
  : typeof v === "number" ? Math.round(v * 1e6) / 1e6 : v;

let bad = 0, withOrders = 0;
const t0 = Date.now();
for (const c of cases) {
  const got = parseTranscript(c.text, catalog);
  if (c.expected.orders.length) withOrders++;
  if (JSON.stringify(canon(got)) !== JSON.stringify(canon(c.expected))) {
    if (bad++ < 5) {
      console.log("LỆCH:", c.text);
      console.log("  python:", JSON.stringify(canon(c.expected)).slice(0, 600));
      console.log("  ts    :", JSON.stringify(canon(got)).slice(0, 600));
    }
  }
}
const ms = Date.now() - t0;
console.log(`${cases.length} ca (${withOrders} có đơn), lệch ${bad}, ${ms} ms (${(ms / cases.length).toFixed(1)} ms/ca)`);
process.exit(bad ? 1 : 0);
