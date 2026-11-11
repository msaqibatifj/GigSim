import { createContext, useContext, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api, type S } from "./lib/client";
import { useLoad } from "./lib/hooks";
import DegradedBanner from "./components/DegradedBanner";
import Login from "./app/login/page";
import Onboarding from "./app/onboarding/page";
import Inbox from "./app/inbox/page";
import JobPage from "./app/jobs/[id]/page";
import Studio from "./app/studio/[id]/page";
import Pipeline from "./app/pipeline/page";
import Messages from "./app/messages/page";
import RunPage from "./app/runs/[id]/page";
import Analytics from "./app/analytics/page";
import SettingsPage from "./app/settings/page";

type MeCtx = { me: S["Me"]; setMe: (m: S["Me"]) => void };
const Ctx = createContext<MeCtx | null>(null);
export const useMe = () => useContext(Ctx)!;

export default function App() {
  const loc = useLocation();
  const [me, setMe] = useState<S["Me"] | null | undefined>(undefined);
  useEffect(() => {
    api.GET("/api/auth/me").then((r) => setMe(r.data ?? null)).catch(() => setMe(null));
  }, [loc.pathname === "/login"]);

  if (loc.pathname === "/login") return <Login onDone={setMe} />;
  if (me === undefined) return <div className="auth-wrap"><div className="skeleton" style={{ width: 240 }} aria-label="Loading" /></div>;
  if (me === null) return <Navigate to="/login" replace />;
  if (!me.settings.onboarded && loc.pathname !== "/onboarding") return <Navigate to="/onboarding" replace />;
  if (loc.pathname === "/onboarding") return <Ctx.Provider value={{ me, setMe }}><Onboarding /></Ctx.Provider>;

  return (
    <Ctx.Provider value={{ me, setMe }}>
      <Shell>
        <Routes>
          <Route path="/" element={<Navigate to="/inbox" replace />} />
          <Route path="/inbox" element={<Inbox />} />
          <Route path="/jobs/:id" element={<JobPage />} />
          <Route path="/studio/:id" element={<Studio />} />
          <Route path="/pipeline" element={<Pipeline />} />
          <Route path="/messages" element={<Messages />} />
          <Route path="/runs/:id" element={<RunPage />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<div className="empty">Page not found.</div>} />
        </Routes>
      </Shell>
    </Ctx.Provider>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const { me } = useMe();
  const pending = useLoad(() => api.GET("/api/approvals"), [], () => true, 8000);
  const n = pending.data?.length ?? 0;
  const links: [string, string, number?][] = [
    ["/inbox", "Job inbox"], ["/pipeline", "Pipeline", n], ["/messages", "Messages"], ["/analytics", "Analytics"], ["/settings", "Settings"],
  ];
  return (
    <div className="shell">
      <a href="#main" className="skip-link">Skip to content</a>
      <aside className="side">
        <div className="brand"><span className="brand-mark" aria-hidden>✓</span>GigBid</div>
        <nav className="nav" aria-label="Main">
          {links.map(([to, label, badge]) => (
            <NavLink key={to} to={to}>
              {label}
              {badge ? <span className="badge b-warn" aria-label={`${badge} awaiting approval`}>{badge}</span> : null}
            </NavLink>
          ))}
        </nav>
        <div className="side-foot muted">
          <div>{me.email}</div>
          <div>Persona: {me.persona}</div>
          <button className="ghost small" onClick={async () => { await api.POST("/api/auth/logout"); window.location.assign("/login"); }}>Sign out</button>
        </div>
      </aside>
      <main id="main" tabIndex={-1}>
        <DegradedBanner />
        {children}
      </main>
    </div>
  );
}
