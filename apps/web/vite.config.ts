import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// dev: the API runs on :8000 and is proxied, so cookies stay same-origin (no CORS)
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } } },
});
