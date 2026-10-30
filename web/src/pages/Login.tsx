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
      setErr("API key không đúng hoặc không kết nối được server.");
    } finally { setBusy(false); }
  }

  return (
    <div className="login">
      <div className="hero">
        <i className="blob b1" /><i className="blob b2" /><i className="blob b3" />
        <div className="hero-in">
          <img src="/logo.png" alt="An Hòa – Art Home" className="hero-logo" />
          <h1>Voice Coach</h1>
          <p>Ghi nhận, dịch và phân tích hội thoại tư vấn của SA/BA.<br />Hiểu khách hàng đang mua gì, tư vấn ra sao – theo thời gian thực.</p>
        </div>
      </div>
      <div className="login-side">
        <form className="login-card" onSubmit={submit}>
          <h2>Chào mừng trở lại 👋</h2>
          <p className="muted">Đăng nhập Coach Console</p>
          <label>API key</label>
          <input type="password" placeholder="Nhập API key" value={key} onChange={(e) => setK(e.target.value)} autoFocus />
          {err && <div className="err">{err}</div>}
          <button className="btn" disabled={busy || !key}>{busy ? "Đang kiểm tra..." : "Đăng nhập"}</button>
          <div className="foot">An Hòa · Art Home Company</div>
        </form>
      </div>
    </div>
  );
}
