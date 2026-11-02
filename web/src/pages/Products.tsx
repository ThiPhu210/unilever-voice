import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, dm, SkuStat, SkuStats, Unauthorized, vnd, vndParts, vndShort } from "../api";
import { BRAND } from "../theme";

const RANGES: [number, string][] = [[7, "7 ngày"], [14, "14 ngày"], [30, "30 ngày"]];
const PALETTE = ["#E07804", "#CE0C0B", "#3A2316", "#2E7D4F", "#3F6FB5", "#8A5FB0"];
type Metric = "qty" | "revenue";

function Spark({ data, color }: { data: number[]; color: string }) {
  const w = 96, h = 26, max = Math.max(1, ...data);
  const pts = data.map((v, i) => `${(i / Math.max(1, data.length - 1)) * w},${h - 2 - (v / max) * (h - 4)}`).join(" ");
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Xu hướng số lượng theo ngày">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

export default function Products({ onAuthError }: { onAuthError: () => void }) {
  const [days, setDays] = useState(14);
  const [data, setData] = useState<SkuStats | null>(null);
  const [err, setErr] = useState("");
  const [metric, setMetric] = useState<Metric>("qty");
  const [picked, setPicked] = useState<string[] | null>(null); // null = mặc định top 3

  useEffect(() => {
    let alive = true;
    const load = () =>
      api<SkuStats>(`/api/stats/skus?days=${days}`)
        .then((d) => alive && (setData(d), setErr("")))
        .catch((e) => (e instanceof Unauthorized ? onAuthError() : setErr(String(e))));
    load();
    const t = setInterval(load, 15000);
    return () => { alive = false; clearInterval(t); };
  }, [days]);

  const sel = useMemo(() => {
    if (!data) return [];
    const ids = picked ?? data.skus.slice(0, 3).map((s) => s.sku_id);
    return ids.filter((id) => data.skus.some((s) => s.sku_id === id));
  }, [data, picked]);
  const colorOf = (id: string) => PALETTE[Math.max(0, sel.indexOf(id)) % PALETTE.length];
  const toggle = (id: string) => {
    const cur = sel;
    setPicked(cur.includes(id) ? cur.filter((x) => x !== id) : cur.length >= PALETTE.length ? cur : [...cur, id]);
  };

  if (err) return <div className="err" role="alert">{err}</div>;
  if (!data) return <p className="muted">Đang tải số liệu</p>;

  const chart = data.dates.map((d, i) => {
    const row: Record<string, string | number> = { label: dm(d) };
    for (const s of data.skus) if (sel.includes(s.sku_id)) row[s.sku_id] = s.by_day[i][metric];
    return row;
  });
  const totalQty = data.skus.reduce((a, s) => a + s.qty, 0);
  const totalRev = data.skus.reduce((a, s) => a + s.revenue, 0);
  const fmtY = (v: number) => (metric === "revenue" ? vndShort(v) : String(v));

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Sản phẩm</h1>
          <p className="muted">Khách đang mua gì, bao nhiêu, giá bao nhiêu, theo từng ngày. Không tính đơn khách từ chối.</p>
        </div>
        <div className="tabs" role="tablist">
          {RANGES.map(([d, l]) => (
            <button key={d} role="tab" aria-selected={days === d} className={days === d ? "on" : ""} onClick={() => setDays(d)}>{l}</button>
          ))}
        </div>
      </header>

      <dl className="facts three">
        <div><dd>{data.skus.length}</dd><dt>mã SKU có bán</dt></div>
        <div><dd>{totalQty}</dd><dt>sản phẩm đã bán</dt></div>
        <div><dd>{vndParts(totalRev)[0]}<i>{vndParts(totalRev)[1]}</i></dd><dt>doanh thu ghi nhận<small>chưa gồm dòng thiếu giá</small></dt></div>
      </dl>

      {data.skus.length === 0 ? (
        <p className="empty">Chưa có đơn nào trong khoảng này. Khi SA/BA ghi âm và chốt đơn trên app, xu hướng sẽ hiện ở đây.</p>
      ) : (
        <>
          <section className="tint">
            <div className="chart-head">
              <h2>Xu hướng theo ngày</h2>
              <div className="tabs small" role="tablist">
                <button role="tab" aria-selected={metric === "qty"} className={metric === "qty" ? "on" : ""} onClick={() => setMetric("qty")}>Số lượng</button>
                <button role="tab" aria-selected={metric === "revenue"} className={metric === "revenue" ? "on" : ""} onClick={() => setMetric("revenue")}>Doanh thu</button>
              </div>
            </div>
            <div className="chips" role="group" aria-label="Chọn sản phẩm để so sánh">
              {data.skus.slice(0, 12).map((s) => {
                const on = sel.includes(s.sku_id);
                return (
                  <button key={s.sku_id} type="button" aria-pressed={on} className={`chip ${on ? "on" : ""}`} onClick={() => toggle(s.sku_id)}
                    style={on ? { borderColor: colorOf(s.sku_id) } : undefined}>
                    <i style={{ background: on ? colorOf(s.sku_id) : "#CBB9A8" }} />{s.name}
                  </button>
                );
              })}
            </div>
            {sel.length === 0 ? <p className="empty">Chọn ít nhất một sản phẩm để xem xu hướng.</p> : (
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={chart} margin={{ left: -6, right: 10, top: 10 }}>
                  <CartesianGrid vertical={false} stroke="#EBCFA9" />
                  <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: BRAND.muted, fontSize: 12 }} interval="preserveStartEnd" />
                  <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fill: BRAND.muted, fontSize: 12 }} tickFormatter={fmtY} width={metric === "revenue" ? 74 : 40} />
                  <Tooltip formatter={(v: number, id: string) => [metric === "revenue" ? vnd(v) : v, data.skus.find((s) => s.sku_id === id)?.name ?? id]} />
                  {sel.map((id) => (
                    <Line key={id} type="monotone" dataKey={id} stroke={colorOf(id)} strokeWidth={2.5} dot={{ r: 3 }} isAnimationActive={false} />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            )}
          </section>

          <section>
            <h2>Chi tiết từng sản phẩm</h2>
            <table className="tbl">
              <thead><tr><th>Sản phẩm</th><th>Xu hướng</th><th className="n">Số lượng</th><th className="n">Số đơn</th><th className="n">Giá TB</th><th className="n">Doanh thu</th><th>Bán gần nhất</th></tr></thead>
              <tbody>
                {data.skus.map((s: SkuStat) => (
                  <tr key={s.sku_id}>
                    <td><b>{s.name}</b></td>
                    <td><Spark data={s.by_day.map((d) => d.qty)} color={sel.includes(s.sku_id) ? colorOf(s.sku_id) : BRAND.muted} /></td>
                    <td className="n"><b>{s.qty}</b></td>
                    <td className="n">{s.orders}</td>
                    <td className="n">{s.avg_price == null ? <span className="muted">chưa có giá</span> : vnd(s.avg_price)}</td>
                    <td className="n">{s.revenue ? vnd(s.revenue) : <span className="muted">-</span>}</td>
                    <td>{dm(s.last_sold)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </>
  );
}
