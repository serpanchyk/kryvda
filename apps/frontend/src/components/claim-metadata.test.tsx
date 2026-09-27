// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, test, vi } from "vitest";

import {
  ClaimMetadata,
  type ClaimMetadataData,
} from "@/components/claim-metadata";

afterEach(() => cleanup());

const base: ClaimMetadataData = {
  published_at: "2026-09-26T14:32:00Z",
  channel_id: 7,
  channel_title: "Україна Сейчас",
  entity_id: 4,
  entity_name: "ЦПК",
  stance: "негативне",
  epistemic_status: "невпевнене",
  rhetoric: ["делегітимізація"],
  source_kind: "named_entity",
  source_entity_id: 12,
  source_entity_name: "Мар'яна Безугла",
};

function renderMetadata(data: ClaimMetadataData = base, onSource = vi.fn()) {
  render(
    <MemoryRouter>
      <ClaimMetadata data={data} actions={{ source: { onClick: onSource } }} />
    </MemoryRouter>,
  );
  return onSource;
}

describe("ClaimMetadata", () => {
  test("separates publication context, target, and resolved named source", async () => {
    const onSource = renderMetadata();
    expect(screen.getByText("Опубліковано")).toBeInTheDocument();
    expect(screen.getByText("Україна Сейчас")).toBeInTheDocument();
    expect(screen.getByText("Ціль")).toBeInTheDocument();
    expect(screen.getByText("ЦПК")).toBeInTheDocument();
    expect(screen.getByText("Мар'яна Безугла")).toBeInTheDocument();
    expect(screen.getByText("Тип: Названа особа")).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Мар'яна Безугла" }),
    );
    expect(onSource).toHaveBeenCalledOnce();
  });

  test.each([
    ["channel_editorial", null, "Позиція каналу"],
    ["named_entity", "Нерозв'язана згадка", "Нерозв'язана згадка"],
    ["external_unnamed", null, "Неназване зовнішнє джерело"],
  ] as const)(
    "renders %s attribution without dropping its source",
    (source_kind, source_entity_name, expected) => {
      renderMetadata({
        ...base,
        source_kind,
        source_entity_id: null,
        source_entity_name,
      });
      expect(screen.getByText(expected)).toBeInTheDocument();
    },
  );

  test("omits rhetoric metadata when no rhetoric is assigned", () => {
    renderMetadata({ ...base, rhetoric: [] });
    expect(screen.queryAllByText("Риторика")).toHaveLength(0);
  });

  test.each(["ствердження", "невпевнене", "питання"] as const)(
    "renders %s as immediately visible status",
    (epistemic_status) => {
      renderMetadata({ ...base, epistemic_status });
      expect(
        screen.getAllByText(
          epistemic_status === "ствердження"
            ? "Ствердження"
            : epistemic_status === "невпевнене"
              ? "Невпевнене"
              : "Питання",
        ).length,
      ).toBeGreaterThan(0);
    },
  );
});
