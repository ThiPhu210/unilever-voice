import { useEffect, useMemo, useState } from "react";
import { api, downloadFile, ReportSku, SalesReport, Unauthorized, vnd, vndParts } from "../api";

type Sa = { sa_id: string; sa_name: string };

const p2 = (n: number) => String(n).padStart(2, "0");
const iso = (d: Date) => `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`;
const ago = (n: number) => { const d = new Date(); d.setDate(d.getDate() - n); return iso(d); };
const PRESETS: { label: string; range: () => [string, string] }[] = [
  { label: "Hôm nay", range: () => [ago(0), ago(0)] },
  { label: "7 ngày", range: () => [ago(6), ago(0)] },
  { label: "30 ngày", range: () => [ago(29), ago(0)] },
  { label: "Tháng này", range: () => { const d = new Date(); return [iso(new Date(d.getFullYear(), d.getMonth(), 1)), ago(0)]; } },
];

export default function Reports({ onAuthError }: { onAuthError: () => void }) {
  const [from, setFrom] = useState(ago(6));
  const [to, setTo] = useState(ago(0));
  const [sa, setSa] = useState("");
  const [declined, setDeclined] = useState(false);
  const [sas, setSas] = useState<Sa[]>([]);
  const [data, setData] = useState<SalesReport | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const fail = (e: unknown) => (e instanceof Unauthorized ? onAuthError() : setErr(e instanceof Error ? e.message : String(e)));
  const query = useMemo(() => {
    const q = new URLSearchParams({ from, to });
    if (sa) q.set("sa_id", sa);
    if (declined) q.set("include_declined", "true");
    return q.toString();
  }, [from, to, sa, declined]);
  const badRange = !from || !to || from > to;

  useEffect(() => { api<Sa[]>("/api/reports/sas").then(setSas).catch(fail); }, []);
  useEffect(() => {
    if (badRange) return;
    let alive = true;
    setErr("");
    api<SalesReport>(`/api/reports/sales?${query}`).then((d) => alive && setData(d)).catch((e) => alive && (setData(null), fail(e)));
    return () => { alive = false; };
  }, [query, badRange]);

  async function download() {
    setBusy(true); setErr("");
    try { await downloadFile(`/api/reports/sales.xlsx?${query}`, "bao-cao-ban-hang.xlsx"); }
    catch (e) { fail(e); }
    finally { setBusy(false); }
  }

  const k = data?.kpi;
  const preset = PRESETS.findIndex((p) => { const [a, b] = p.range(); return a === from && b === to; });

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Báo cáo bán hàng</h1>
          <p className="muted">Xuất doanh số của SA/BA theo ngày, theo SKU (kèm barcode) ra file Excel. Ngày tính theo giờ Việt Nam.</p>
        </div>
        <div className="tabs" role="group" aria-label="Chọn nhanh khoảng ngày">
          {PRESETS.map((p, i) => (
            <button key={p.label} className={preset === i ? "on" : ""} aria-pressed={preset === i}
              onClick={() => { const [a, b] = p.range(); setFrom(a); setTo(b); }}>{p.label}</button>
          ))}
        </div>
      </header>

      <div className="filters report-filters">
        <label className="pick"><span>Từ ngày</span><input type="date" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} /></label>
        <label className="pick"><span>Đến ngày</span><input type="date" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} /></label>
        <label className="pick">
          <span>SA/BA</span>
          <select value={sa} onChange={(e) => setSa(e.target.value)}>
            <option value="">Tất cả SA/BA</option>
            {sas.map((s) => <option key={s.sa_id} value={s.sa_id}>{s.sa_name} ({s.sa_id})</option>)}
          </select>
        </label>
        <label className="check"><input type="checkbox" checked={declined} onChange={(e) => setDeclined(e.target.checked)} />Gồm cả đơn khách từ chối</label>
        <button className="btn dl" onClick={download} disabled={busy || badRange}>{busy ? "Đang tạo file..." : "Tải file Excel"}</button>
      </div>
      {badRange && <div className="err" role="alert">Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.</div>}
      {err && <div className="err" role="alert">{err}</div>}

      {k && data && (
        <>
          <dl className="facts">
            <div><dd>{k.sessions}</dd><dt>cuộc tư vấn có đơn</dt></div>
            <div><dd>{k.orders}</dd><dt>đơn chốt</dt></div>
            <div><dd>{k.units}</dd><dt>sản phẩm<small>{k.skus} mã SKU khác nhau</small></dt></div>
            <div><dd>{vndParts(k.revenue)[0]}<i>{vndParts(k.revenue)[1]}</i></dd><dt>doanh thu ghi nhận<small>chưa gồm dòng thiếu giá</small></dt></div>
            <div className={k.missing_price ? "alert" : ""}><dd>{k.missing_price}</dd><dt>dòng thiếu giá<small>để trống trong file, SA/BA bổ sung trên app</small></dt></div>
            <div><dd>{data.line_count}</dd><dt>dòng chi tiết<small>trong sheet "Chi tiết"</small></dt></div>
          </dl>

          {data.line_count === 0 ? (
            <p className="empty">Không có đơn nào trong khoảng này{sa ? " của SA/BA đã chọn" : ""}. Thử mở rộng khoảng ngày.</p>
          ) : (
            <>
              <section>
                <h2>Theo SA/BA</h2>
                <table className="tbl">
                  <thead><tr><th>SA/BA</th><th className="n">Cuộc tư vấn</th><th className="n">Đơn</th><th className="n">Sản phẩm</th><th className="n">SKU</th><th className="n">Doanh thu</th></tr></thead>
                  <tbody>
                    {data.by_sa.map((a) => (
                      <tr key={a.sa_id}>
                        <td><b>{a.sa_name}</b><small className="sub">{a.sa_id}</small></td>
                        <td className="n">{a.sessions}</td><td className="n">{a.orders}</td><td className="n">{a.units}</td><td className="n">{a.skus}</td>
                        <td className="n"><b>{vnd(a.revenue)}</b>{a.missing_price > 0 && <small className="warn">{a.missing_price} dòng thiếu giá</small>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
              <section>
                <h2>Theo sản phẩm</h2>
                <table className="tbl">
                  <thead><tr><th>Barcode</th><th>Sản phẩm</th><th className="n">Số lượng</th><th className="n">Số đơn</th><th className="n">Giá TB</th><th className="n">Doanh thu</th></tr></thead>
                  <tbody>
                    {data.by_sku.map((s: ReportSku) => (
                      <tr key={s.sku_id}>
                        <td className="code">{s.barcode || <span className="muted">chưa có</span>}</td>
                        <td><b>{s.name}</b></td>
                        <td className="n"><b>{s.qty}</b></td><td className="n">{s.orders}</td>
                        <td className="n">{s.avg_price == null ? <span className="muted">chưa có giá</span> : vnd(s.avg_price)}</td>
                        <td className="n">{s.revenue ? vnd(s.revenue) : <span className="muted">-</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            </>
          )}
        </>
      )}
      {!data && !err && !badRange && <p className="muted">Đang tải số liệu</p>}
    </>
  );
}
