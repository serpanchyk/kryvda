import { expect, test } from "vitest";

import { apiClient } from "./client";

test("builds the default API health URL", () => {
  expect(apiClient.healthUrl()).toBe("http://localhost:8000/health");
});
