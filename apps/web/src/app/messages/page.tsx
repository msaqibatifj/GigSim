import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../../lib/client";
import { useLoad } from "../../lib/hooks";
import ApprovalPanel from "../../components/ApprovalPanel";
import { Badge, Empty, ErrorBox, Loading } from "../../components/States";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Any = any;

export default function Messages() {
  const [params, setParams] = useSearchParams();
  const threads = useLoad(() => api.GET("/api/messages"), [], () => true, 8000);
  const sel = params.get("thread") ?? threads.data?.[0]?.thread_id ?? "";
  const t = useLoad(() => (sel ? api.GET("/api/messages/{thread_id}", { params: { path: { thread_id: sel } } }) : Promise.resolve({ data: undefined, response: new Response() })), [sel],
    (d) => !!d?.run && ["queued", "running", "resuming"].includes(d.run.status), 2000);
  const run = t.data?.run;
  const payload: Any = (run?.summary as Any)?.approval;
  const [text, setText] = useState("");
  useEffect(() => { setText(payload?.reply?.text ?? ""); }, [payload?.reply?.text]);

  return (
    <>
      <div className="page-head"><div><h1>Messages</h1><p className="muted">Client messages are untrusted. Suggested replies need your approval before sending.</p></div></div>
      <ErrorBox error={threads.error} />
      {threads.loading && !threads.data ? <Loading /> : !threads.data?.length ? <Empty>No client threads yet.</Empty> : (
        <div className="grid" style={{ gridTemplateColumns: "minmax(200px, 280px) 1fr" }}>
          <nav className="thread-list" aria-label="Threads">
            {threads.data.map((x) => (
              <button key={x.thread_id} aria-current={x.thread_id === sel} onClick={() => setParams({ thread: x.thread_id })}>
                <b>{x.thread_id}</b>
                <span className="small muted">{x.last?.text.slice(0, 70)}</span>
                {x.run && <Badge kind={x.run.status} />}
              </button>
            ))}
          </nav>
          <div className="stack">
            <section className="card">
              <div className="msgs" data-testid="thread">
                {t.data?.messages.map((m) => <div key={m.id} className={`msg ${m.sender === "freelancer" ? "me" : ""}`}><span className="small muted">{m.sender}</span><br />{m.text}</div>)}
              </div>
              <div className="row" style={{ marginTop: 12 }}>
                <button className="primary" onClick={async () => { await api.POST("/api/messages/{thread_id}/draft", { params: { path: { thread_id: sel } } }); t.reload(); }}
                  disabled={!!run && ["queued", "running", "awaiting_approval", "resuming"].includes(run.status)}>Suggest a reply</button>
                {run && <Badge kind={run.status} />}
              </div>
            </section>
            {run?.status === "needs_attention" && <div className="banner banner-bad">Flagged as a possible scam or off-platform request; no reply drafted.</div>}
            {run?.status === "awaiting_approval" && payload && (
              <>
                <section className="card stack">
                  <h2>Suggested reply <Badge kind="info">{payload.intent?.intent?.replace("_", " ")}</Badge></h2>
                  <label htmlFor="reply" style={{ position: "absolute", left: -9999 }}>Reply</label>
                  <textarea id="reply" value={text} onChange={(e) => setText(e.target.value)} style={{ minHeight: 120 }} />
                  {payload.reply?.slots?.length > 0 && <p className="small">Interview slots offered: {payload.reply.slots.map((s: string) => new Date(s).toLocaleString()).join(" · ")}</p>}
                </section>
                <ApprovalPanel runId={run.id} kind="message" original={payload.reply?.text ?? ""} text={text} onDone={t.reload} />
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}
