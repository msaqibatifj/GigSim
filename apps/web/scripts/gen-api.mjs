// Regenerates src/lib/api/schema.d.ts from FastAPI's OpenAPI schema. Never hand-edit src/lib/api/.
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "../../..");
const py = process.env.PYTHON || "python";
const spec = execFileSync(py, ["-c", "import json; from apps.api.main import app; print(json.dumps(app.openapi()))"], {
  cwd: root, env: { ...process.env, MODEL_PROFILE: "offline" }, maxBuffer: 1 << 26,
});
writeFileSync(resolve(import.meta.dirname, "../openapi.json"), spec);
execFileSync(process.platform === "win32" ? "npx.cmd" : "npx", ["openapi-typescript", "openapi.json", "-o", "src/lib/api/schema.d.ts"], {
  cwd: resolve(import.meta.dirname, ".."), stdio: "inherit", shell: process.platform === "win32",
});
