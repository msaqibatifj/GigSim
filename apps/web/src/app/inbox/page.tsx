import { useState } from "react";
import { Link } from "react-router-dom";
import { useMe } from "../../App";
import { api } from "../../lib/client";
import { fmtUsd, useLoad } from "../../lib/hooks";
import { Badge, Empty, ErrorBox, Loading, Meter } from "../../components/States";

const BUSY = new Set(["queued", "running", "resuming", "queued_degraded"]);

export default function Inbox() {
  const { me } = useMe();
  const [filter, setFilter] = useState("all");
  const { data, error, loading, reload } = useLoad(() => api.GET("/api/jobs"), [], (d) => !d || d.length === 0 || d.some((i) => BUSY.has(i.status)), 3000);
  const autoSkip = me.settings.autonomy === "auto_skip_low_fit";
  const items = (data ?? []).filter((i) => (filter === "all" ? !(autoSkip && i.action === "skip") : i.action === filter));

  return (
    <>
      <div className="page-head">
        <div><h1>Job inbox</h1><p className="muted">Ranked by recommendation and fit. Scouted on your saved searches every {me.settings.scout_every_hours}h.</p></div>
        <div className="row">
          <label htmlFor="filter" className="small" style={{ margin: 0 }}>Show</label>
          <select id="filter" value={filter} onChange={(e) => setFilter(e.target.value)} style={{ width: "auto" }}>
            <option value="all">All</option><option value="bid">Bid</option><option value="watch">Watch</option><option value="skip">Skip</option>
          </select>
          <button onClick={async () => { await api.POST("/api/jobs/scout"); setTimeout(reload, 1500); }}>Scout now</button>
        </div>
      </div>
      <ErrorBox error={error} />
      {loading && !data ? <Loading /> : items.length === 0 ? (
        <Empty>No jobs yet. GigBid is scouting your saved searches; new jobs appear here as they are analysed.</Empty>
      ) : (
        <div className="card" style={{ padding: 0 }} data-testid="inbox">
          {items.map((i) => (
            <div className="job-row" key={i.job.id} data-testid="inbox-row">
              <div>
                <Link className="job-title" to={`/jobs/${i.job.id}`}>{i.job.title}</Link>
                <div className="job-meta">
                  {BUSY.has(i.status) ? <Badge kind="running">analysing…</Badge> : i.action ? <Badge kind={i.action}>{i.action}</Badge> : <Badge kind={i.status} />}
                  {i.risk_flags.map((f) => <Badge key={f} kind="bad">⚠ {f.replace("_", " ")}</Badge>)}
                  <Meter value={i.fit} label="Fit" />
                  <span>budget {fmtUsd(i.job.budget_usd)}</span>
                  {i.price_usd ? <span>bid {fmtUsd(i.price_usd)}</span> : null}
                  <span>{i.connects ?? i.job.connects_cost ?? "?"} Connects</span>
                  {i.job.source !== "synthetic" && <span className="badge" title={i.job.source}>real posting</span>}
                </div>
                {i.reasons[0] && <div className="small muted" style={{ marginTop: 4 }}>{i.reasons[0]}</div>}
              </div>
              <div className="row">
                {i.status === "awaiting_approval" && <Link className="btn primary" to={`/studio/${i.run_id}`}>Review proposal</Link>}
                {["error", "dead_letter", "new"].includes(i.status) && <button onClick={async () => { await api.POST("/api/jobs/{job_id}/analyse", { params: { path: { job_id: i.job.id } } }); reload(); }}>Analyse</button>}
                {i.action !== "skip" && i.status !== "submitted" && i.status !== "skipped_by_user" && (
                  <button className="ghost" onClick={async () => { await api.POST("/api/jobs/{job_id}/skip", { params: { path: { job_id: i.job.id } } }); reload(); }}>Skip</button>
                )}
                <Link className="btn" to={`/jobs/${i.job.id}`}>Open</Link>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
