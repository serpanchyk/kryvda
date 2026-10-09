/** Axis-aligned box in pixel space. */
export interface Box { x0: number; y0: number; x1: number; y1: number }

export interface LabelSubject { id: number; cx: number; cy: number; r: number; width: number }

export interface PlacedLabel {
  id: number;
  /** Text anchor point (start of the text, on its baseline). */
  x: number;
  y: number;
  box: Box;
  /** Leader line from the point's edge to the label when the label had to move away. */
  leader?: [number, number, number, number];
}

export const LABEL_HEIGHT = 13;
const BASELINE = 10;
export const FAR_RINGS = [0, 8, 18, 30, 44, 60, 80, 104, 130];
/** Only positions touching the point: labels that read as attached without a leader line. */
export const ADJACENT_RINGS = [0, 5];
const DIRECTIONS: Array<[number, number]> = [[1, 0], [-1, 0], [0, -1], [0, 1], [1, -1], [-1, -1], [1, 1], [-1, 1]];

const overlaps = (a: Box, b: Box, pad = 1): boolean =>
  a.x0 < b.x1 + pad && a.x1 + pad > b.x0 && a.y0 < b.y1 + pad && a.y1 + pad > b.y0;

const inside = (box: Box, bounds: Box): boolean =>
  box.x0 >= bounds.x0 && box.x1 <= bounds.x1 && box.y0 >= bounds.y0 && box.y1 <= bounds.y1;

export const circleBox = (cx: number, cy: number, r: number): Box => ({ x0: cx - r, y0: cy - r, x1: cx + r, y1: cy + r });

function candidate(subject: LabelSubject, [dx, dy]: [number, number], ring: number): Box {
  const gap = subject.r + 3 + ring;
  const diagonal = dx !== 0 && dy !== 0 ? Math.SQRT1_2 : 1;
  const ax = subject.cx + dx * gap * diagonal;
  const ay = subject.cy + dy * gap * diagonal;
  const x0 = dx > 0 ? ax : dx < 0 ? ax - subject.width : ax - subject.width / 2;
  const y0 = dy > 0 ? ay : dy < 0 ? ay - LABEL_HEIGHT : ay - LABEL_HEIGHT / 2;
  return { x0, y0, x1: x0 + subject.width, y1: y0 + LABEL_HEIGHT };
}

/** Nearest point of a box to (x, y), used to end a leader line at the label's edge. */
function nearestOnBox(box: Box, x: number, y: number): [number, number] {
  return [Math.min(Math.max(x, box.x0), box.x1), Math.min(Math.max(y, box.y0), box.y1)];
}

/**
 * Place one label per subject, in priority order, so that no label overlaps a point, another
 * label, or any fixed obstacle, and every label stays inside the bounds. Labels try eight
 * directions on growing rings; a label moved off its point gets a leader line. Subjects with no
 * free position are left out rather than drawn over other text.
 */
export function placeLabels(subjects: LabelSubject[], obstacles: Box[], bounds: Box, rings: number[] = FAR_RINGS): PlacedLabel[] {
  const taken: Box[] = [...obstacles, ...subjects.map((subject) => circleBox(subject.cx, subject.cy, subject.r))];
  const placed: PlacedLabel[] = [];
  for (const subject of subjects) {
    let found: PlacedLabel | undefined;
    for (const ring of rings) {
      for (const direction of DIRECTIONS) {
        const box = candidate(subject, direction, ring);
        if (!inside(box, bounds) || taken.some((other) => overlaps(box, other))) continue;
        const leader = ring > 0 ? (() => {
          const [ex, ey] = nearestOnBox(box, subject.cx, subject.cy);
          const length = Math.hypot(ex - subject.cx, ey - subject.cy) || 1;
          return [subject.cx + ((ex - subject.cx) / length) * subject.r, subject.cy + ((ey - subject.cy) / length) * subject.r, ex, ey] as [number, number, number, number];
        })() : undefined;
        found = { id: subject.id, x: box.x0, y: box.y0 + BASELINE, box, leader };
        break;
      }
      if (found) break;
    }
    if (found) {
      placed.push(found);
      taken.push(found.box);
    }
  }
  return placed;
}
