import { readFileSync } from "node:fs";
import { expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

test("annotator selects Unicode evidence, saves a draft and finalizes a control", async () => {
  const schema = JSON.parse(
    readFileSync("../../datasets/golden_v0/annotation_schema_v1.json", "utf8"),
  );
  const source = {
    post_revision_id: 1,
    raw_post_id: 1,
    channel_id: 1,
    channel_reference: "test",
    telegram_message_id: 1,
    published_at: "2026-09-08T00:00:00Z",
    text: "😀 ЦПК",
  };
  let item = {
    version: 1,
    status: "draft",
    record: {
      example_id: "golden_v0-001",
      schema_version: "annotation_schema_v1",
      source,
      selection: { facets: [], reason: "", is_keyword_false_positive: false },
      annotations: {
        entities: [],
        stances: [],
        claims: [],
        rhetorical_features: [],
      },
    },
  };
  let started = false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url, options) => {
      let result;
      if (url === "/api/schema") result = schema;
      else if (url === "/api/state")
        result = { records: started ? { 1: item } : {}, registry: [] };
      else if (url === "/api/channels") result = [{ id: 1, title: "Канал" }];
      else if (url.startsWith("/api/posts")) result = [source];
      else if (url === "/api/start/1") {
        started = true;
        result = item;
      } else if (url === "/api/records/1") {
        item = { ...JSON.parse(options.body), version: item.version + 1 };
        result = item;
      }
      return { ok: true, json: async () => structuredClone(result) };
    }),
  );
  document.body.innerHTML = '<div id="root"></div>';
  await import("./main.jsx");
  fireEvent.click(await screen.findByText("😀 ЦПК"));
  await screen.findByText("golden_v0-001");
  const article = document.querySelector("article");
  const range = document.createRange();
  range.setStart(article.firstChild, 3);
  range.setEnd(article.firstChild, 6);
  window.getSelection().removeAllRanges();
  window.getSelection().addRange(range);
  fireEvent.mouseUp(article);
  fireEvent.click(screen.getByText("+ Додати: сутності"));
  await waitFor(
    () =>
      expect(item.record.annotations.entities[0]?.mention_span).toEqual({
        start: 2,
        end: 5,
      }),
    { timeout: 3000 },
  );
  await waitFor(() =>
    expect(screen.getByText("Видалити запис").disabled).toBe(false),
  );
  fireEvent.click(screen.getByText("Видалити запис"));
  fireEvent.change(screen.getByLabelText("Чому обрано цей пост"), {
    target: { value: "Контрольний приклад" },
  });
  fireEvent.click(screen.getByLabelText("Хибний збіг ключового слова"));
  fireEvent.click(screen.getByText("+ Додати"));
  const areas = screen.getAllByRole("textbox");
  fireEvent.change(
    areas.find(
      (a) =>
        a !== screen.getByLabelText("Чому обрано цей пост") &&
        a.tagName === "TEXTAREA",
    ),
    { target: { value: "контроль" } },
  );
  fireEvent.click(screen.getByText("Завершити й перейти далі →"));
  await waitFor(() => expect(item.status).toBe("completed"));
  expect(item.record.selection.reason).toBe("Контрольний приклад");
  expect(item.record.annotations.entities).toEqual([]);
});
