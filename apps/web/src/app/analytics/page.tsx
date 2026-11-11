import { api } from "../../lib/client";
import { pct, useLoad } from "../../lib/hooks";
import { Empty, ErrorBox, Loading } from "../../components/States";

export default function Analytics() {
  const { data, error, loading } = useLoad(() => api.GET("/api/analytics"), []);
  if (loading && !data) return <Loading />;
  if (!data) return <ErrorBox error={error} />;
  const cats = Object.entries(data.by_category);
  return (
    <>
      <div className="page-head"><div><h1>Analytics</h1><p className="muted">From your runs and GigSim outcomes.</p></div></div>
      <div className="grid grid-3">
        <section className="card"><h3>Connects spent</h3><p style={{ fontSize: "1.6rem", fontWeight: 700 }}>{data.connects_spent}</p>
          <p className="small muted">Outcomes: {Object.entries(data.outcomes).map(([k, v]) => `${v} ${k}`).join(", ") || "none yet"}</p></section>
        <section className="card"><h3>Per proposal</h3><p style={{ fontSize: "1.6rem", fontWeight: 700 }}>{data.per_proposal.latency_p95_s ?? 0}s <span className="small muted">p95</span></p>
          <p className="small muted">${(data.per_proposal.usd_mean ?? 0).toFixed(4)} mean · {Math.round(data.per_proposal.tokens_mean ?? 0)} tokens · n={data.per_proposal.n ?? 0}</p></section>
        <section className="card"><h3>Per job analysed</h3><p style={{ fontSize: "1.6rem", fontWeight: 700 }}>{data.per_job.latency_p95_s ?? 0}s <span className="small muted">p95</span></p>
          <p className="small muted">${(data.per_job.usd_mean ?? 0).toFixed(4)} mean · n={data.per_job.n ?? 0}</p></section>
      </div>
      <div className="grid grid-2" style={{ marginTop: 14 }}>
        <section className="card">
          <h2>Reply and hire rate by category</h2>
          {cats.length === 0 ? <Empty>No submitted proposals yet.</Empty> : (
            <table><thead><tr><th>Category</th><th>Submitted</th><th>Reply rate</th><th>Hire rate</th></tr></thead>
              <tbody>{cats.map(([c, v]) => (
                <tr key={c}><td>{c}</td><td>{v.submitted}</td>
                  <td><div className="row"><div className="bar" style={{ width: `${(v.reply_rate ?? 0) * 100}px` }} />{pct(v.reply_rate)}</div></td>
                  <td>{pct(v.hire_rate)}</td></tr>
              ))}</tbody></table>
          )}
        </section>
        <section className="card">
          <h2>Top rejection reasons</h2>
          {data.rejection_reasons.length ? <ol>{data.rejection_reasons.map(([r, n]) => <li key={r}>{r} <span className="muted">×{n}</span></li>)}</ol> : <p className="muted">None.</p>}
          <h2>Top skip reasons</h2>
          {data.skip_reasons.length ? <ol>{data.skip_reasons.map(([r, n]) => <li key={r}>{r} <span className="muted">×{n}</span></li>)}</ol> : <p className="muted">None.</p>}
        </section>
      </div>
    </>
  );
}
