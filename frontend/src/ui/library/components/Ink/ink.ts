/* Gent's ink print ("J", settled 2026-11-05): a solid ink shape whose edge feathers into the page as short fibres,
 * flecks and a faint creep, with uneven ink drifting inside. Drawn on a canvas at device resolution (SVG filters
 * looked pixelated). Ported from the gent-ink prototype; the numbers are the ones the user picked.
 *
 *   InkSurface   one inked shape on one canvas: a fill (Gent's panels) or an outline (the card he is in).
 *                `drawn` (0..1) draws an outline on from its top centre, both ways round, for his arrivals.
 *   ticker       one rAF loop for every surface on screen, at 30fps.
 *
 * The shape and fuzz are a mask; two seamless noise tiles laid over it ("source-atop") are the uneven ink, and
 * moving them is the flow. Only the longest quarter of the fibres and a third of the flecks sway; the rest is
 * drawn once into a cached base. */

const J = { hairs: 2.4, reach: 2.6, tooth: 0.35, mottle: 0.1, pores: 0.55, swaySpeed: 2.6, swayAmount: 2.2 };
const FLOW = { blotch: [5.5, 2.2], grain: [-3.2, 4.1] } as const; // px per second, in different directions
const BUCKETS = 5;

export type InkKind = "fill" | "outline";
type Pt = [number, number];
type PerimeterPt = { x: number; y: number; nx: number; ny: number; t: number };
type Hair = { t: number; x: number; y: number; nx: number; ny: number; len: number; angle: number; bend: number; alpha: number; width: number; phase: number; speed: number; moves: boolean; bucket: number };
type Speck = { t: number; x: number; y: number; nx: number; ny: number; r: number; alpha: number; phase: number; speed: number; moves: boolean; bucket: number };
export type Edge = {
  pts: PerimeterPt[];
  outer: Pt[];
  /** an outline's inner edge, index-aligned with outer */
  inner: Pt[] | null;
  hairs: Hair[];
  specks: Speck[];
  halos: { alpha: number; pts: Pt[] }[];
  fill: string;
};

export const reducedMotion = () => typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;

/** seeded random, so each piece keeps its own shape across redraws */
export function rng(seed: number) {
  let s = seed >>> 0 || 1;
  return () => {
    s ^= s << 13;
    s ^= s >>> 17;
    s ^= s << 5;
    return ((s >>> 0) % 100000) / 100000;
  };
}

/** smooth closed noise around the perimeter: sines in whole turns, so it meets itself */
const NOISE_SAMPLES = 4096; // ~20 per cycle of the finest wave (200 round the loop): linear lookup is exact enough
const noiseTables = new Map<string, Float32Array>();

/** The noise, sampled once per seed into a table: an edge rebuilt every frame (a resize) then costs a lookup per
 * point instead of a hundred sines, and every build of the same seed has exactly the same edge. */
function loopNoise(seed: number, low: number, high: number, amp: number) {
  const key = `${seed}:${low}:${high}:${amp}`;
  let table = noiseTables.get(key);
  if (!table) {
    const r = rng(seed);
    const waves: { k: number; a: number; p: number }[] = [];
    for (let k = low; k <= high; k++) waves.push({ k, a: (amp * (0.4 + r())) / Math.sqrt(k), p: r() * Math.PI * 2 });
    table = new Float32Array(NOISE_SAMPLES + 1);
    for (let i = 0; i <= NOISE_SAMPLES; i++) {
      const t = i / NOISE_SAMPLES;
      table[i] = waves.reduce((v, w) => v + w.a * Math.sin(2 * Math.PI * w.k * t + w.p), 0);
    }
    noiseTables.set(key, table);
  }
  const values = table;
  return (t: number) => {
    const x = (((t % 1) + 1) % 1) * NOISE_SAMPLES, i = Math.floor(x);
    return values[i]! + (values[i + 1]! - values[i]!) * (x - i);
  };
}

