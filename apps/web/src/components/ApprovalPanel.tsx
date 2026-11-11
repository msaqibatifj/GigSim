import { useState } from "react";
import { api, errorText } from "../lib/client";
import { fmtUsd } from "../lib/hooks";

const sents = (t: string) => t.split(/(?<=[.!?])\s+/).map((s) => s.trim()).filter(Boolean);

/** Sentence-level diff of the user's edit (what style memory learns from). */
export function EditDiff({ before, after }: { before: string; after: string }) {
  const a = new Set(sents(after));
  const b = new Set(sents(before));
  const removed = sents(before).filter((s) => !a.has(s));
  const added = sents(after).filter((s) => !b.has(s));
  if (!removed.length && !added.length) return null;
  return (
    <div className="small" data-testid="edit-diff">
      {removed.map((s, i) => <div key={"r" + i} style={{ color: "var(--bad)", textDecoration: "line-through" }}>− {s}</div>)}
      {added.map((s, i) => <div key={"a" + i} style={{ color: "var(--good)" }}>+ {s}</div>)}
    </div>
  );
}

type Props = {
  runId: string;
  kind: "proposal" | "message";
  original: string;
  text: string;
  dryRun?: { connects_cost?: number; would_send?: Record<string, unknown> } | null;
  priceUsd?: number | null;
  onDone: () => void;
};

/** Approve / edit / reject. Nothing is sent until this resumes the interrupted graph thread. */
export default function ApprovalPanel({ runId, kind, original, text, dryRun, priceUsd, onDone }: Props) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const edited = text.trim() !== original.trim();
  const cost = (dryRun?.would_send as { connects_cost_on_submit?: number } | undefined)?.connects_cost_on_submit ?? dryRun?.connects_cost;
  const send = async (body: { action: "approve" | "edit" | "reject"; text?: string; reason?: string }) => {
    setBusy(true);
    setErr("");
    const r = await api.POST("/api/approvals/{run_id}", { params: { path: { run_id: runId } }, body });
    setBusy(false);
    if (r.error) setErr(errorText(r.error));
    else onDone();
  };
  return (
    <section className="card stack" aria-label="Approval">
      <h2>Approve before anything is sent</h2>
      {kind === "proposal" && (
        <div className="banner banner-info small" data-testid="dry-run">
          <div>
            <strong>Dry run:</strong> creates a marketplace <em>draft</em> bidding {fmtUsd(priceUsd)}; submitting it spends{" "}
            <strong>{cost ?? "?"} Connects</strong>. Final confirmation happens on the marketplace.
          </div>
        </div>
      )}
      {edited && (
        <div>
          <h3>Your edits</h3>
          <EditDiff before={original} after={text} />
          <p className="hint">Edits are re-checked by the Compliance Guard and saved for style memory.</p>
        </div>
      )}
      <div className="row">
        {edited ? (
          <button className="primary" disabled={busy} onClick={() => send({ action: "edit", text })} data-testid="approve-edit">Approve with my edits</button>
        ) : (
          <button className="primary" disabled={busy} onClick={() => send({ action: "approve" })} data-testid="approve">Approve {kind}</button>
        )}
      </div>
      <hr />
      <div className="field">
        <label htmlFor="reject-reason">Reject with a reason</label>
        <input id="reject-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Budget too low for this scope" />
      </div>
      <button className="danger" disabled={busy || !reason.trim()} onClick={() => send({ action: "reject", reason })} data-testid="reject">Reject</button>
      {err && <div className="error-box" role="alert">{err}</div>}
    </section>
  );
}
