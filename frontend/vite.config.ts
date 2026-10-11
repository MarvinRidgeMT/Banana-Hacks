import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// During `npm run dev`, API calls go to the local backend on :8000.
// On Vercel, set VITE_API_URL to the Cloudflare Tunnel URL instead.
const API = process.env.VITE_DEV_API ?? "http://localhost:8000";
const apiRoutes = ["/health", "/metrics", "/demos", "/restore", "/jobs", "/results"];

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: Object.fromEntries(apiRoutes.map((r) => [r, { target: API, changeOrigin: true }])),
  },
});
