// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test } from "vitest";

import { AmbientToggle } from "@/components/liquid";

describe("animated background toggle", () => {
  afterEach(() => { cleanup(); window.localStorage.clear(); });

  test("turns the background off and remembers the choice", async () => {
    render(<AmbientToggle />);
    const toggle = screen.getByRole("button", { name: "Вимкнути анімований фон" });
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Увімкнути анімований фон" })).toHaveAttribute("aria-pressed", "false");
    expect(window.localStorage.getItem("kryvda:ambient")).toBe("off");
  });

  test("starts off when the browser remembered it off", () => {
    window.localStorage.setItem("kryvda:ambient", "off");
    render(<AmbientToggle withLabel />);
    expect(screen.getByRole("button", { name: /Анімований фон/ })).toHaveAttribute("aria-pressed", "false");
  });
});
