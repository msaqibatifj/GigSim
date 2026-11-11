import { errorText } from "../lib/client";

export const Loading = ({ rows = 3 }: { rows?: number }) => (
  <div aria-busy="true" aria-label="Loading">{Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton" />)}</div>
);
export const Empty = ({ children }: { children: React.ReactNode }) => <div className="empty card">{children}</div>;
export const ErrorBox = ({ error }: { error: unknown }) => (error ? <div className="error-box" role="alert">{errorText(error)}</div> : null);
export const Badge = ({ kind, children }: { kind?: string | null; children?: React.ReactNode }) => (
  <span className={`badge b-${kind ?? "info"}`}>{children ?? kind?.replace(/_/g, " ")}</span>
);
export const Meter = ({ value, label }: { value?: number | null; label: string }) => (
  <span className="row" title={label}>
    <span className="meter" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round((value ?? 0) * 100)} aria-label={label}>
      <span style={{ width: `${Math.round((value ?? 0) * 100)}%` }} />
    </span>
    <span className="small">{value == null ? "–" : `${Math.round(value * 100)}%`}</span>
  </span>
);
