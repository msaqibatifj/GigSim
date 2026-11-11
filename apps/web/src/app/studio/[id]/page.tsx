import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, errorText } from "../../../lib/client";
import { fmtUsd, useLoad } from "../../../lib/hooks";
import ApprovalPanel from "../../../components/ApprovalPanel";
import EvidenceHover from "../../../components/EvidenceHover";
import { Badge, Empty, ErrorBox, Loading } from "../../../components/States";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Any = any;

export default function Studio() {
  const { id = "" } = useParams();
  const { data, error, loading, reload } = useLoad(() => api.GET("/api/proposals/{run_id}", { params: { path: { run_id: id } } }), [id],
    (d) => !!d && ["resuming", "running", "queued"].includes(d.run.status), 2000);
  const p: Any = data?.payload ?? {};
  const original: string = p.draft?.cover_letter ?? "";
  const [text, setText] = useState("");
  const [para, setPara] = useState(0);
  const [regen, setRegen] = useState("");
  useEffect(() => { setText(original); }, [original]);

  if (loading && !data) return <Loading rows={5} />;
  if (!data) return <ErrorBox error={error} />;
  if (data.run.status !== "awaiting_approval")
    return (
      <Empty>
        <p>This run is <Badge kind={data.run.status} />.</p>
        {data.run.status === "rejected" && <p>Rejected: {(data.run.summary as Any).rejection_reason}</p>}
        <p><Link to={`/runs/${id}`}>Open the agent run</Link> · <Link to="/pipeline">Pipeline</Link></p>
      </Empty>
    );

  const paras = text.split("\n\n");
  const critiques: Any[] = p.critiques ?? [];
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Proposal studio</h1>
          <p className="muted">Job <Link to={`/jobs/${data.run.ref}`}>{(data.run.summary as Any).job_title ?? data.run.ref}</Link> · bid {fmtUsd(p.price?.amount_usd)} · <Link to={`/runs/${id}`}>agent run</Link></p>
        </div>
      </div>
      <div className="grid grid-2">
        <div className="stack">
          <section className="card stack">
            <div className="spread"><h2>Draft</h2><span className="small muted">{text.split(/\s+/).filter(Boolean).length} words</span></div>
            <label htmlFor="draft" className="sr-only" style={{ position: "absolute", left: -9999 }}>Cover letter</label>
            <textarea id="draft" value={text} onChange={(e) => setText(e.target.value)} data-testid="draft-editor" />
            <div className="row">
              <label htmlFor="para" className="small" style={{ margin: 0 }}>Regenerate paragraph</label>
              <select id="para" style={{ width: "auto" }} value={para} onChange={(e) => setPara(Number(e.target.value))}>
                {paras.map((_, i) => <option key={i} value={i}>{i + 1}</option>)}
              </select>
              <button onClick={async () => {
                setRegen("…");
                const r = await api.POST("/api/proposals/{run_id}/regenerate", { params: { path: { run_id: id } }, body: { text, paragraph: para } });
                if (r.data) { setText(r.data.text); setRegen(""); } else setRegen(errorText(r.error));
              }}>Regenerate</button>
              {regen && <span className="small muted">{regen}</span>}
            </div>
            {Object.keys(p.draft?.screening_answers ?? {}).length > 0 && (
              <div><h3>Screening answers</h3>{Object.entries(p.draft.screening_answers).map(([q, a]) => <p key={q} className="small"><b>{q}</b><br />{String(a)}</p>)}</div>
            )}
          </section>
          <section className="card">
            <h2>Evidence behind each claim <span className="hint">hover or focus an underlined claim</span></h2>
            <EvidenceHover text={text} claims={p.draft?.claims ?? []} evidence={p.evidence ?? []} />
          </section>
        </div>
        <div className="stack">
          <ApprovalPanel runId={id} kind="proposal" original={original} text={text} dryRun={p.dry_run} priceUsd={p.price?.amount_usd} onDone={reload} />
          <section className="card stack" aria-label="Checks">
            <h2>Checks</h2>
            <div>
              <h3>Claim verification</h3>
              <p className="small">Unsupported claims: {p.verification?.unsupported_before ?? "–"} found, removed before the critic; {p.verification?.unsupported_after ?? "–"} remain. {p.verification?.partial ?? 0} partly supported.</p>
            </div>
            <div>
              <h3>Critic ({critiques.length} pass{critiques.length === 1 ? "" : "es"})</h3>
              {critiques.map((c, i) => (
                <p key={i} className="small">{c.ok ? <Badge kind="good">ok</Badge> : <Badge kind="warn">sent back</Badge>} {c.issues?.join("; ")}</p>
              ))}
            </div>
            <div>
              <h3>Compliance Guard</h3>
              <p className="small">{p.compliance?.allowed ? <Badge kind="good">allowed</Badge> : <Badge kind="bad">blocked</Badge>} {p.compliance?.violations?.join("; ") || "no violations"}</p>
            </div>
            <div>
              <h3>Risk</h3>
              <p className="small">Client quality {Math.round((p.risk?.client_score ?? 0) * 100)}% · {p.risk?.flags?.length ? p.risk.flags.join(", ") : "no flags"}</p>
            </div>
            <div><h3>Price rationale</h3><p className="small">{p.price?.rationale}</p></div>
          </section>
        </div>
      </div>
    </>
  );
}
