import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../../../lib/client";
import { useLoad } from "../../../lib/hooks";
import RunTimeline from "../../../components/RunTimeline";
import { Badge, ErrorBox, Loading } from "../../../components/States";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Any = any;

export default function RunPage() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const run = useLoad(() => api.GET("/api/runs/{run_id}", { params: { path: { run_id: id } } }), [id]);
  const hist = useLoad(() => api.GET("/api/runs/{run_id}/history", { params: { path: { run_id: id } } }), [id]);
  if (run.loading && !run.data) return <Loading />;
  if (!run.data) return <ErrorBox error={run.error} />;
  const s: Any = run.data.summary;
  const usage: Record<string, Any> = s.usage ?? {};
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Agent run</h1>
          <p className="muted small">{run.data.kind} · {run.data.ref} · trace id <span className="mono">{run.data.trace_id}</span></p>
        </div>
        <div className="row">
          <Badge kind={run.data.status} />
          {s.trace_url && <a className="btn" href={s.trace_url} target="_blank" rel="noreferrer">Full trace ↗</a>}
          {run.data.status === "awaiting_approval" && <Link className="btn primary" to={run.data.kind === "bid" ? `/studio/${id}` : `/messages?thread=${run.data.ref}`}>Review</Link>}
          {["error", "queued_degraded"].includes(run.data.status) && <button onClick={async () => { await api.POST("/api/runs/{run_id}/retry", { params: { path: { run_id: id } } }); run.reload(); }}>Retry</button>}
        </div>
      </div>
      {s.error && <div className="banner banner-bad">{s.error}</div>}
      <div className="grid grid-2">
        <section className="card"><h2>Progress</h2><RunTimeline runId={id} onEnd={() => run.reload()} /></section>
        <div className="stack">
          <section className="card">
            <h2>Cost and latency</h2>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Node</th><th>Calls</th><th>Tokens</th><th>USD</th><th>s</th></tr></thead>
                <tbody>
                  {Object.entries(usage).map(([n, u]) => (
                    <tr key={n}><td>{n}</td><td>{u.calls}</td><td>{u.prompt_tokens + u.completion_tokens}</td><td>{u.usd.toFixed(5)}</td><td>{u.seconds.toFixed(1)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="small muted">Wall clock {s.seconds ?? "–"} s</p>
          </section>
          <section className="card">
            <h2>Checkpoints</h2>
            <p className="small muted">Replay forks the thread from any earlier step (e.g. to debug a wrong skip).</p>
            <ol className="small">
              {(hist.data ?? []).slice(0, 25).map((h: Any) => (
                <li key={h.checkpoint_id} className="spread">
                  <span>step {h.step} → {h.next.join(", ") || "end"}</span>
                  {h.next.length > 0 && <button className="ghost small" onClick={async () => {
                    const r = await api.POST("/api/runs/{run_id}/replay/{checkpoint_id}", { params: { path: { run_id: id, checkpoint_id: h.checkpoint_id } } });
                    if (r.data) nav(`/runs/${r.data.id}`);
                  }}>Replay</button>}
                </li>
              ))}
            </ol>
          </section>
        </div>
      </div>
    </>
  );
}
