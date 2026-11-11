import { useId } from "react";

type Claim = { text: string; label: string; evidence_ids?: string[] };
type Ev = { id: string; title?: string; text?: string; type?: string; outcome?: string | null };

/** Renders the draft with every verified claim underlined; hover or focus a claim to see the portfolio evidence behind it. */
export default function EvidenceHover({ text, claims, evidence }: { text: string; claims: Claim[]; evidence: Ev[] }) {
  const byId = Object.fromEntries(evidence.map((e) => [e.id, e]));
  const marks: { start: number; end: number; c: Claim }[] = [];
  for (const c of claims) {
    const t = c.text.trim();
    if (t.length < 8 || !c.evidence_ids?.length) continue;
    const i = text.indexOf(t);
    if (i >= 0 && !marks.some((m) => i < m.end && i + t.length > m.start)) marks.push({ start: i, end: i + t.length, c });
  }
  marks.sort((a, b) => a.start - b.start);
  const out: React.ReactNode[] = [];
  let at = 0;
  marks.forEach((m, k) => {
    out.push(text.slice(at, m.start));
    out.push(<ClaimSpan key={k} claim={m.c} text={text.slice(m.start, m.end)} ev={(m.c.evidence_ids ?? []).map((id) => byId[id] ?? { id })} />);
    at = m.end;
  });
  out.push(text.slice(at));
  return <div className="letter" data-testid="evidence-preview">{out}</div>;
}

function ClaimSpan({ claim, text, ev }: { claim: Claim; text: string; ev: Ev[] }) {
  const id = useId();
  return (
    <span className={`claim ${claim.label}`} tabIndex={0} aria-describedby={id} data-testid="claim">
      {text}
      <span className="tip" role="tooltip" id={id}>
        <strong>{claim.label === "partial" ? "Partly supported by" : "Supported by"}</strong>
        {ev.map((e) => (
          <span key={e.id} style={{ display: "block", marginTop: 6 }}>
            <span className="mono">{e.id}</span> {e.title ? <b>{e.title}</b> : null}
            {e.outcome ? <span className="badge b-info" style={{ marginLeft: 4 }}>{e.outcome}</span> : null}
            {e.text ? <span className="muted" style={{ display: "block" }}>{e.text.replace(/^#.*\n+/, "").slice(0, 220)}…</span> : null}
          </span>
        ))}
      </span>
    </span>
  );
}
