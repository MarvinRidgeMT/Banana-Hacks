import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// During `npm run dev`, API calls go to the local backend on :8000.
// On Vercel, set VITE_API_URL to the Cloudflare Tunnel URL instead.
const API = process.env.VITE_DEV_API ?? "http://localhost:8000";
const apiRoutes = ["/health", "/metrics", "/demos", "/restore", "/jobs", "/results"];

// Content-Security-Policy for the built site only (the dev server needs inline scripts).
// Images, API calls and downloads may come from the restoring server (any https host, since the
// tunnel URL changes); scripts only from this site; no plugins, no foreign forms, no <base> tricks.
const CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "font-src 'self' https://fonts.gstatic.com",
  "img-src 'self' data: blob: https:",
  "connect-src 'self' https:",
  "media-src 'self' blob: https:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

const csp = {
  name: "coldcase-csp",
  apply: "build" as const,
  transformIndexHtml(html: string) {
    return html.replace("<head>", `<head>\n    <meta http-equiv="Content-Security-Policy" content="${CSP}" />`);
  },
};

export default defineConfig({
  plugins: [react(), tailwindcss(), csp],
  server: {
    proxy: Object.fromEntries(apiRoutes.map((r) => [r, { target: API, changeOrigin: true }])),
  },
});
