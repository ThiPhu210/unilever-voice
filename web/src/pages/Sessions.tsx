import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtDur, fmtTime, SessionRow, Unauthorized } from "../api";

const STATUS: Record<string, string> = {
  queued: "Đang chờ", processing: "Đang dịch", done: "Xong", error: "Lỗi",
};

function ConfirmBadges({ c }: { c: string[] }) {
  if (!c.length) return <span className="muted">–</span>;
  return <>{c.map((x, i) => (
    <span key={i} className={`badge ${x}`}>{x === "yes" ? "Khách đồng ý" : x === "no" ? "Khách từ chối" : "Khách im lặng"}</span>
  ))}</>;
}

export default function Sessions({ onAuthError }: { onAuthError: () => void }) {
  const [rows, setRows] = useState<SessionRow[]>([]);
  const [sa, setSa] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    const load = () =>
      api<SessionRow[]>("/api/sessions?limit=200")
        .then((d) => alive && (setRows(d), setErr("")))
        .catch((e) => (e instanceof Unauthorized ? onAuthError() : setErr(String(e))));
    load();
    const t = setInterval(load, 8000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const sas = useMemo(() => Array.from(new Set(rows.map((r) => r.sa_name))), [rows]);
  const shown = sa ? rows.filter((r) => r.sa_name === sa) : rows;

  return (
    <>
      <div className="head">
        <div><h2>Cuộc hội thoại</h2><div className="sub">Lịch sử tư vấn của SA/BA · bấm Xem để nghe lại và đọc transcript</div></div>
        <select value={sa} onChange={(e) => setSa(e.target.value)}>
          <option value="">Tất cả SA/BA</option>
          {sas.map((s) => <option key={s}>{s}</option>)}
        </select>
      </div>
      {err && <div className="err">{err}</div>}
      <section className="card">
        <table>
          <thead><tr><th>Thời gian</th><th>SA/BA</th><th>Cửa hàng</th><th>Thời lượng</th><th>Trạng thái</th><th>Đơn</th><th>SL</th><th>Phản hồi khách</th><th /></tr></thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.id}>
                <td>{fmtTime(r.created_at)}</td><td><span className="avatar">{r.sa_name.trim().split(" ").pop()?.[0]?.toUpperCase()}</span>{r.sa_name}</td><td>{r.store || "–"}</td>
                <td>{fmtDur(r.duration)}</td>
                <td><span className={`badge st-${r.status}`}>{STATUS[r.status] || r.status}</span></td>
                <td>{r.orders}{r.pending_review ? <span className="badge warn">cần XN</span> : null}</td>
                <td>{r.units}</td>
                <td><ConfirmBadges c={r.confirm} /></td>
                <td><Link to={`/sessions/${r.id}`}>Xem</Link></td>
              </tr>
            ))}
            {shown.length === 0 && <tr><td colSpan={9} className="muted">Chưa có cuộc hội thoại nào</td></tr>}
          </tbody>
        </table>
      </section>
    </>
  );
}
