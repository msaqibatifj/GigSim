import { useEffect, useState } from "react";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Any = any;
type Ev = { seq: number; data: Any };

function summary(node: string, u: Any): string {
  if (!u) return "";
  if (u.decision) return `${u.decision.action}: ${(u.decision.reasons ?? []).slice(0, 2).join("; ")}`;
  if (u.fit) return `fit ${Math.round(u.fit.score * 100)}% · ${u.fit.reasons?.[0] ?? ""}`;
  if (u.risk) return `client ${Math.round(u.risk.client_score * 100)}% · flags: ${u.risk.flags?.join(", ") || "none"}`;
  if (u.spec) return `${u.spec.skills?.length ?? 0} skills, ${u.spec.deliverables?.length ?? 0} deliverables`;
  if (u.price) return `$${u.price.amount_usd} · ${u.price.connects} Connects${u.price.worth_connects ? "" : " · not worth it"}`;
  if (u.verification) return `unsupported claims ${u.verification.unsupported_before} → ${u.verification.unsupported_after}`;
  if (u.critiques) return u.critiques[0]?.ok ? "critic: ok" : `critic sent back: ${u.critiques[0]?.issues?.join("; ")}`;
  if (u.compliance)
    return u.compliance.allowed
      ? `compliance ok${u.compliance.violations?.length ? " (" + u.compliance.violations.join(", ") + ")" : ""}`
      : `BLOCKED: ${u.compliance.violations?.join(", ")}`;
  if (u.intent) return `intent: ${u.intent.intent}`;
  if (u.status) return u.status;
  if (u.draft) return `${u.draft.cover_letter?.split(/\s+/).length ?? 0} words`;
  return node;
}

/** Live node-by-node progress streamed over SSE from the worker's LangGraph run. */
export default function RunTimeline({ runId, onEnd }: { runId: string; onEnd?: (status: string) => void }) {
  const [events, setEvents] = useState<Ev[]>([]);
  const [live, setLive] = useState(true);
  useEffect(() => {
    setEvents([]);
    setLive(true);
    const es = new EventSource(`/api/runs/${runId}/stream`);
    const add = (e: MessageEvent) =>
      setEvents((xs) => (xs.some((x) => x.seq === Number(e.lastEventId)) ? xs : [...xs, { seq: Number(e.lastEventId), data: JSON.parse(e.data) }]));
    ["node", "status", "interrupt", "approval"].forEach((k) => es.addEventListener(k, add as EventListener));
    es.addEventListener("end", (e) => {
      setLive(false);
      es.close();
      onEnd?.(JSON.parse((e as MessageEvent).data).status);
    });
    es.onerror = () => setLive(false);
    return () => es.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);
  return (
    <div>
      <p className="small muted" aria-live="polite">{live ? "● Live" : "Stream closed"} · {events.length} events</p>
      <ol className="timeline" data-testid="timeline">
        {events.map((e) => {
          const d = e.data;
          const label =
            d.kind === "node" ? d.node : d.kind === "interrupt" ? "waiting for your approval" : d.kind === "approval" ? `you: ${d.answer?.action}` : `status: ${d.status}`;
          const cls = d.kind === "interrupt" ? "wait" : d.status && /error|dead|attention/.test(d.status) ? "bad" : "";
          return (
            <li key={e.seq}>
              <span className={`dot ${cls}`} aria-hidden />
              <div>
                <strong>{label}</strong> <span className="muted small">{new Date(d.ts * 1000).toLocaleTimeString()}</span>
                <div className="small">{d.kind === "node" ? summary(d.node, d.update) : d.error ?? ""}</div>
                {d.kind === "node" && (
                  <details>
                    <summary className="small muted">state update</summary>
                    <pre>{JSON.stringify(d.update, null, 1)}</pre>
                  </details>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
