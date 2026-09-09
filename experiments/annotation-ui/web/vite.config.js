import { defineConfig } from "vite";
export default defineConfig({
  test: { environment: "jsdom", include: ["src/editor.test.jsx"] },
});
