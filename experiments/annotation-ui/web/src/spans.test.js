import test from "node:test";
import assert from "node:assert/strict";
import { codePointSpan, spanText } from "./spans.js";
test("emoji and Ukrainian text use code points, preserving newlines", () => {
  const text = "😀\nЦПК";
  const span = codePointSpan(text, 3, 6);
  assert.deepEqual(span, { start: 2, end: 5 });
  assert.equal(spanText(text, span), "ЦПК");
});
