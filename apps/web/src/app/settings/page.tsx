import { useState } from "react";
import { useMe } from "../../App";
import { api, errorText } from "../../lib/client";
import { useLoad } from "../../lib/hooks";
import { Badge, ErrorBox } from "../../components/States";

export default function SettingsPage() {
  const { me, setMe } = useMe();
  const [s, setS] = useState(me.settings);
  const [msg, setMsg] = useState("");
  const mem = useLoad(() => api.GET("/api/memory"), []);
  const save = async () => {
    const r = await api.PUT("/api/auth/settings", { body: s });
    if (r.data) { setMe(r.data); setMsg("Saved."); } else setMsg(errorText(r.error));
  };
  return (
    <>
      <div className="page-head"><div><h1>Settings</h1></div></div>
      <div className="grid grid-2">
        <section className="card">
          <h2>Autonomy and budgets</h2>
          <div className="field">
            <label htmlFor="autonomy">Autonomy</label>
            <select id="autonomy" value={s.autonomy} onChange={(e) => setS({ ...s, autonomy: e.target.value as typeof s.autonomy })}>
              <option value="ask_always">Show every job, I decide</option>
              <option value="auto_skip_low_fit">Hide low-fit skips automatically</option>
            </select>
            <p className="hint">GigBid never sends a proposal or message without your approval, at any setting.</p>
          </div>
          <div className="grid grid-2">
            <div className="field"><label htmlFor="sr">Hourly rate</label><input id="sr" type="number" value={s.rate ?? ""} onChange={(e) => setS({ ...s, rate: Number(e.target.value) || null })} /></div>
            <div className="field"><label htmlFor="sf">Floor rate</label><input id="sf" type="number" value={s.floor ?? ""} onChange={(e) => setS({ ...s, floor: Number(e.target.value) || null })} /></div>
            <div className="field"><label htmlFor="sc">Weekly Connects budget</label><input id="sc" type="number" value={s.connects_budget_weekly} onChange={(e) => setS({ ...s, connects_budget_weekly: Number(e.target.value) })} /></div>
            <div className="field"><label htmlFor="se">Scout every (hours)</label><input id="se" type="number" min={1} value={s.scout_every_hours} onChange={(e) => setS({ ...s, scout_every_hours: Number(e.target.value) })} /></div>
          </div>
          <h3>Saved searches</h3>
          {s.saved_searches.map((q, i) => (
            <div className="row" key={i} style={{ marginBottom: 6 }}>
              <input aria-label={`Search ${i + 1} keywords`} value={q.query} onChange={(e) => setS({ ...s, saved_searches: s.saved_searches.map((x, j) => (j === i ? { ...x, query: e.target.value } : x)) })} style={{ flex: 1, width: "auto" }} />
              <select aria-label={`Search ${i + 1} category`} value={q.category ?? ""} style={{ width: "auto" }} onChange={(e) => setS({ ...s, saved_searches: s.saved_searches.map((x, j) => (j === i ? { ...x, category: (e.target.value || null) as typeof x.category } : x)) })}>
                <option value="">any</option><option value="ml_nlp">ML/NLP</option><option value="web">Web</option><option value="data">Data</option>
              </select>
              <button className="ghost" onClick={() => setS({ ...s, saved_searches: s.saved_searches.filter((_, j) => j !== i) })} aria-label="Remove search">✕</button>
            </div>
          ))}
          <button className="ghost" onClick={() => setS({ ...s, saved_searches: [...s.saved_searches, { query: "", category: null }] })}>+ Add search</button>
          <hr />
          <div className="row"><button className="primary" onClick={save}>Save settings</button><span className="small muted" role="status">{msg}</span></div>
        </section>
        <div className="stack">
          <section className="card">
            <h2>Connected accounts</h2>
            <p>GigSim {s.marketplace === "gigsim" ? <Badge kind="good">connected</Badge> : <Badge kind="info">not connected</Badge>}</p>
            <p>Upwork {me.upwork_connected ? <Badge kind="good">connected</Badge> : <Badge kind="info">not connected</Badge>}</p>
          </section>
          <section className="card">
            <h2>Memory</h2>
            <p className="small muted">Learned only through explicit promotion rules: a style pattern needs 2 separate edits; outcome stats need 3 outcomes per category. Delete anything you disagree with.</p>
            <ErrorBox error={mem.error} />
            {!mem.data?.length ? <p className="muted">Nothing learned yet.</p> : (
              <ul style={{ paddingLeft: 0, listStyle: "none" }} data-testid="memory">
                {mem.data.map((m) => (
                  <li key={m.kind + m.key} className="spread" style={{ padding: "6px 0", borderBottom: "1px solid var(--line)" }}>
                    <span><Badge kind="info">{m.kind}</Badge> {String((m.value as Record<string, unknown>).rule ?? `${m.key}: reply rate ${(m.value as Record<string, unknown>).rate}`)}</span>
                    <button className="ghost danger" onClick={async () => { await api.DELETE("/api/memory/{kind}/{key}", { params: { path: { kind: m.kind, key: m.key } } }); mem.reload(); }}>Delete</button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </>
  );
}