/** points with outward normals round a rounded rectangle, by arc length, starting at the top left */
export function perimeter(w: number, h: number, radius: number, step: number): PerimeterPt[] {
  const r = Math.max(0, Math.min(radius, w / 2, h / 2));
  const q = Math.PI / 2;
  const arc = (cx: number, cy: number, a0: number) => (u: number) => {
    const a = a0 + u / (r || 1);
    return [cx + r * Math.cos(a), cy + r * Math.sin(a), Math.cos(a), Math.sin(a)];
  };
  const segs: { len: number; at(u: number): number[] }[] = [
    { len: w - 2 * r, at: (u) => [r + u, 0, 0, -1] },
    { len: q * r, at: arc(w - r, r, -q) },
    { len: h - 2 * r, at: (u) => [w, r + u, 1, 0] },
    { len: q * r, at: arc(w - r, h - r, 0) },
    { len: w - 2 * r, at: (u) => [w - r - u, h, 0, 1] },
    { len: q * r, at: arc(r, h - r, q) },
    { len: h - 2 * r, at: (u) => [0, h - r - u, -1, 0] },
    { len: q * r, at: arc(r, r, Math.PI) },
  ];
  const total = segs.reduce((s, g) => s + g.len, 0);
  const n = Math.max(24, Math.round(total / step));
  const pts: PerimeterPt[] = [];
  for (let i = 0; i < n; i++) {
    let d = (i / n) * total;
    let j = 0;
    while (j < segs.length - 1 && d > segs[j]!.len) d -= segs[j++]!.len;
    const [x, y, nx, ny] = segs[j]!.at(Math.min(d, segs[j]!.len)) as [number, number, number, number];
    pts.push({ x, y, nx, ny, t: i / n });
  }
  return pts;
}

const offsetEdge = (pts: PerimeterPt[], offset: number, noise: (t: number) => number): Pt[] =>
  pts.map((p) => {
    const o = offset + noise(p.t);
    return [p.x + p.nx * o, p.y + p.ny * o];
  });

/** The shape and its bleed as data, so the same edge draws still, or at any moment of its sway. `lite`: the
 * solid toothed shape only, on a coarser perimeter (no fibres, flecks or creep): cheap enough to rebuild every
 * frame while the shape is changing size. */
