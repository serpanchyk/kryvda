import { defineConfig } from "vite";
import path from "node:path";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  build: {
    rollupOptions: {
      output: {
        // Long-lived vendor chunks cache across deploys; the app chunk stays small.
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          charts: ["recharts"],
          ui: ["@base-ui/react", "lucide-react", "sonner"],
          data: ["@tanstack/react-query"],
        },
      },
    },
  },
  server: {
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000",
        rewrite: (requestPath) => requestPath.replace(/^\/api/, ""),
      },
    },
  },
});
