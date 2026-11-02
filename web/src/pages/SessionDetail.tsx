import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, audioUrl, fmtDur, fmtTime, SessionDetail, Unauthorized } from "../api";

const plain = (s: string) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").toLowerCase();
const isClosing = (s: string) => /\bvay minh ch[oua]t\b/.test(plain(s)) || (/\bch[oua]t\b/.test(plain(s)) && plain(s).includes("cam on"));
const REPLY: Record<string, string> = { yes: "Khách đồng ý", no: "Khách từ chối", none: "Khách im lặng" };

const Tick = ({ ok }: { ok: boolean }) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" stroke={ok ? "#2E7D4F" : "#CE0C0B"} aria-label={ok ? "Đạt" : "Chưa đạt"}>
    {ok ? <path d="M5 12.5l4.5 4.5L19 7.5" /> : <path d="M6 6l12 12M18 6L6 18" />}
  </svg>
);

export default function SessionDetailPage({ onAuthError }: { onAuthError: () => void }) {
  const { id = "" } = useParams();
  const [s, setS] = useState<SessionDetail | null>(null);
  const [err, setErr] = useState("");
  const [now, setNow] = useState(0);
  const audio = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api<SessionDetail>(`/api/sessions/${id}`)
        .then((d) => { if (alive) { setS(d); setErr(""); } })
        .catch((e) => (e instanceof Unauthorized ? onAuthError() : setErr(String(e))));
    load();
    const t = setInterval(() => { if (!s || s.status === "queued" || s.status === "processing") load(); }, 4000);
    return () => { alive = false; clearInterval(t); };
  }, [id, s?.status]);

  const seek = (t: number) => { if (audio.current) { audio.current.currentTime = t; audio.current.play(); } };

  if (err) return <div className="err" role="alert">{err}</div>;
  if (!s) return <p className="muted">Đang tải cuộc hội thoại</p>;
  const passed = s.coaching.checklist.filter((c) => c.passed).length;

  return (
    <>
      <Link to="/sessions" className="back">Quay lại danh sách</Link>
      <header className="page-head">
        <div>
          <h1>{s.sa_name}</h1>
          <p className="muted">{fmtTime(s.created_at)}{s.duration != null ? `, thời lượng ${fmtDur(s.duration)}` : ""}{s.store ? `, ${s.store}` : ""}</p>
        </div>
      </header>

      {s.status === "error" && <div className="err" role="alert">Chưa xử lý được file ghi âm: {s.error}. Thử ghi âm lại, hoặc gửi lỗi này cho quản trị viên.</div>}
      {(s.status === "queued" || s.status === "processing") && <div className="note">Đang dịch giọng nói thành văn bản. Trang tự cập nhật khi xong.</div>}

      <div className="detail">
        <div>
          {s.has_audio && <audio ref={audio} controls src={audioUrl(s.id)} onTimeUpdate={(e) => setNow(e.currentTarget.currentTime)} />}
          <h2>Nội dung hội thoại</h2>
          {s.segments.length > 0 ? (
            <ol className="tx">
              {s.segments.map((g, i) => {
                const active = now >= g.start && now < g.end;
                const closing = isClosing(g.text);
                return (
                  <li key={i} className={`${active ? "active" : ""} ${closing ? "closing" : ""}`}>
                    <button onClick={() => seek(g.start)}>
                      <time>{fmtDur(g.start)}</time>
                      <span>{g.text}{closing && <em>Câu chốt đơn</em>}</span>
                    </button>
                  </li>
                );
              })}
            </ol>
          ) : <p className="plain-tx">{s.transcript_text || "Chưa có nội dung."}</p>}
        </div>

        <div className="side-col">
          <h2>Đơn khách chốt</h2>
          {s.orders.length === 0 && <p className="empty">Không nghe thấy câu chốt đơn trong cuộc này.</p>}
          {s.orders.map((o, k) => (
            <div key={o.id} className="order">
              <div className="order-h">
                <h3>Đơn {k + 1}</h3>
                <span className={`st r-${o.customer_confirm}`}>{REPLY[o.customer_confirm]}</span>
              </div>
              <table>
                <tbody>
                  {o.items.map((it, i) => (
                    <tr key={i}>
                      <td>{it.sku_name}{it.manual && <small className="sub">SA đã sửa tay</small>}{it.need_confirm && !o.reviewed && <small className="warn">Chưa chắc chắn ({Math.round(it.conf * 100)}%)</small>}</td>
                      <td className="q">{it.qty}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {o.needs_review && !o.reviewed ? <p className="warn-line">SA cần xác nhận lại đơn này trên app.</p> : null}
            </div>
          ))}

          <h2>Tuân thủ kịch bản</h2>
          <p className="muted score">{passed} trên {s.coaching.checklist.length} mục đạt</p>
          <ul className="checks">
            {s.coaching.checklist.map((c) => <li key={c.key}><Tick ok={c.passed} />{c.label}</li>)}
          </ul>
          {s.coaching.objections.length > 0 && <p className="muted">Khách có dấu hiệu do dự: {s.coaching.objections.join(", ")}.</p>}
        </div>
      </div>
    </>
  );
}
