import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, audioUrl, fmtDur, fmtTime, SessionDetail, Unauthorized } from "../api";

const plain = (s: string) =>
  s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").toLowerCase();
const isClosing = (s: string) => /\bch[oua]t\b/.test(plain(s)) && plain(s).includes("cam on") || /\bvay minh ch[oua]t\b/.test(plain(s));

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

  if (err) return <div className="err">{err}</div>;
  if (!s) return <div className="muted">Đang tải...</div>;

  return (
    <>
      <div className="head">
        <div>
          <Link to="/sessions" className="back">← Danh sách</Link>
          <h2>{s.sa_name} <span className="muted">· {fmtTime(s.created_at)} · {fmtDur(s.duration)}</span></h2>
        </div>
      </div>

      {s.status === "error" && <div className="err">Lỗi xử lý: {s.error}</div>}
      {(s.status === "queued" || s.status === "processing") && <div className="note">Đang dịch giọng nói ({s.status})... trang sẽ tự cập nhật.</div>}

      {s.has_audio && (
        <section className="card">
          <audio ref={audio} controls src={audioUrl(s.id)} style={{ width: "100%" }}
                 onTimeUpdate={(e) => setNow(e.currentTarget.currentTime)} />
        </section>
      )}

      <div className="grid2 wide-left">
        <section className="card">
          <h3>Transcript</h3>
          {s.segments.length > 0 ? (
            <div className="transcript">
              {s.segments.map((g, i) => {
                const active = now >= g.start && now < g.end;
                const closing = isClosing(g.text);
                return (
                  <div key={i} className={`seg${active ? " active" : ""}${closing ? " closing" : ""}`} onClick={() => seek(g.start)}>
                    <span className="ts">{fmtDur(g.start)}</span>
                    <span>{g.text}</span>
                    {closing && <span className="badge yes">Câu chốt</span>}
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="pre">{s.transcript_text || "Chưa có transcript"}</p>
          )}
        </section>

        <div>
          <section className="card">
            <h3>Đơn khách chốt</h3>
            {s.orders.length === 0 && <div className="muted">Không phát hiện câu chốt đơn.</div>}
            {s.orders.map((o, k) => (
              <div key={o.id} className="order">
                <div className="order-h">
                  <b>Đơn {k + 1}</b>
                  <span className={`badge ${o.customer_confirm}`}>
                    {o.customer_confirm === "yes" ? "Khách đồng ý" : o.customer_confirm === "no" ? "Khách từ chối" : "Khách im lặng"}
                  </span>
                  {o.needs_review && !o.reviewed ? <span className="badge warn">chờ SA xác nhận</span> : null}
                </div>
                <table>
                  <thead><tr><th>SKU</th><th>SL</th><th>Tin cậy</th></tr></thead>
                  <tbody>
                    {o.items.map((it, i) => (
                      <tr key={i}>
                        <td>{it.sku_name}{it.manual && <span className="badge">SA sửa</span>}</td>
                        <td><b>{it.qty}</b></td>
                        <td className={it.need_confirm ? "low" : ""}>{Math.round(it.conf * 100)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </section>

          <section className="card">
            <h3>Tuân thủ kịch bản <span className="score">{s.coaching.score}%</span></h3>
            <ul className="plain">
              {s.coaching.checklist.map((c) => (
                <li key={c.key}><span>{c.label}</span><b className={c.passed ? "ok" : "bad"}>{c.passed ? "✓" : "✗"}</b></li>
              ))}
            </ul>
            {s.coaching.objections.length > 0 && <p className="muted">Khách do dự: {s.coaching.objections.join(", ")}</p>}
          </section>
        </div>
      </div>
    </>
  );
}
