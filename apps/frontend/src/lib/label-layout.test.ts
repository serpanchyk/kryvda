import { describe, expect, test } from "vitest";

import { circleBox, placeLabels, type Box } from "@/lib/label-layout";

const bounds: Box = { x0: 0, y0: 0, x1: 400, y1: 300 };
const overlap = (a: Box, b: Box) => a.x0 < b.x1 && a.x1 > b.x0 && a.y0 < b.y1 && a.y1 > b.y0;

describe("label layout", () => {
  test("labels every point in a crowded cluster without any overlap", () => {
    const subjects = Array.from({ length: 8 }, (_, index) => ({ id: index, cx: 200 + (index % 3) * 6, cy: 150 + Math.floor(index / 3) * 6, r: 5, width: 70 }));
    const placed = placeLabels(subjects, [], bounds);
    expect(placed).toHaveLength(8);
    const boxes = [...placed.map((label) => label.box), ...subjects.map((subject) => circleBox(subject.cx, subject.cy, subject.r))];
    for (let i = 0; i < placed.length; i += 1) {
      for (let j = 0; j < boxes.length; j += 1) {
        if (boxes[j] !== placed[i].box) expect(overlap(placed[i].box, boxes[j])).toBe(false);
      }
    }
    expect(placed.some((label) => label.leader)).toBe(true);
  });

  test("keeps labels inside the bounds and clear of fixed obstacles", () => {
    const obstacle: Box = { x0: 380, y0: 0, x1: 400, y1: 300 };
    const placed = placeLabels([{ id: 1, cx: 390, cy: 5, r: 4, width: 90 }], [obstacle], bounds);
    expect(placed).toHaveLength(1);
    const [label] = placed;
    expect(label.box.x0).toBeGreaterThanOrEqual(0);
    expect(label.box.x1).toBeLessThanOrEqual(400);
    expect(label.box.y0).toBeGreaterThanOrEqual(0);
    expect(overlap(label.box, obstacle)).toBe(false);
  });

  test("leaves a label out rather than drawing it over other text", () => {
    const wall: Box = { x0: 0, y0: 0, x1: 400, y1: 300 };
    expect(placeLabels([{ id: 1, cx: 200, cy: 150, r: 4, width: 60 }], [wall], bounds)).toEqual([]);
  });
});
