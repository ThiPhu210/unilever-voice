import { useState } from "react";
import { api, setKey, clearKey } from "../api";

export default function Login({ onDone }: { onDone: () => void }) {
  const [key, setK] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    setKey(key.trim());
    try {
      await api("/api/stats/overview?days=1");
      onDone();
    } catch {
      clearKey();
      setErr("API key chưa đúng, hoặc chưa kết nối được server. Kiểm tra lại key và thử lại.");
    } finally { setBusy(false); }
  }

  return (
    <div className="login">
      <section className="login-brand">
        <img src="/logo.png" alt="An Hòa – Art Home" />
        <h1>Nghe khách hàng nói gì,<br />xem SA/BA tư vấn ra sao.</h1>
        <p>Mỗi cuộc hội thoại được ghi lại, dịch thành văn bản và gắn với đơn hàng khách đã chốt.</p>
      </section>
      <section className="login-form">
        <form onSubmit={submit}>
          <h2>Đăng nhập</h2>
          <label htmlFor="k">API key</label>
          <input id="k" type="password" value={key} onChange={(e) => setK(e.target.value)} autoFocus autoComplete="current-password" />
          <span className="hint">Quản trị viên cấp key này cho bạn.</span>
          {err && <div className="err" role="alert">{err}</div>}
          <button className="btn" disabled={busy || !key}>{busy ? "Đang kiểm tra" : "Đăng nhập"}</button>
        </form>
      </section>
    </div>
  );
}
