import { rng } from "../Ink/ink";

/* A torn paper outline for one panel: an SVG path (px, origin at the panel's top-left) that walks the perimeter in
 * ~4px steps, each point pushed inward by a fibrous 1–5px (two noise waves plus a little jitter). Each corner is its
 * own: an irregular rounding of 2–7px, or now and then a tiny dog-ear. Pure and seeded, so a panel keeps its shape. */

const STEP = 4;
type Pt = [number, number];

export function tornPath(w: number, h: number, seed: number): string {
  const rand = rng(seed);
  const wave = () => ({ p1: rand() * Math.PI * 2, p2: rand() * Math.PI * 2, l1: 17 + rand() * 12, l2: 5 + rand() * 3 });
  const waves = [wave(), wave(), wave(), wave()]; // one per side
  const depth = (side: number, t: number) => {
    const k = waves[side];
    const n = 0.55 * Math.sin((t / k.l1) * Math.PI * 2 + k.p1) + 0.3 * Math.sin((t / k.l2) * Math.PI * 2 + k.p2) + 0.15 * (rand() * 2 - 1);
    return Math.min(5, Math.max(1, 3 + 2 * n));
  };
  const clamp = ([x, y]: Pt): Pt => [Math.min(w, Math.max(0, x)), Math.min(h, Math.max(0, y))];
  const reach = Math.min(7, w / 4, h / 4);

  // each corner: how far it eats along each edge, and the points that make its shape (clockwise, in its own frame)
  const corners = [0, 1, 2, 3].map(() => {
    const r = Math.max(1, Math.min(reach, 2 + rand() * 5));
    const dogEar = rand() < 0.25;
    const pts: Pt[] = [];
    if (dogEar) {
      const k = r * (0.9 + rand() * 0.4);
      pts.push([k, 1 + rand()], [1 + rand(), k]); // a diagonal fold, slightly off true
    } else {
      for (let i = 0; i <= 4; i++) {
        const a = (i / 4) * (Math.PI / 2);
        const rr = r * (0.75 + rand() * 0.5);
        pts.push([r - rr * Math.sin(a), r - rr * Math.cos(a)]); // arc about (r, r), top-left frame
      }
      pts[0][1] = Math.max(1, pts[0][1]);
      pts[pts.length - 1][0] = Math.max(1, pts[pts.length - 1][0]);
    }
    return { r, pts: pts.reverse() }; // clockwise: up the left edge, then along the top
  });

  const out: Pt[] = [];
  const mapCorner = (c: number, [x, y]: Pt): Pt =>
    c === 0 ? [x, y] : c === 1 ? [w - y, x] : c === 2 ? [w - x, h - y] : [y, h - x]; // rotate the top-left frame clockwise
  let along = 0;
  for (let side = 0; side < 4; side++) {
    const len = side % 2 === 0 ? w : h;
    // corner `side` (its shape ends the previous side's walk): its points run from the end of the previous
    // edge to the start of this one, so emit the corner first, then this edge's body up to the next corner
    for (const p of corners[side].pts) out.push(clamp(mapCorner(side, p)));
    const a = corners[side].r, b = corners[(side + 1) % 4].r;
    for (let s = a + STEP; s < len - b; s += STEP) {
      const d = depth(side, along + s);
      out.push(clamp(side === 0 ? [s, d] : side === 1 ? [w - d, s] : side === 2 ? [w - s, h - d] : [d, h - s]));
    }
    along += len;
  }
  return "M" + out.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join("L") + "Z";
}
