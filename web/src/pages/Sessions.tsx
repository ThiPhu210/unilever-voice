import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtDur, fmtTime, SessionRow, Unauthorized } from "../api";

const STATUS: Record<string, string> = { queued: "Đang chờ", processing: "Đang dịch", done: "Đã xong", error: "Lỗi" };
const REPLY: Record<string, string> = { yes: "Khách đồng ý", no: "Khách từ chối", none: "Khách im lặng" };

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

  const names = useMemo(() => Array.from(new Set(rows.map((r) => r.sa_name))), [rows]);
  const shown = sa ? rows.filter((r) => r.sa_name === sa) : rows;

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Cuộc hội thoại</h1>
          <p className="muted">Mở một cuộc để nghe lại và đọc nội dung.</p>
        </div>
        <label className="pick">
          <span>Lọc theo</span>
          <select value={sa} onChange={(e) => setSa(e.target.value)}>
            <option value="">Tất cả SA/BA</option>
            {names.map((s) => <option key={s}>{s}</option>)}
          </select>
        </label>
      </header>
      {err && <div className="err" role="alert">{err}</div>}
      <table className="tbl list">
        <thead><tr><th>Thời gian</th><th>SA/BA</th><th className="n">Thời lượng</th><th>Xử lý</th><th>Đơn chốt</th><th>Phản hồi của khách</th><th /></tr></thead>
        <tbody>
          {shown.map((r) => (
            <tr key={r.id}>
              <td>{fmtTime(r.created_at)}</td>
              <td><b>{r.sa_name}</b>{r.store && <small className="sub">{r.store}</small>}</td>
              <td className="n">{fmtDur(r.duration)}</td>
              <td><span className={`st st-${r.status}`}>{STATUS[r.status] || r.status}</span></td>
              <td>{r.orders ? `${r.orders} đơn, ${r.units} sản phẩm` : <span className="muted">Không có đơn</span>}
                {r.pending_review > 0 && <small className="warn">Cần SA xác nhận</small>}</td>
              <td>{r.confirm.length ? r.confirm.map((c, i) => <span key={i} className={`st r-${c}`}>{REPLY[c] || c}</span>) : <span className="muted">-</span>}</td>
              <td className="act"><Link to={`/sessions/${r.id}`}>Mở</Link></td>
            </tr>
          ))}
          {shown.length === 0 && <tr><td colSpan={7} className="empty">Chưa có cuộc hội thoại nào. Khi SA/BA ghi âm trên app, dữ liệu sẽ hiện ở đây.</td></tr>}
        </tbody>
      </table>
    </>
  );
}
