import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Relative asset paths so the build works both at / (vite dev) and mounted at /app by the gateway.
  base: "./",
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/v1": "http://127.0.0.1:8080",
      "/net": "http://127.0.0.1:8080",
      "/health": "http://127.0.0.1:8080",
    },
  },
});
