import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, errorText, type S } from "../../lib/client";
import { useLoad } from "../../lib/hooks";

export default function Login({ onDone }: { onDone: (m: S["Me"]) => void }) {
  const nav = useNavigate();
  const [mode, setMode] = useState<"in" | "up">("in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [persona, setPersona] = useState("ayesha_ml");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const personas = useLoad(() => api.GET("/api/auth/personas"), []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setErr("");
    const r = mode === "in"
      ? await api.POST("/api/auth/login", { body: { email, password } })
      : await api.POST("/api/auth/signup", { body: { email, password, persona } });
    setBusy(false);
    if (r.error || !r.data) return setErr(errorText(r.error));
    onDone(r.data);
    nav(r.data.settings.onboarded ? "/inbox" : "/onboarding");
  };

  return (
    <div className="auth-wrap">
      <form className="card auth-card stack" onSubmit={submit} aria-label={mode === "in" ? "Sign in" : "Create account"}>
        <div className="brand"><span className="brand-mark" aria-hidden>✓</span>GigBid</div>
        <p className="muted">Finds freelance jobs, checks them for risk and fit, and drafts proposals backed by your own portfolio. Nothing is sent without your approval.</p>
        <div className="field"><label htmlFor="email">Email</label><input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></div>
        <div className="field"><label htmlFor="pw">Password</label><input id="pw" type="password" minLength={mode === "up" ? 8 : 1} autoComplete={mode === "in" ? "current-password" : "new-password"} required value={password} onChange={(e) => setPassword(e.target.value)} /></div>
        {mode === "up" && (
          <div className="field">
            <label htmlFor="persona">Start from a persona <span className="hint">(synthetic portfolio; upload your own later)</span></label>
            <select id="persona" value={persona} onChange={(e) => setPersona(e.target.value)}>
              {personas.data?.map((p) => <option key={p.id} value={p.id}>{p.name}: {p.title}</option>)}
            </select>
          </div>
        )}
        {err && <div className="error-box" role="alert">{err}</div>}
        <button className="primary" disabled={busy} type="submit">{mode === "in" ? "Sign in" : "Create account"}</button>
        <button type="button" className="ghost" onClick={() => setMode(mode === "in" ? "up" : "in")}>
          {mode === "in" ? "New here? Create an account" : "Have an account? Sign in"}
        </button>
      </form>
    </div>
  );
}