export function edgeOf(w: number, h: number, radius: number, kind: InkKind, seed: number, fill: string, lite = false): Edge {
  const cfg = J;
  const pts = perimeter(w, h, radius, lite ? 1.5 : 0.5);
  const rand = rng(seed * 19);
  const half = 1.5;
  const tooth = loopNoise(seed, 90, 200, cfg.tooth * 2.2);
  const outer = offsetEdge(pts, kind === "fill" ? 0 : half, tooth);
  const inner = kind === "fill" ? null : offsetEdge(pts, -half, loopNoise(seed + 3, 90, 200, cfg.tooth * 2.2));
  const sides = kind === "fill" ? [{ off: 0, dir: 1, share: 1 }] : [{ off: half, dir: 1, share: 0.7 }, { off: -half, dir: -1, share: 0.35 }];
  // mostly short straight feathering, flecks caught in the paper, and a creep that fades out (long curves read as hair)
  const hairs: Hair[] = [];
  const specks: Speck[] = [];
  const halos: Edge["halos"] = [];
  for (const side of lite ? [] : sides) {
    const count = Math.round(pts.length * 0.9 * cfg.hairs * side.share);
    for (let i = 0; i < count; i++) {
      const q = pts[Math.floor(rand() * pts.length)]!;
      hairs.push({
        t: q.t, x: q.x + q.nx * (side.off - 0.4 * side.dir), y: q.y + q.ny * (side.off - 0.4 * side.dir), nx: q.nx * side.dir, ny: q.ny * side.dir,
        len: cfg.reach * (0.1 + Math.pow(rand(), 3) * 0.85), angle: (rand() - 0.5) * 1.2, bend: (rand() - 0.5) * 0.25,
        alpha: 0.2 + rand() * 0.45, width: 0.22 + rand() * 0.3, phase: rand() * Math.PI * 2, speed: 0.6 + rand() * 1.1, moves: false, bucket: 0,
      });
    }
    const flecks = Math.round(pts.length * 0.7 * cfg.hairs * side.share);
    for (let j = 0; j < flecks; j++) {
      const f = pts[Math.floor(rand() * pts.length)]!;
      const out = Math.min(1.3, -Math.log(1 - rand() * 0.98) * 0.32) * cfg.reach;
      const slide = (rand() - 0.5) * 1.5;
      const fade = 1 - out / (cfg.reach * 1.4);
      specks.push({
        t: f.t, x: f.x + f.nx * (side.off + side.dir * out) - f.ny * slide, y: f.y + f.ny * (side.off + side.dir * out) + f.nx * slide,
        nx: f.nx * side.dir, ny: f.ny * side.dir, r: 0.18 + rand() * 0.32 * fade, alpha: 0.25 + rand() * 0.5 * fade,
        phase: rand() * Math.PI * 2, speed: 0.5 + rand(), moves: false, bucket: 0,
      });
    }
    // the creep: for an outline only outward, so the card stays clean
    if (side.dir < 0) continue;
    halos.push({ alpha: 0.14, pts: offsetEdge(pts, side.off + cfg.reach * 0.3, loopNoise(seed + 9, 12, 60, cfg.reach * 0.25)) });
    halos.push({ alpha: 0.07, pts: offsetEdge(pts, side.off + cfg.reach * 0.65, loopNoise(seed + 13, 10, 50, cfg.reach * 0.35)) });
  }
  const lengths = hairs.map((hr) => hr.len).sort((a, b) => a - b);
  const longEnough = lengths[Math.floor(lengths.length * 0.75)] ?? 0;
  for (const hr of hairs) {
    hr.moves = hr.len >= longEnough;
    hr.bucket = Math.min(BUCKETS - 1, Math.floor(((hr.alpha - 0.2) / 0.45) * BUCKETS)) * 2 + (hr.width > 0.37 ? 1 : 0);
  }
  specks.forEach((sp, k) => {
    sp.moves = k % 3 === 0;
    sp.bucket = Math.min(BUCKETS - 1, Math.max(0, Math.floor(((sp.alpha - 0.1) / 0.65) * BUCKETS)));
  });
  return { pts, outer, inner, hairs, specks, halos, fill };
}

