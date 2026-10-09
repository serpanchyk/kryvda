import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("nginx serves the React entry point for direct client-side routes", () => {
  const config = readFileSync(new URL("../nginx.conf", import.meta.url), "utf8");

  expect(config).toContain("try_files $uri $uri/ /index.html;");
});

test("nginx re-resolves the API container instead of pinning its startup address", () => {
  const config = readFileSync(new URL("../nginx.conf", import.meta.url), "utf8");

  expect(config).toContain("resolver 127.0.0.11");
  expect(config).toContain("proxy_pass $api_upstream;");
  expect(config).toContain("rewrite ^/api/(.*)$ /$1 break;");
});
