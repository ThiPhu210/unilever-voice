import { useState } from "react";
import { NavLink, Route, Routes, Navigate } from "react-router-dom";
import { clearKey, getKey } from "./api";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Sessions from "./pages/Sessions";
import SessionDetailPage from "./pages/SessionDetail";

const IconDash = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="7" height="9" rx="2" /><rect x="14" y="3" width="7" height="5" rx="2" />
    <rect x="14" y="12" width="7" height="9" rx="2" /><rect x="3" y="16" width="7" height="5" rx="2" />
  </svg>
);
const IconChat = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z" />
  </svg>
);

export default function App() {
  const [authed, setAuthed] = useState(!!getKey());
  if (!authed) return <Login onDone={() => setAuthed(true)} />;
  const logout = () => { clearKey(); setAuthed(false); };
  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">
          <img src="/logo.png" alt="An Hòa – Art Home" />
          <div>
            <div className="brand-t">Voice<span>Coach</span></div>
            <div className="brand-s">An Hòa · Art Home</div>
          </div>
        </div>
        <nav>
          <NavLink to="/" end><IconDash />Tổng quan</NavLink>
          <NavLink to="/sessions"><IconChat />Cuộc hội thoại</NavLink>
        </nav>
        <button className="logout" onClick={logout}>Đăng xuất</button>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<Dashboard onAuthError={logout} />} />
          <Route path="/sessions" element={<Sessions onAuthError={logout} />} />
          <Route path="/sessions/:id" element={<SessionDetailPage onAuthError={logout} />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>
    </div>
  );
}
