// Thin wrapper over the generated client (src/lib/api/schema.d.ts is generated: `npm run gen:api`).
import createClient, { type Middleware } from "openapi-fetch";
import type { components, paths } from "./api/schema";

export type S = components["schemas"];

const trace: Middleware = {
  async onRequest({ request }) {
    // one trace id per UI action flows API -> graph -> MCP servers -> audit log
    request.headers.set("x-trace-id", crypto.randomUUID().replace(/-/g, "").slice(0, 16));
    return request;
  },
};

export const api = createClient<paths>({ baseUrl: "", credentials: "include" });
api.use(trace);

export function errorText(e: unknown): string {
  if (!e) return "";
  if (typeof e === "string") return e;
  const d = (e as { detail?: unknown }).detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => (x as { msg?: string }).msg ?? "").join("; ");
  return "Something went wrong.";
}
