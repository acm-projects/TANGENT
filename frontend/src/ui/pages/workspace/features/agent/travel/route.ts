import { HOME, nodeOf, stationEl } from "@/store/gentStations";

/* How Gent gets from one station to another, as segments of screen points read live each frame (the map can pan
 * or zoom mid-flight). Between two cards he keeps to the strings: up to the nearest card both hang from, then
 * down, running over each card he passes (and knocking it). Anywhere else he takes a short arc. */

export type Pt = { x: number; y: number };
export type Segment = {
  points(): Pt[] | null;
  /** knocked as Gent reaches this segment */
  hit?: () => Element | undefined;
};

/** The cards from `from` to `to` along the drawn strings (`"parent->child"` ids), or null if they don't connect. */
export function treePath(edges: string[], from: string, to: string): string[] | null {
  const next = new Map<string, string[]>();
  for (const id of edges) {
    const [a, b] = id.split("->");
    if (!a || !b) continue;
    next.set(a, [...(next.get(a) ?? []), b]);
    next.set(b, [...(next.get(b) ?? []), a]);
  }
  const back = new Map<string, string>([[from, from]]);
  const queue = [from];
  while (queue.length) {
    const at = queue.shift()!;
    if (at === to) {
      const path = [to];
      while (path[0] !== from) path.unshift(back.get(path[0]!)!);
      return path;
    }
    for (const n of next.get(at) ?? []) {
      if (back.has(n)) continue;
      back.set(n, at);
      queue.push(n);
    }
  }
  return null;
}

const topOf = (el: Element): Pt => {
  const r = el.getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.top };
};
const bottomOf = (el: Element): Pt => {
  const r = el.getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.bottom };
};
const centreOf = (el: Element): Pt => {
  const r = el.getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
};

/** Where Gent leaves from and lands: his socket's centre at home, a station's top centre anywhere else. */
export function anchorOf(key: string): Pt | null {
  const el = stationEl(key);
  if (!el) return null;
  return key === HOME ? centreOf(el) : topOf(el);
}

function edgeEl(map: Element, id: string) {
  return map.querySelector<SVGPathElement>(`.react-flow__edge[data-id="${CSS.escape(id)}"] .react-flow__edge-path`);
}

/** A string's points on screen, parent to child (or reversed). */
function stringPoints(path: SVGPathElement, reverse: boolean, samples = 18): Pt[] | null {
  const m = path.getScreenCTM();
  if (!m) return null;
  const len = path.getTotalLength();
  const pts = Array.from({ length: samples + 1 }, (_, i) => {
    const p = path.getPointAtLength((len * i) / samples);
    const s = new DOMPoint(p.x, p.y).matrixTransform(m);
    return { x: s.x, y: s.y };
  });
  return reverse ? pts.reverse() : pts;
}

/** Card to card along the strings, or null (not both on the map, or not connected): fly an arc instead. */
function alongStrings(fromId: string, toId: string): Segment[] | null {
  const fromEl = stationEl(`node:${fromId}`);
  const map = fromEl?.closest(".react-flow");
  if (!fromEl || !map) return null;
  const edges = [...map.querySelectorAll(".react-flow__edge")].map((e) => e.getAttribute("data-id") ?? "");
  const path = treePath(edges, fromId, toId);
  if (!path || path.length < 2) return null;
  const card = (id: string) => () => stationEl(`node:${id}`);
  const segs: Segment[] = [];
  let side: "top" | "bottom" = "top"; // Gent starts on top of the card he leaves
  for (let i = 0; i < path.length - 1; i++) {
    const [a, b] = [path[i]!, path[i + 1]!];
    const down = edges.includes(`${a}->${b}`);
    const string = edgeEl(map, down ? `${a}->${b}` : `${b}->${a}`);
    if (!string) return null;
    const exit = down ? "bottom" : "top";
    if (side !== exit) {
      // run over the card to the side the string leaves from
      const el = card(a);
      segs.push({ points: () => { const c = el(); return c ? (exit === "bottom" ? [topOf(c), bottomOf(c)] : [bottomOf(c), topOf(c)]) : null; }, hit: i > 0 ? el : undefined });
    }
    segs.push({ points: () => stringPoints(string, !down), hit: i > 0 && side === exit ? card(a) : undefined });
    side = down ? "top" : "bottom";
  }
  // on top of the card he lands on
  const last = card(path[path.length - 1]!);
  if (side === "bottom") segs.push({ points: () => { const c = last(); return c ? [bottomOf(c), topOf(c)] : null; } });
  return segs;
}

/** A hop that lifts and drops onto the target, as ink falls onto a page. */
function arc(from: string, to: string): Segment[] {
  return [{
    points: () => {
      const a = anchorOf(from), b = anchorOf(to);
      if (!a || !b) return null;
      const lift = Math.min(160, 40 + Math.hypot(b.x - a.x, b.y - a.y) * 0.25);
      const c = { x: (a.x + b.x) / 2, y: Math.min(a.y, b.y) - lift };
      return Array.from({ length: 25 }, (_, i) => {
        const t = i / 24, u = 1 - t;
        return { x: u * u * a.x + 2 * u * t * c.x + t * t * b.x, y: u * u * a.y + 2 * u * t * c.y + t * t * b.y };
      });
    },
  }];
}

export function routeBetween(from: string, to: string): Segment[] {
  const [a, b] = [nodeOf(from), nodeOf(to)];
  return (a && b && alongStrings(a, b)) || arc(from, to);
}