function trace(ctx: CanvasRenderingContext2D, pts: Pt[], move = true) {
  pts.forEach(([x, y], i) => (i || !move ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
  ctx.closePath();
}

/** fill the band between two index-aligned edges, only where seen(i / n): one shape per unbroken stretch */
function partialBand(ctx: CanvasRenderingContext2D, outer: Pt[], inner: Pt[], seen: (u: number) => boolean) {
  const n = outer.length;
  let start = 0;
  for (let g = 0; g < n; g++) if (!seen(g / n)) { start = g; break; }
  let run: number[] = [];
  const flush = () => {
    if (run.length > 1) {
      ctx.beginPath();
      run.forEach((i, k) => (k ? ctx.lineTo(...outer[i]!) : ctx.moveTo(...outer[i]!)));
      for (let k = run.length - 1; k >= 0; k--) ctx.lineTo(...inner[run[k]!]!);
      ctx.closePath();
      ctx.fill();
    }
    run = [];
  };
  for (let j = 0; j <= n; j++) {
    const i = (start + j) % n;
    if (j < n && seen(i / n)) run.push(i);
    else flush();
  }
}

/** Draw an edge (ctx already in CSS px). `t` seconds sways the fibres that move (0: still); `part` draws only the
 * still or only the moving pieces; `seen` limits an outline to the stretch drawn on so far. */
export function drawEdge(ctx: CanvasRenderingContext2D, e: Edge, t: number, part?: "still" | "moving", seen?: (u: number) => boolean) {
  const want = (item: { moves: boolean; t: number }) => (!part || (part === "moving") === item.moves) && (!seen || seen(item.t));
  ctx.fillStyle = ctx.strokeStyle = e.fill;
  ctx.globalAlpha = 1;
  if (part !== "moving") {
    if (seen && e.inner) partialBand(ctx, e.outer, e.inner, seen);
    else if (!seen) {
      ctx.beginPath();
      trace(ctx, e.outer);
      if (e.inner) {
        trace(ctx, [...e.inner].reverse());
        ctx.fill("evenodd");
      } else ctx.fill();
    }
  }
  ctx.lineCap = "round";
  const paths = Array.from({ length: BUCKETS * 2 }, () => new Path2D());
  for (const hr of e.hairs) {
    if (!want(hr)) continue;
    const ht0 = hr.moves ? t : 0;
    const ht = ht0 * hr.speed * J.swaySpeed;
    const sway = ht0 ? Math.sin(ht + hr.phase) : 0;
    const stretch = ht0 ? 1 + 0.22 * J.swayAmount * Math.sin(ht * 0.7 + hr.phase * 1.7) : 1;
    const a = hr.angle + sway * 0.35 * J.swayAmount;
    const len = hr.len * Math.max(0.2, stretch);
    const bend = (hr.bend + sway * 0.25 * J.swayAmount) * len * 0.5;
    const ca = Math.cos(a), sa = Math.sin(a);
    const nx = hr.nx * ca - hr.ny * sa, ny = hr.ny * ca + hr.nx * sa;
    const path = paths[hr.bucket]!;
    path.moveTo(hr.x, hr.y);
    path.quadraticCurveTo(hr.x + nx * len * 0.5 - ny * bend, hr.y + ny * len * 0.5 + nx * bend, hr.x + nx * len, hr.y + ny * len);
  }
  paths.forEach((p, i) => {
    ctx.globalAlpha = 0.2 + (((i >> 1) + 0.5) / BUCKETS) * 0.45;
    ctx.lineWidth = i & 1 ? 0.45 : 0.3;
    ctx.stroke(p);
  });
  const dots = Array.from({ length: BUCKETS }, () => new Path2D());
  for (const sp of e.specks) {
    if (!want(sp)) continue;
    const drift = t && sp.moves ? Math.sin(t * sp.speed * J.swaySpeed + sp.phase) * 0.35 * J.swayAmount : 0;
    const cx = sp.x + sp.nx * drift, cy = sp.y + sp.ny * drift;
    dots[sp.bucket]!.moveTo(cx + sp.r, cy);
    dots[sp.bucket]!.arc(cx, cy, sp.r, 0, Math.PI * 2);
  }
  dots.forEach((d, i) => {
    ctx.globalAlpha = 0.1 + ((i + 0.5) / BUCKETS) * 0.65;
    ctx.fill(d);
  });
  if (part !== "moving") {
    for (const h of e.halos) {
      ctx.globalAlpha = h.alpha;
      if (seen) {
        if (e.inner) partialBand(ctx, h.pts, e.inner, seen);
        continue;
      }
      ctx.beginPath();
      trace(ctx, h.pts);
      if (e.inner) {
        trace(ctx, [...e.inner].reverse());
        ctx.fill("evenodd");
      } else ctx.fill();
    }
  }
  ctx.globalAlpha = 1;
}

/* ── the uneven ink: seamless noise tiles ───────────────────────────────────────────────────── */

/** periodic value noise, so a tile built from it repeats without a seam */
function tileNoise(seed: number, period: number) {
  const r = rng(seed);
  const grid = new Float32Array(period * period).map(() => r());
  const at = (x: number, y: number) => grid[(((y % period) + period) % period) * period + (((x % period) + period) % period)]!;
  return (x: number, y: number) => {
    const xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi;
    const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
    const a = at(xi, yi), b = at(xi + 1, yi), c = at(xi, yi + 1), d = at(xi + 1, yi + 1);
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
  };
}

function hexToRgb(hex: string) {
  const h = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)) as [number, number, number];
}

