import { expect, test } from "vitest";
import { chatgptPrompt, parseAnnotationRecord } from "./json-record.js";

test("parses raw and fenced JSON annotation records", () => {
  expect(parseAnnotationRecord('{"example_id":"golden_v0-001"}')).toEqual({
    example_id: "golden_v0-001",
  });
  expect(parseAnnotationRecord('```json\n{"example_id":"golden_v0-001"}\n```')).toEqual({
    example_id: "golden_v0-001",
  });
  expect(() => parseAnnotationRecord("[]")).toThrow("один об'єкт");
});

test("builds a prompt with the immutable source and schema", () => {
  const prompt = chatgptPrompt(
    { title: "Golden v0 annotation" },
    { example_id: "golden_v0-001", source: { text: "Пост" } },
  );
  expect(prompt).toContain("Golden v0 annotation");
  expect(prompt).toContain('"text": "Пост"');
  expect(prompt).toContain("Не змінюй example_id");
});
