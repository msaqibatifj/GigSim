import { defineConfig } from "@playwright/test";

// The API serves the built app (npm run build) on one port, offline model profile, throwaway databases.
const tmp = process.env.E2E_TMP ?? "../../data/processed/e2e";
export default defineConfig({
  testDir: "tests/e2e",
  timeout: 90_000,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: { baseURL: "http://127.0.0.1:8010", channel: process.env.CI ? undefined : "chrome", trace: "retain-on-failure" },
  webServer: {
    command: "python -m uvicorn apps.api.main:app --port 8010",
    cwd: "../..",
    url: "http://127.0.0.1:8010/api/health",
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      MODEL_PROFILE: "offline", LANGSMITH_TRACING: "false", DATABASE_URL: "", REDIS_URL: "", LOCAL_WORKER_SLOTS: "4", GIGBID_SCOUT_BATCH: "2",
      APP_DATABASE_URL: `sqlite:///${tmp}/app.sqlite`, MEMORY_DB: `${tmp}/memory.sqlite`, CHECKPOINT_DB: `${tmp}/ckpt.sqlite`,
      MOCK_GIGSIM_STATE: `${tmp}/gigsim.json`, AUDIT_LOG: `${tmp}/audit.jsonl`,
    },
  },
});
