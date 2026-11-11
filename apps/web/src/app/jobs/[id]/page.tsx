import { Link, useParams } from "react-router-dom";
import { api } from "../../../lib/client";
import { fmtUsd, pct, useLoad } from "../../../lib/hooks";
import { Badge, ErrorBox, Loading, Meter } from "../../../components/States";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Any = any;
const BUSY = new Set(["queued", "running", "resuming"]);

export default function JobPage() {
  const { id = "" } = useParams();
  const { data, error, loading, reload } = useLoad(() => api.GET("/api/jobs/{job_id}", { params: { path: { job_id: id } } }), [id],
    (d) => !!d?.run && BUSY.has(d.run.status), 3000);
  if (loading && !data) return <Loading rows={4} />;
  if (!data) return <ErrorBox error={error} />;
  const st: Any = data.state, run = data.run;
  const spec = st.spec, risk = st.risk, fit = st.fit, price = st.price, decision = st.decision;
  const evidence: Any[] = st.evidence ?? [];
  return (
    <>
      <div className="page-head">
        <div>
          <h1>{data.job.title}</h1>
          <div className="row small muted">
            <span>Budget {fmtUsd(data.job.budget_usd)}</span>
            <span>{data.job.connects_cost ?? "policy"} Connects</span>
            <span title={data.job.source}>{data.job.source === "synthetic" ? "synthetic job" : "real Kaggle posting"}</span>
            {run && <Badge kind={run.status} />}
          </div>
        </div>
        <div className="row">
          {run?.status === "awaiting_approval" && <Link className="btn primary" to={`/studio/${run.id}`}>Review proposal</Link>}
          {run && <Link className="btn" to={`/runs/${run.id}`}>Agent run</Link>}
          {!run || ["error", "dead_letter", "skipped_by_user"].includes(run.status) ? (
            <button className="primary" onClick={async () => { await api.POST("/api/jobs/{job_id}/analyse", { params: { path: { job_id: id } } }); reload(); }}>Analyse</button>
          ) : null}
        </div>
      </div>
      <div className="grid grid-2">
        <section className="card">
          <h2>Job post <span className="hint">untrusted client text</span></h2>
          <p style={{ whiteSpace: "pre-wrap" }}>{data.job.description}</p>
        </section>
        <section className="card">
          <h2>Recommendation</h2>
          {decision ? (
            <>
              <p><Badge kind={decision.action}>{decision.action.toUpperCase()}</Badge></p>
              <ul className="small">{decision.reasons.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>
            </>
          ) : <p className="muted">{run && BUSY.has(run.status) ? "Analysing…" : "Not analysed yet."}</p>}
          {price && (
            <>
              <h3>Price</h3>
              <p><b>{fmtUsd(price.amount_usd)}</b> · {price.connects} Connects {price.worth_connects ? "" : <Badge kind="bad">not worth the Connects</Badge>}</p>
              <p className="small muted">{price.rationale}</p>
            </>
          )}
        </section>
        <section className="card">
          <h2>Risk report</h2>
          {risk ? (
            <>
              <div className="row"><span>Client quality</span><Meter value={risk.client_score} label="Client quality" /></div>
              <div className="row" style={{ margin: "8px 0" }}>{risk.flags.length ? risk.flags.map((f: string) => <Badge key={f} kind="bad">⚠ {f}</Badge>) : <Badge kind="good">no flags</Badge>}</div>
              <ul className="small">{risk.reasons.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>
            </>
          ) : <p className="muted">–</p>}
          {data.client && <p className="small muted">Client: spent {fmtUsd((data.client as Any).total_spent_usd)}, hire rate {pct((data.client as Any).hire_rate)}, payment {(data.client as Any).payment_verified ? "verified" : "unverified"}</p>}
        </section>
        <section className="card">
          <h2>JobSpec</h2>
          {spec ? (
            <div className="small">
              <p><b>Deliverables:</b> {spec.deliverables.join("; ") || "–"}</p>
              <p><b>Skills:</b> {spec.skills.join(", ") || "–"}</p>
              <p><b>Timeline:</b> {spec.timeline_days ? `${spec.timeline_days} days` : "–"}</p>
              <p><b>Screening questions:</b> {spec.screening_questions.join(" / ") || "none"}</p>
              <p><b>Hidden needs:</b> {spec.hidden_needs.join("; ") || "–"}</p>
            </div>
          ) : <p className="muted">–</p>}
        </section>
      </div>
      <section className="card" style={{ marginTop: 14 }}>
        <div className="spread"><h2>Requirement → evidence</h2>{fit && <Meter value={fit.score} label="Fit score" />}</div>
        {fit ? (
          <div className="table-wrap">
            <table data-testid="evidence-matrix">
              <thead><tr><th>Requirement</th><th>Portfolio evidence</th></tr></thead>
              <tbody>
                {fit.evidence.map((e: Any, i: number) => {
                  const it = evidence.find((x) => x.id === e.item_id);
                  return (
                    <tr key={i}>
                      <td>{e.requirement}</td>
                      <td>{e.item_id ? <><span className="mono">{e.item_id}</span> {it?.title}{it?.outcome && <> <Badge kind="info">{it.outcome}</Badge></>}</> : <Badge kind="bad">no evidence — will not be claimed</Badge>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : <p className="muted">–</p>}
      </section>
    </>
  );
}
