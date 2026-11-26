import type { NodeMeta, TagColor, TreeResponse } from "@/api/types";
import { caseLayout } from "@/store/layout";
import { selectThread } from "@/store/treeStore";

/* What a case's card on the dashboard shows, worked out from its tree. Pure.
 *
 * The photo is the case's board in miniature, laid out by the map's own layout (caseLayout: merged cards below
 * what they join, their strings from each source), so the two always have the same shape: paper cards, the case
 * card in its double frame, strings between them, tags as little flags, branches that ended faded, and the thread
 * to the newest card strung in red, where the case left off. Drawn by CaseSketch.
 *
 * It also files the case: open, cold (nothing new for COLD_DAYS) or closed (every branch has ended). */

export type SketchCard = {
  /** top-left corner and size, in board units (px at zoom 1) */
  x: number;
  y: number;
  w: number;
  h: number;
  root: boolean;
  onPath: boolean;
  /** the newest card: where the case left off */
  latest: boolean;
  tag: TagColor | null;
  ended: boolean;
};

export type SketchString = { d: string; onPath: boolean };

export type Sketch = { box: { x: number; y: number; w: number; h: number }; cards: SketchCard[]; strings: SketchString[] };

export type CaseStatus = "open" | "cold" | "closed";

export type CaseFacts = {
  sketch: Sketch;
  cards: number;
  /** the latest thing that happened in it: a card made or a branch ended */
  lastActive: string;
  status: CaseStatus;
};

/** A case nothing has happened in for this long is cold. */
export const COLD_DAYS = 21;

// a card on the board is about this big (MindMap.css: up to 17rem wide, at least 4.5rem tall); the case card more
const CARD = { w: 250, h: 72 };
const ROOT = { w: 290, h: 104 };
// the photo's frame: at least this much board, so a small case's cards stay card-sized instead of filling it
const MIN_BOX = { w: 1300, h: 800 };
const PAD = 60;

export function caseFacts({ tree, nodes }: TreeResponse, now = Date.now()): CaseFacts {
  const nodesById = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const childrenByParent: Record<string, string[]> = {};
  for (const n of [...nodes].sort((a, b) => a.fork_index - b.fork_index)) {
    if (n.parent_id) (childrenByParent[n.parent_id] ??= []).push(n.id);
  }
  const { positions, merges } = caseLayout({ rootId: tree.root_node_id, nodesById, childrenByParent });
  const ids = Object.keys(positions).filter((id) => nodesById[id]);

  const newest = ids.map((id) => nodesById[id]!).reduce<NodeMeta | null>((a, b) => (!a || b.created_at > a.created_at ? b : a), null);
  const path = newest ? selectThread({ nodesById }, newest.id) : new Set<string>();

  const cards: SketchCard[] = ids.map((id) => {
    const n = nodesById[id]!;
    const size = id === tree.root_node_id ? ROOT : CARD;
    const at = positions[id]!;
    return {
      x: at.x - size.w / 2,
      y: at.y,
      ...size,
      root: id === tree.root_node_id,
      onPath: path.has(id),
      latest: id === newest?.id,
      tag: n.tag?.color ?? null,
      ended: Boolean(n.resolved),
    };
  });
  const card = new Map(ids.map((id, i) => [id, cards[i]!]));

  // a string from the bottom of each parent (or each card a merge joins) down to the top of its card
  const strings: SketchString[] = [];
  for (const id of ids) {
    const from = merges.get(id) ?? (nodesById[id]!.parent_id ? [nodesById[id]!.parent_id!] : []);
    for (const source of from) {
      const a = card.get(source);
      const b = card.get(id);
      if (!a || !b) continue;
      const sx = a.x + a.w / 2;
      const sy = a.y + a.h;
      const tx = b.x + b.w / 2;
      const ty = b.y;
      const bend = Math.max(40, (ty - sy) / 2);
      strings.push({ d: `M${sx} ${sy} C${sx} ${sy + bend} ${tx} ${ty - bend} ${tx} ${ty}`, onPath: path.has(id) && path.has(source) });
    }
  }
  // red over grey, as on the map
  strings.sort((a, b) => Number(a.onPath) - Number(b.onPath));

  // the photo's frame: the board around the cards, never tighter than MIN_BOX, centred on them
  const minX = cards.length ? Math.min(...cards.map((c) => c.x)) : 0;
  const maxX = cards.length ? Math.max(...cards.map((c) => c.x + c.w)) : 0;
  const maxY = cards.length ? Math.max(...cards.map((c) => c.y + c.h)) : 0;
  const w = Math.max(maxX - minX + 2 * PAD, MIN_BOX.w);
  const h = Math.max(maxY + 2 * PAD, MIN_BOX.h, w * 0.5);
  const box = { x: (minX + maxX) / 2 - w / 2, y: maxY / 2 - h / 2, w, h };

  // the case's latest move: a card made, or a branch ended
  const times = nodes.flatMap((n) => [n.created_at, n.resolved?.at ?? ""]).filter(Boolean);
  const lastActive = times.reduce((a, b) => (b > a ? b : a), "") || tree.created_at;

  // closed: it has branches, and every one has ended (a card with no branches, and no merge it feeds, is an end)
  const feeding = new Set([...merges.values()].flat());
  const ends = ids.filter((id) => id !== tree.root_node_id && !(childrenByParent[id]?.length) && !feeding.has(id));
  const closed = ends.length > 0 && ends.every((id) => nodesById[id]!.resolved);
  const cold = now - Date.parse(lastActive) > COLD_DAYS * 86_400_000;

  return { sketch: { box, cards, strings }, cards: ids.length, lastActive, status: closed ? "closed" : cold ? "cold" : "open" };
}

/** When a case was last worked on, the way a note on a file says it: today, yesterday, 4 days ago, Nov 1. */
export function lastWorked(iso: string, now = Date.now()) {
  const days = Math.floor((now - Date.parse(iso)) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** 1 or -1, fixed per id: which way a card tilts. */
export function tiltOf(id: string) {
  return hashOf(id) & 1 ? 1 : -1;
}

/** How a card hangs on the board, fixed by its id: tipped its tilt's way by
 * 0.6–2°, and pinned up to 4px off the row. */
export function leanOf(id: string) {
  const h = hashOf(id);
  return { rotate: tiltOf(id) * (0.6 + (((h >>> 1) & 7) / 7) * 1.4), y: ((h >>> 4) & 7) - 4 };
}

function hashOf(id: string) {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) | 0;
  return h;
}
