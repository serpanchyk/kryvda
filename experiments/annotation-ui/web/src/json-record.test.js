import { expect, test } from "vitest";
import {
  chatgptPrompt,
  mutablePayload,
  parseAnnotationPayload,
} from "./json-record.js";

test("parses raw and fenced mutable JSON", () => {
  expect(parseAnnotationPayload('{"selection":{}}')).toEqual({
    selection: {},
  });
  expect(parseAnnotationPayload('```json\n{"selection":{}}\n```')).toEqual({
    selection: {},
  });
  expect(() => parseAnnotationPayload("[]")).toThrow("один об'єкт");
});

test("builds a prompt with source separate from the mutable payload", () => {
  const prompt = chatgptPrompt(
    { title: "Golden v0 annotation" },
    { text: "Пост" },
    { selection: {}, annotations: {} },
  );
  expect(prompt).toContain("Golden v0 annotation");
  expect(prompt).toContain('"text": "Пост"');
  expect(prompt).toContain("лише selection та annotations");
  expect(prompt).toContain("неповнолітніх, жертв, свідків");
  expect(prompt).toContain("external_unnamed");
});

test("removes registry fields before confirming an imported preview", () => {
  expect(
    mutablePayload({
      selection: { facets: [], reason: "" },
      annotations: {
        entities: [
          {
            id: "e1",
            mention_span: { start: 0, end: 3 },
            surface_form: "ЦПК",
            canonical_name: " ЦПК ",
            entity_type: "organization",
            subject_role: "primary",
            registry_entity_id: "local-1",
            registry_status: "candidate",
            resolution_source: "registry",
          },
        ],
        stances: [],
        claims: [],
        rhetorical_features: [],
      },
    }),
  ).toEqual({
    selection: { facets: [], reason: "" },
    annotations: {
      entities: [
        {
          id: "e1",
          mention_span: { start: 0, end: 3 },
          surface_form: "ЦПК",
          canonical_name: "ЦПК",
          entity_type: "organization",
          subject_role: "primary",
        },
      ],
      stances: [],
      claims: [],
      rhetorical_features: [],
    },
  });
});