/** a tile: where the noise is high the ink is paler (paper showing through), where low it is denser */
function inkTexture(seed: number, cell: number, period: number, light: number, dark: number, pores: number, paper: string, dpr: number) {
  const c = document.createElement("canvas");
  c.width = c.height = Math.round(cell * period * dpr);
  const ctx = c.getContext("2d")!;
  const img = ctx.createImageData(c.width, c.height);
  const d = img.data;
  const n = tileNoise(seed, period), fine = tileNoise(seed + 1, period * 4), poresAt = tileNoise(seed + 2, period * 8);
  const [pr, pg, pb] = hexToRgb(paper);
  for (let y = 0; y < c.height; y++) {
    for (let x = 0; x < c.width; x++) {
      const px = x / dpr / cell, py = y / dpr / cell, k = (y * c.width + x) * 4;
      const m = (n(px, py) - 0.5) * 2 + (fine(px * 4, py * 4) - 0.5) * 0.7;
      // pale pores: the tops of a fine noise field, so they come in small clumps
      const pv = pores ? poresAt(px * 8, py * 8) : 0;
      if (pv > 1 - 0.035 * pores || m > 0) {
        d[k] = pr;
        d[k + 1] = pg;
        d[k + 2] = pb;
        d[k + 3] = pv > 1 - 0.035 * pores ? 110 + (pv - 0.95) * 600 : Math.min(1, m) * light * 255;
      } else d[k + 3] = Math.min(1, -m) * dark * 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  return c;
}

let tiles: { blotch: HTMLCanvasElement; grain: HTMLCanvasElement; dpr: number } | null = null;
function textures(dpr: number) {
  if (!tiles || tiles.dpr !== dpr) {
    const paper = inkColors().paper;
    tiles = {
      dpr,
      blotch: inkTexture(11, 18, 24, J.mottle * 1.6, J.mottle * 1.2, J.pores, paper, dpr), // the big uneven patches
      grain: inkTexture(29, 6, 48, J.mottle * 0.9, J.mottle * 0.7, 0, paper, dpr), // finer streaks over them
    };
  }
  return tiles;
}

/** Gent's inks (colors.css), one pair for both themes like the red */
let colors: { fill: string; line: string; paper: string } | null = null;
export function inkColors() {
  // read once: they're the same in both themes, and reading styles mid-resize forces a style recalculation
  if (colors) return colors;
  const css = getComputedStyle(document.documentElement);
  const read = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback;
  colors = { fill: read("--gent-ink", "#006c93"), line: read("--blue-gent", "#0083b2"), paper: read("--on-gent-ink", "#f3f2ef") };
  return colors;
}

/* ── one inked shape on one canvas ──────────────────────────────────────────────────────────── */

const FIBRE_FADE_MS = 120;
const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const loopDist = (a: number, b: number) => {
  const d = Math.abs(a - b) % 1;
  return Math.min(d, 1 - d);
};

export class InkSurface {
  readonly canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private kind: InkKind;
  private seed: number;
  /** room round the shape for the fuzz (and, for an outline, the splash) */
  readonly pad: number;
  private edge: Edge | null = null;
  private base: HTMLCanvasElement | null = null;
  private live: HTMLCanvasElement | null = null;
  private top = 0;
  private offset: number;
  private patterns: { tex: object; blotch: CanvasPattern | null; grain: CanvasPattern | null } | null = null;
  private w = 0;
  private dpr = 1;
  /** how much of an outline is drawn on: 1 settled, 0 none (Gent's arrival draws it from the top centre) */
  drawn = 1;
  /** a lite build (the shape only), and when the fibres of the full build after it started fading in */
  private lite = false;
  private fibresFrom = 0;
  /** how strongly the uneven ink shows, 0..1 (a large reading surface wants it calmer) */
  mottle = 1;

  constructor(canvas: HTMLCanvasElement, kind: InkKind, seed: number) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d")!;
    this.kind = kind;
    this.seed = seed;
    this.pad = kind === "fill" ? 10 : 30;
    this.offset = rng(seed * 5)() * 300;
  }

  /** (Re)shape to a box of w × h CSS px with corner radius r. `scale` is any CSS zoom the canvas sits under.
   * `lite` while the box is resizing (the solid shape only); a full build after a lite one fades the fibres in. */
  build(w: number, h: number, r: number, scale = 1, lite = false) {
    if (w < 1 || h < 1) return;
    const dpr = Math.min(3, (window.devicePixelRatio || 1) * scale);
    const pad = this.pad;
    this.w = w;
    this.dpr = dpr;
    const W = Math.ceil((w + pad * 2) * dpr), H = Math.ceil((h + pad * 2) * dpr);
    Object.assign(this.canvas, { width: W, height: H });
    Object.assign(this.canvas.style, { width: `${w + pad * 2}px`, height: `${h + pad * 2}px`, left: `${-pad}px`, top: `${-pad}px` });
    const colors = inkColors();
    this.edge = edgeOf(w, h, Math.min(r, h / 2), this.kind, this.seed, this.kind === "fill" ? colors.fill : colors.line, lite);
    this.fibresFrom = lite ? Infinity : this.lite ? performance.now() : 0;
    this.lite = lite;
    const pts = this.edge.pts;
    let best = 0;
    pts.forEach((p, i) => {
      if (p.y < 1 && Math.abs(p.x - w / 2) < Math.abs(pts[best]!.x - w / 2)) best = i;
    });
    this.top = best / pts.length; // where Gent lands: the top centre
    // reused between builds (a resize rebuilds every frame); setting the size clears them
    const layer = (c: HTMLCanvasElement | null) => Object.assign(c ?? document.createElement("canvas"), { width: W, height: H });
    this.base = layer(this.base);
    this.live = layer(this.live);
    if (lite) return; // the shape alone is drawn straight into the live layer
    const bc = this.base.getContext("2d")!;
    bc.setTransform(dpr, 0, 0, dpr, pad * dpr, pad * dpr);
    drawEdge(bc, this.edge, 0, "still");
  }

  /** the top centre, in this surface's own CSS px (0,0 is the host's top left) */
  get landing() {
    return { x: this.w / 2, y: 0 };
  }

  render(ms: number) {
    const e = this.edge, live = this.live, base = this.base;
    if (!e || !live || !base) return;
    const { dpr, pad } = this;
    const still = reducedMotion();
    const t = still ? 0 : inkSeconds(ms);
    const lc = live.getContext("2d")!;
    lc.setTransform(1, 0, 0, 1, 0, 0);
    lc.clearRect(0, 0, live.width, live.height);
    lc.setTransform(dpr, 0, 0, dpr, pad * dpr, pad * dpr);
    const drawn = this.kind === "fill" ? 1 : Math.max(0, Math.min(1, this.drawn));
    // the fibres fade in over FIBRE_FADE_MS after a resize settles, so the full edge doesn't pop in
    const fibres = this.lite ? 0 : Math.min(1, (performance.now() - this.fibresFrom) / FIBRE_FADE_MS);
    if (drawn >= 1 && fibres < 1) {
      lc.setTransform(1, 0, 0, 1, 0, 0);
      if (fibres > 0) {
        lc.globalAlpha = fibres;
        lc.drawImage(base, 0, 0);
        lc.globalAlpha = 1;
      }
      lc.setTransform(dpr, 0, 0, dpr, pad * dpr, pad * dpr);
      drawEdge(lc, { ...e, hairs: [], specks: [], halos: [] }, 0); // the solid shape, at full strength
    } else if (drawn >= 1) {
      lc.setTransform(1, 0, 0, 1, 0, 0);
      lc.drawImage(base, 0, 0);
      lc.setTransform(dpr, 0, 0, dpr, pad * dpr, pad * dpr);
      drawEdge(lc, e, t, "moving");
    } else if (drawn > 0) {
      // drawn on from the impact, both ways round, led by a bead of ink at each end, after a splash
      const reach = ease(drawn) * 0.5 + 0.006, top = this.top;
      drawEdge(lc, e, t, undefined, (u) => loopDist(u, top) <= reach);
      lc.fillStyle = e.fill;
      const inner = e.inner ?? e.outer, n = e.outer.length;
      for (const u of [top + reach, top - reach]) {
        const i = Math.round((((u % 1) + 1) % 1) * n) % n;
        lc.beginPath();
        lc.arc((e.outer[i]![0] + inner[i]![0]) / 2, (e.outer[i]![1] + inner[i]![1]) / 2, 2.8 * (1 - drawn * 0.6), 0, Math.PI * 2);
        lc.fill();
      }
      const splash = rng(3), tt = Math.min(1, drawn * 2.4), cx = this.w / 2;
      if (tt < 1) {
        lc.globalAlpha = 1 - tt;
        for (let d = 0; d < 7; d++) {
          const a = -Math.PI * (0.15 + splash() * 0.7), v = 12 + splash() * 20, size = 0.9 + splash() * 1.3;
          lc.beginPath();
          lc.arc(cx + Math.cos(a) * v * tt, Math.sin(a) * v * tt + 26 * tt * tt, size, 0, Math.PI * 2);
          lc.fill();
        }
        lc.globalAlpha = 1;
      }
    }
    // the drifting ink over the mask
    const ctx = this.ctx, W = this.canvas.width, H = this.canvas.height, tex = textures(dpr);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalCompositeOperation = "source-over";
    ctx.clearRect(0, 0, W, H);
    if (drawn <= 0) return;
    ctx.drawImage(live, 0, 0);
    ctx.globalCompositeOperation = "source-atop";
    ctx.globalAlpha = this.mottle;
    if (this.patterns?.tex !== tex) this.patterns = { tex, blotch: ctx.createPattern(tex.blotch, "repeat"), grain: ctx.createPattern(tex.grain, "repeat") };
    for (const name of ["blotch", "grain"] as const) {
      const pattern = this.patterns[name];
      if (!pattern) continue;
      const [vx, vy] = FLOW[name];
      pattern.setTransform(new DOMMatrix([1, 0, 0, 1, (this.offset + vx * t) * dpr, (this.offset * 0.7 + vy * t) * dpr]));
      ctx.fillStyle = pattern;
      ctx.fillRect(0, 0, W, H);
    }
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
  }
}

/* ── the ink's own clock: slow at rest, full speed while Gent works ─────────────────────────── */

export const PACE_REST = 0.15;
let pace = PACE_REST;
let target = PACE_REST;
let clock = 0;
let lastReal: number | null = null;

/** How fast the ink drifts and its fibres sway: 1 while Gent works, PACE_REST at rest. Eases there over ~1s. */
export function setInkPace(value: number) {
  target = value;
}

/** Seconds on the ink's clock at real time `ms` (every surface reads the same clock, so they move together). */
export function inkSeconds(ms: number): number {
  if (lastReal !== null && ms > lastReal) {
    const dt = Math.min(ms - lastReal, 250); // a backgrounded tab doesn't jump
    pace += (target - pace) * Math.min(1, dt / 400);
    clock += (dt / 1000) * pace;
  }
  if (lastReal === null || ms > lastReal) lastReal = ms;
  return clock;
}

/* ── one loop for every surface on screen ───────────────────────────────────────────────────── */

type Tick = (ms: number) => void;
const ticks = new Set<Tick>();
const STEP = 1000 / 30; // the ink moves slowly: 60fps buys nothing
let last = -STEP;
let frame = 0;

function loop(ms: number) {
  if (ms - last >= STEP) {
    last = ms;
    ticks.forEach((tick) => tick(ms));
  }
  frame = ticks.size ? requestAnimationFrame(loop) : 0;
}

/** Call `tick` every ink frame until the returned function is called. */
export function onInkFrame(tick: Tick): () => void {
  ticks.add(tick);
  if (!frame) frame = requestAnimationFrame(loop);
  return () => ticks.delete(tick);
}
