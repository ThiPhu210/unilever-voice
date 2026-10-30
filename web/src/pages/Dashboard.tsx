import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, Overview, Unauthorized } from "../api";

function Kpi({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="kpi">
      <div className="kpi-v">{value}</div>
      <div className="kpi-l">{label}</div>
      {hint && <div className="kpi-h">{hint}</div>}
    </div>
  );
}

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
        <h2>Tổng quan</h2>
        <select value={days} onChange={(e) => setDays(+e.target.value)}>
          <option value={1}>Hôm nay</option><option value={7}>7 ngày</option><option value={30}>30 ngày</option>
        </select>
      </div>

      <div className="kpis">
        <Kpi label="Cuộc hội thoại" value={k.sessions} />
        <Kpi label="Đơn chốt" value={k.orders} hint={`${k.confirmed} khách xác nhận · ${k.declined} từ chối`} />
        <Kpi label="Tỷ lệ khách xác nhận" value={`${k.confirm_rate}%`} />
        <Kpi label="SL / đơn" value={k.avg_units_per_order} hint={`${k.avg_skus_per_order} SKU / đơn`} />
        <Kpi label="Điểm tuân thủ kịch bản" value={`${k.avg_compliance}%`} />
        <Kpi label="Chờ SA xác nhận" value={k.pending_review} />
      </div>

      <div className="grid2">
        <section className="card">
          <h3>Top SKU (số lượng)</h3>
          {data.top_skus.length === 0 ? <div className="muted">Chưa có dữ liệu</div> : (
            <ResponsiveContainer width="100%" height={Math.max(220, data.top_skus.length * 34)}>
              <BarChart data={data.top_skus} layout="vertical" margin={{ left: 30 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" allowDecimals={false} />
                <YAxis type="category" dataKey="name" width={190} tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="qty" name="Số lượng" fill="#1f5eff" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </section>

        <section className="card">
          <h3>Xu hướng theo ngày</h3>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={data.by_day}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} />
              <Tooltip /><Legend />
              <Line dataKey="sessions" name="Hội thoại" stroke="#8a94a6" />
              <Line dataKey="orders" name="Đơn chốt" stroke="#1f5eff" />
              <Line dataKey="units" name="Số lượng bán" stroke="#16a34a" />
            </LineChart>
          </ResponsiveContainer>
        </section>
      </div>

      <div className="grid2">
        <section className="card">
          <h3>Xếp hạng SA/BA</h3>
          <table>
            <thead><tr><th>SA/BA</th><th>HT</th><th>Đơn</th><th>Khách XN</th><th>SL</th><th>Tuân thủ</th></tr></thead>
            <tbody>
              {data.by_sa.map((s) => (
                <tr key={s.sa_id}>
                  <td>{s.sa_name}</td><td>{s.sessions}</td><td>{s.orders}</td><td>{s.confirmed}</td>
                  <td><b>{s.units}</b></td><td>{s.avg_compliance}%</td>
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
              {data.objections.map((o) => <li key={o.key}><span>{o.label}</span><b>{o.count}</b></li>)}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}
