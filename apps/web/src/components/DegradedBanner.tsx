import { api } from "../lib/client";
import { useLoad } from "../lib/hooks";

/** Polls /api/health; when the marketplace MCP server is down, work is queued and resumes on recovery. */
export default function DegradedBanner() {
  const { data, error } = useLoad(() => api.GET("/api/health"), [], () => true, 10000);
  if (error) return <div className="banner banner-bad" role="alert" data-testid="degraded-banner">GigBid API unreachable. Retrying…</div>;
  if (data?.marketplace === "down")
    return (
      <div className="banner banner-bad" role="alert" data-testid="degraded-banner">
        <strong>Marketplace unavailable.</strong> New analyses and approved sends are queued and will resume automatically when it is back.
      </div>
    );
  return null;
}
