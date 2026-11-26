import { rng } from "../Ink/ink";

/* A torn paper outline for one panel: an SVG path (px, origin at the panel's top-left) that walks the perimeter in
 * uneven ~3px steps, each point pushed inward by 0.6–5px of layered value noise, fibres and the odd nick. Each corner is its
 * own: an irregular rounding of 2–7px, or now and then a tiny dog-ear. Pure and seeded, so a panel keeps its shape. */

const STEP = 3;
type Pt = [number, number];

/* Smooth 1D value noise: random values on a lattice `span` px apart, eased between. Not periodic, unlike sines. */
function valueNoise(rand: () => number, span: number) {
  const knots: number[] = [];
  return (t: number) => {
    const i = Math.floor(t / span), f = t / span - i;
    while (knots.length <= i + 1) knots.push(rand() * 2 - 1);
    const e = f * f * (3 - 2 * f);
    return knots[i] * (1 - e) + knots[i + 1] * e;
  };
}

export function tornPath(w: number, h: number, seed: number): string {
  const rand = rng(seed);
  // per side: a slow wander, a mid ripple and fine fibres at unrelated scales, plus now and then a nick
  const sides = [0, 1, 2, 3].map(() => {
    const octaves = [valueNoise(rand, 70 + rand() * 50), valueNoise(rand, 16 + rand() * 10), valueNoise(rand, 4 + rand() * 3)];
    const nicks: { at: number; width: number; deep: number }[] = [];
    for (let at = rand() * 120; at < 4000; at += 60 + rand() * 180) nicks.push({ at, width: 3 + rand() * 7, deep: 1 + rand() * 2.2 });
    return { octaves, nicks };
  });
  const depth = (side: number, t: number) => {
    const { octaves: [slow, mid, fine], nicks } = sides[side];
    let d = 2.2 + 1.1 * slow(t) + 0.55 * mid(t) + 0.45 * fine(t) + 0.3 * (rand() * 2 - 1);
    for (const n of nicks) {
      const k = 1 - Math.abs(t - n.at) / n.width;
      if (k > 0) d += n.deep * k;
    }
    return Math.min(5, Math.max(0.6, d));
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
  for (let side = 0; side < 4; side++) {
    const len = side % 2 === 0 ? w : h;
    // corner `side` (its shape ends the previous side's walk): its points run from the end of the previous
    // edge to the start of this one, so emit the corner first, then this edge's body up to the next corner
    // the corner sits as deep as the two edges it joins, so it never pokes out past them
    const inset = (depth((side + 3) % 4, 0) + depth(side, 0)) / 2;
    for (const [x, y] of corners[side].pts) out.push(clamp(mapCorner(side, [x + inset, y + inset])));
    const a = corners[side].r, b = corners[(side + 1) % 4].r;
    for (let s = a + STEP; s < len - b; s += STEP * (0.6 + rand() * 0.8)) {
      const d = depth(side, s);
      out.push(clamp(side === 0 ? [s, d] : side === 1 ? [w - d, s] : side === 2 ? [w - s, h - d] : [d, h - s]));
    }
  }
  return "M" + out.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join("L") + "Z";
}
