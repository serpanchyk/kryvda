import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("nginx serves the React entry point for direct client-side routes", () => {
  const config = readFileSync(new URL("../nginx.conf", import.meta.url), "utf8");

  expect(config).toContain("try_files $uri $uri/ /index.html;");
});
