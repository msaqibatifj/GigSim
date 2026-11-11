import { Link } from "react-router-dom";
import { api } from "../../lib/client";
import { fmtUsd, useLoad } from "../../lib/hooks";
import { Empty, ErrorBox, Loading } from "../../components/States";

const COLS = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"] as const;

export default function Pipeline() {
  const { data, error, loading } = useLoad(() => api.GET("/api/pipeline"), [], () => true, 5000);
  return (
    <>
      <div className="page-head"><div><h1>Pipeline</h1><p className="muted">Cards move as the marketplace reports views, replies and hires.</p></div></div>
      <ErrorBox error={error} />
      {loading && !data ? <Loading /> : !data?.length ? <Empty>No proposals yet. Approve one from the inbox to start your pipeline.</Empty> : (
        <div className="board" data-testid="board">
          {COLS.map((c) => {
            const cards = data.filter((x) => x.stage === c);
            return (
              <section className="col" key={c} aria-label={c}>
                <h3><span>{c}</span><span>{cards.length}</span></h3>
                {cards.map((k) => (
                  <div className="kcard" key={k.run_id} data-testid={`card-${c}`}>
                    <Link to={k.stage === "drafted" ? `/studio/${k.run_id}` : `/jobs/${k.job_id}`}>{k.title}</Link>
                    <div className="small muted">{fmtUsd(k.price_usd)}</div>
                    {k.thread_id && <Link className="small" to={`/messages?thread=${k.thread_id}`}>Open thread</Link>}
                  </div>
                ))}
              </section>
            );
          })}
        </div>
      )}
    </>
  );
}
