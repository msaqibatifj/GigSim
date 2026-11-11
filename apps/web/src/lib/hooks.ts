import { useCallback, useEffect, useRef, useState } from "react";

type Res<T> = { data?: T; error?: unknown; response: Response };

/** Load data; optionally poll while `poll(data)` returns true. Keeps the last good data on errors. */
export function useLoad<T>(fn: () => Promise<Res<T>>, deps: unknown[], poll?: (d: T | undefined) => boolean, everyMs = 3000) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<unknown>();
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const reload = useCallback(async () => {
    try {
      const r = await fnRef.current();
      if (r.response.status === 401) { window.location.assign("/login"); return; }
      if (r.error !== undefined) setError(r.error); else { setData(r.data); setError(undefined); }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { setLoading(true); reload(); }, deps);
  useEffect(() => {
    if (!poll || !poll(data)) return;
    const t = setInterval(reload, everyMs);
    return () => clearInterval(t);
  }, [data, poll, reload, everyMs]);
  return { data, error, loading, reload, setData };
}

export const fmtUsd = (n?: number | null) => (n == null ? "–" : `$${Math.round(n).toLocaleString()}`);
export const pct = (n?: number | null) => (n == null ? "–" : `${Math.round(n * 100)}%`);
