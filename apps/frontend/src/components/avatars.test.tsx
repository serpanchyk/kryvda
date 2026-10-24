// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test } from "vitest";

import { EntityAvatar, PhotoCredits } from "@/components/avatars";
import photos from "@/lib/entity-photos.json";

afterEach(() => cleanup());

test("falls back to initials when the registry entry has no verified photo", () => {
  const { container } = render(<EntityAvatar id={-1} name="Тестова Сутність" />);
  expect(container.querySelector("img")).toBeNull();
  expect(screen.getByText("ТС")).toBeInTheDocument();
});

test("lists every photo's author and licence only once the credits are opened", async () => {
  render(<PhotoCredits />);
  const summary = screen.getByText("Авторство фото і логотипів");
  expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  await userEvent.click(summary);
  expect(screen.getAllByRole("listitem")).toHaveLength(Object.keys(photos).length);
});
