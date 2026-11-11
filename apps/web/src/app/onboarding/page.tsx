import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMe } from "../../App";
import { api, errorText } from "../../lib/client";
import { useLoad } from "../../lib/hooks";

const STEPS = ["Persona", "Marketplace", "Portfolio", "Rates & budget"];

export default function Onboarding() {
  const { me, setMe } = useMe();
  const nav = useNavigate();
  const [step, setStep] = useState(0);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [s, setS] = useState(me.settings);
  const [query, setQuery] = useState("");
  const personas = useLoad(() => api.GET("/api/auth/personas"), []);
  const cat = personas.data?.find((p) => p.id === me.persona)?.category;

  const run = async (fn: () => Promise<{ data?: typeof me; error?: unknown }>, next = true) => {
    setBusy(true); setErr("");
    const r = await fn();
    setBusy(false);
    if (r.error || !r.data) return setErr(errorText(r.error));
    setMe(r.data); setS(r.data.settings);
    if (next) setStep((x) => x + 1);
  };

  const finish = async () => {
    const body = { ...s, onboarded: true, saved_searches: [{ query, category: (cat as "ml_nlp" | "web" | "data") ?? null }] };
    await run(() => api.PUT("/api/auth/settings", { body }), false);
    await api.POST("/api/jobs/scout");
    nav("/inbox");
  };

  return (
    <div className="auth-wrap">
      <div className="card auth-card stack" style={{ width: "min(560px,100%)" }}>
        <h1>Set up GigBid</h1>
        <div className="steps" aria-label="Progress">{STEPS.map((x, i) => <span key={x} className={i === step ? "on" : ""} aria-current={i === step ? "step" : undefined}>{i + 1}. {x}</span>)}</div>
        {step === 0 && (
          <div className="stack">
            <p>Pick the portfolio GigBid writes from. You can switch or upload your own work at any time.</p>
            {personas.data?.map((p) => (
              <label key={p.id} className="card row" style={{ cursor: "pointer", fontWeight: 400 }}>
                <input type="radio" name="persona" style={{ width: "auto" }} checked={me.persona === p.id} onChange={() => run(() => api.PUT("/api/auth/persona/{persona}", { params: { path: { persona: p.id } } }), false)} />
                <span><b>{p.name}</b>: {p.title}<br /><span className="small muted">{p.skills.join(", ")}</span></span>
              </label>
            ))}
            <button className="primary" onClick={() => setStep(1)}>Continue</button>
          </div>
        )}
        {step === 1 && (
          <div className="stack">
            <p>Connect a marketplace. GigSim is the simulator; Upwork uses its official MCP server with OAuth (drafts only, you confirm on Upwork).</p>
            <button className="primary" disabled={busy} onClick={() => run(() => api.POST("/api/auth/connect/gigsim"))} data-testid="connect-gigsim">Connect GigSim</button>
            <button disabled={busy} onClick={async () => { const r = await api.GET("/api/auth/upwork/start"); if (r.data) window.location.assign((r.data as { url: string }).url); else setErr(errorText(r.error)); }}>Connect Upwork (OAuth)</button>
          </div>
        )}
        {step === 2 && (
          <div className="stack">
            <p>Optional: add a case study (.md / .txt) or a CV (.pdf). Every claim in a proposal must link to something here.</p>
            <input type="file" aria-label="Portfolio file" accept=".md,.txt,.pdf" onChange={async (e) => {
              const f = e.target.files?.[0]; if (!f) return;
              const fd = new FormData(); fd.append("file", f);
              setBusy(true);
              const r = await fetch("/api/auth/portfolio", { method: "POST", body: fd, credentials: "include" });
              setBusy(false);
              if (r.ok) setMe(await r.json()); else setErr((await r.json()).detail ?? "Upload failed");
            }} />
            <button className="primary" onClick={() => setStep(3)}>{busy ? "Uploading…" : "Continue"}</button>
          </div>
        )}
        {step === 3 && (
          <div className="stack">
            <div className="grid grid-2">
              <div className="field"><label htmlFor="rate">Hourly rate (USD)</label><input id="rate" type="number" min={1} value={s.rate ?? ""} onChange={(e) => setS({ ...s, rate: Number(e.target.value) || null })} /></div>
              <div className="field"><label htmlFor="floor">Floor rate (USD/h) <span className="hint">never bid below</span></label><input id="floor" type="number" min={1} value={s.floor ?? ""} onChange={(e) => setS({ ...s, floor: Number(e.target.value) || null })} /></div>
              <div className="field"><label htmlFor="connects">Weekly Connects budget</label><input id="connects" type="number" min={0} value={s.connects_budget_weekly ?? 60} onChange={(e) => setS({ ...s, connects_budget_weekly: Number(e.target.value) })} /></div>
              <div className="field"><label htmlFor="q">Saved search keywords <span className="hint">optional</span></label><input id="q" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. dashboard" /></div>
            </div>
            <button className="primary" disabled={busy} onClick={finish} data-testid="finish-onboarding">Finish and scout jobs</button>
          </div>
        )}
        {err && <div className="error-box" role="alert">{err}</div>}
      </div>
    </div>
  );
}
