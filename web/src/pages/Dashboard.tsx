import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, Overview, Unauthorized } from "../api";
import { BRAND } from "../theme";

const RANGES: [number, string][] = [[1, "Hôm nay"], [7, "7 ngày"], [30, "30 ngày"]];
const dm = (d: string) => { const [, m, day] = d.split("-"); return `${day}/${m}`; };

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
    const t = setInterval(load, 15000);
    return () => { alive = false; clearInterval(t); };
  }, [days]);

  if (err) return <div className="err" role="alert">{err}</div>;
  if (!data) return <p className="muted">Đang tải số liệu</p>;
  const k = data.kpi;
  const max = Math.max(1, ...data.top_skus.map((s) => s.qty));
  const maxObj = Math.max(1, ...data.objections.map((o) => o.count));

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Tổng quan</h1>
          <p className="muted">Số liệu tự cập nhật mỗi 15 giây.</p>
        </div>
        <div className="tabs" role="tablist">
          {RANGES.map(([d, l]) => (
            <button key={d} role="tab" aria-selected={days === d} className={days === d ? "on" : ""} onClick={() => setDays(d)}>{l}</button>
          ))}
        </div>
      </header>

      <dl className="facts">
        <div><dd>{k.sessions}</dd><dt>cuộc hội thoại</dt></div>
        <div><dd>{k.orders}</dd><dt>đơn chốt<small>{k.confirmed} khách đồng ý, {k.declined} từ chối</small></dt></div>
        <div><dd>{k.confirm_rate}<i>%</i></dd><dt>khách đồng ý</dt></div>
        <div><dd>{k.avg_units_per_order}</dd><dt>sản phẩm mỗi đơn<small>{k.avg_skus_per_order} mã SKU mỗi đơn</small></dt></div>
        <div><dd>{k.avg_compliance}<i>%</i></dd><dt>tuân thủ kịch bản</dt></div>
        <div className={k.pending_review ? "alert" : ""}><dd>{k.pending_review}</dd><dt>đơn chờ SA xác nhận</dt></div>
      </dl>

      <section className="best">
        <h2>Bán chạy nhất</h2>
        {data.top_skus.length === 0 ? (
          <p className="empty">Chưa có đơn nào trong khoảng này. Khi SA/BA ghi âm và chốt đơn trên app, sản phẩm sẽ hiện ở đây.</p>
        ) : (
          <ol className="bars">
            {data.top_skus.map((s, i) => (
              <li key={s.sku_id} className={i < 5 ? "lg" : "sm"}>
                <i style={{ width: `${Math.max(6, (s.qty / max) * 100)}%` }} />
                <span className="nm">{s.name}</span>
                <span className="qt"><b>{s.qty}</b><small>{s.orders} đơn</small></span>
              </li>
            ))}
          </ol>
        )}
      </section>

      <div className="two">
        <section className="tint">
          <h2>Theo ngày</h2>
          <div className="legend"><span><i className="sq o" />Sản phẩm bán</span><span><i className="sq b" />Đơn chốt</span></div>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={data.by_day.map((d) => ({ ...d, label: dm(d.date) }))} margin={{ left: -18, right: 4, top: 6 }} barGap={3}>
              <CartesianGrid vertical={false} stroke="#EBCFA9" />
              <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: BRAND.muted, fontSize: 12 }} />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fill: BRAND.muted, fontSize: 12 }} />
              <Tooltip cursor={{ fill: "rgba(224,120,4,.1)" }} />
              <Bar dataKey="units" name="Sản phẩm bán" fill={BRAND.frame} maxBarSize={26} isAnimationActive={false} />
              <Bar dataKey="orders" name="Đơn chốt" fill={BRAND.ink} maxBarSize={26} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </section>

        <section>
          <h2>Khách do dự vì</h2>
          {data.objections.length === 0 ? <p className="empty">Chưa nghe thấy lý do từ chối nào.</p> : (
            <ul className="obj">
              {data.objections.map((o) => (
                <li key={o.key}>
                  <div><span>{o.label}</span><b>{o.count}</b></div>
                  <i style={{ width: `${(o.count / maxObj) * 100}%` }} />
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section>
        <h2>Từng SA/BA</h2>
        <table className="tbl">
          <thead><tr><th>Tên</th><th className="n">Hội thoại</th><th className="n">Đơn</th><th className="n">Khách đồng ý</th><th className="n">Sản phẩm</th><th>Tuân thủ kịch bản</th></tr></thead>
          <tbody>
            {data.by_sa.map((s) => (
              <tr key={s.sa_id}>
                <td><b>{s.sa_name}</b></td><td className="n">{s.sessions}</td><td className="n">{s.orders}</td>
                <td className="n">{s.confirmed}</td><td className="n"><b>{s.units}</b></td>
                <td><span className="meter"><i style={{ width: `${s.avg_compliance}%` }} className={s.avg_compliance < 50 ? "low" : ""} /></span>{s.avg_compliance}%</td>
              </tr>
            ))}
            {data.by_sa.length === 0 && <tr><td colSpan={6} className="empty">Chưa có SA/BA nào ghi âm trong khoảng này.</td></tr>}
          </tbody>
        </table>
      </section>
    </>
  );
}
