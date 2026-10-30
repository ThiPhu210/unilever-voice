import { useState } from "react";
import { NavLink, Route, Routes, Navigate } from "react-router-dom";
import { clearKey, getKey } from "./api";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Sessions from "./pages/Sessions";
import SessionDetailPage from "./pages/SessionDetail";

export default function App() {
  const [authed, setAuthed] = useState(!!getKey());
  if (!authed) return <Login onDone={() => setAuthed(true)} />;
  const logout = () => { clearKey(); setAuthed(false); };
  return (
    <div className="app">
      <aside className="rail">
        <img className="rail-logo" src="/logo.png" alt="An Hòa – Art Home" />
        <nav>
          <NavLink to="/" end>Tổng quan</NavLink>
          <NavLink to="/sessions">Cuộc hội thoại</NavLink>
        </nav>
        <button className="rail-out" onClick={logout}>Đăng xuất</button>
      </aside>
      <main className="sheet">
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
