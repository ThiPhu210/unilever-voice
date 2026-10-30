import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, Overview, Unauthorized } from "../api";
import { BRAND } from "../theme";

function Kpi({ icon, tone, label, value, hint }: { icon: string; tone: string; label: string; value: string | number; hint?: string }) {
  return (
    <div className={`kpi tone-${tone}`}>
      <div className="kpi-ic">{icon}</div>
      <div className="kpi-v">{value}</div>
      <div className="kpi-l">{label}</div>
      {hint && <div className="kpi-h">{hint}</div>}
    </div>
  );
}

const RANGES: [number, string][] = [[1, "Hôm nay"], [7, "7 ngày"], [30, "30 ngày"]];
const MEDAL = ["🥇", "🥈", "🥉"];

export default function Dashboard({ onAuthError }: { onAuthError: () => void }) {
  const [days, setDays] = useState(7);
  const [data, setData] = useState<Overview | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    const load = () =>
      api<Overview>(`/api/stats/overview?days=${days}`)
        .then((d) => alive && (setData(d), setErr("")))
        .catch((e) => (e instanceof Unauthorized ? onAuthError() : setErr(String(e))));
    load();
    const t = setInterval(load, 15000); // gần realtime: làm mới mỗi 15s
    return () => { alive = false; clearInterval(t); };
  }, [days]);

  if (err) return <div className="err">{err}</div>;
  if (!data) return <div className="muted">Đang tải...</div>;
  const k = data.kpi;

  return (
    <>
      <div className="head">
        <div>
          <h2>Tổng quan</h2>
          <div className="sub">Hành vi mua sắm &amp; chất lượng tư vấn · cập nhật tự động</div>
        </div>
        <div className="seg-ctl">
          {RANGES.map(([d, l]) => (
            <button key={d} className={days === d ? "on" : ""} onClick={() => setDays(d)}>{l}</button>
          ))}
        </div>
      </div>

      <div className="kpis">
        <Kpi icon="💬" tone="orange" label="Cuộc hội thoại" value={k.sessions} />
        <Kpi icon="🧾" tone="red" label="Đơn chốt" value={k.orders} hint={`${k.confirmed} khách xác nhận · ${k.declined} từ chối`} />
        <Kpi icon="✅" tone="green" label="Khách xác nhận" value={`${k.confirm_rate}%`} />
        <Kpi icon="📦" tone="brown" label="Số lượng / đơn" value={k.avg_units_per_order} hint={`${k.avg_skus_per_order} SKU / đơn`} />
        <Kpi icon="🎯" tone="gold" label="Tuân thủ kịch bản" value={`${k.avg_compliance}%`} />
        <Kpi icon="⏳" tone="rose" label="Chờ SA xác nhận" value={k.pending_review} />
      </div>

      <div className="grid2">
        <section className="card">
          <h3>Top SKU bán chạy</h3>
          {data.top_skus.length === 0 ? <div className="muted">Chưa có dữ liệu</div> : (
            <ResponsiveContainer width="100%" height={Math.max(240, data.top_skus.length * 36)}>
              <BarChart data={data.top_skus} layout="vertical" margin={{ left: 24, right: 12 }}>
                <defs>
                  <linearGradient id="og" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stopColor={BRAND.orangeLight} /><stop offset="100%" stopColor={BRAND.orange} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#F0E3D3" />
                <XAxis type="number" allowDecimals={false} tick={{ fill: "#8A6F5C", fontSize: 12 }} />
                <YAxis type="category" dataKey="name" width={230} tick={{ fill: BRAND.brown, fontSize: 12 }} />
                <Tooltip cursor={{ fill: "rgba(232,122,0,.08)" }} />
                <Bar dataKey="qty" name="Số lượng" fill="url(#og)" radius={[0, 8, 8, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </section>

        <section className="card">
          <h3>Xu hướng theo ngày</h3>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={data.by_day} margin={{ left: -10, right: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F0E3D3" />
              <XAxis dataKey="date" tick={{ fill: "#8A6F5C", fontSize: 11 }} />
              <YAxis allowDecimals={false} tick={{ fill: "#8A6F5C", fontSize: 12 }} />
              <Tooltip /><Legend />
              <Line isAnimationActive={false} dataKey="sessions" name="Hội thoại" stroke="#B9A18C" strokeWidth={2.5} dot={{ r: 3 }} />
              <Line isAnimationActive={false} dataKey="orders" name="Đơn chốt" stroke={BRAND.red} strokeWidth={2.5} dot={{ r: 3 }} />
              <Line isAnimationActive={false} dataKey="units" name="Số lượng bán" stroke={BRAND.orange} strokeWidth={2.5} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </section>
      </div>

      <div className="grid2">
        <section className="card">
          <h3>Xếp hạng SA/BA</h3>
          <table>
            <thead><tr><th>SA/BA</th><th>Hội thoại</th><th>Đơn</th><th>Khách XN</th><th>SL</th><th>Tuân thủ</th></tr></thead>
            <tbody>
              {data.by_sa.map((s, i) => (
                <tr key={s.sa_id}>
                  <td><span className="rank">{MEDAL[i] || i + 1}</span>{s.sa_name}</td>
                  <td>{s.sessions}</td><td>{s.orders}</td><td>{s.confirmed}</td>
                  <td><b>{s.units}</b></td>
                  <td><span className={`pill ${s.avg_compliance >= 75 ? "ok" : s.avg_compliance >= 50 ? "mid" : "low"}`}>{s.avg_compliance}%</span></td>
                </tr>
              ))}
              {data.by_sa.length === 0 && <tr><td colSpan={6} className="muted">Chưa có dữ liệu</td></tr>}
            </tbody>
          </table>
        </section>

        <section className="card">
          <h3>Lý do khách từ chối / do dự</h3>
          {data.objections.length === 0 ? <div className="muted">Chưa phát hiện</div> : (
            <ul className="plain">
              {data.objections.map((o) => {
                const max = data.objections[0].count || 1;
                return (
                  <li key={o.key} className="obj">
                    <div className="obj-r"><span>{o.label}</span><b>{o.count}</b></div>
                    <div className="obj-bar"><i style={{ width: `${(o.count / max) * 100}%` }} /></div>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}
