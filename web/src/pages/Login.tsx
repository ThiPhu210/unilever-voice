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
      <form className="card" onSubmit={submit}>
        <h1>Voice<span>Coach</span></h1>
        <p className="muted">Đăng nhập Coach Console</p>
        <input type="password" placeholder="API key" value={key} onChange={(e) => setK(e.target.value)} autoFocus />
        {err && <div className="err">{err}</div>}
        <button disabled={busy || !key}>{busy ? "Đang kiểm tra..." : "Đăng nhập"}</button>
      </form>
    </div>
  );
}
