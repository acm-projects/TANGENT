import type { NodeMeta, TreeResponse } from "@/api/types";
import { layoutTree } from "@/store/layout";

/* A project card's preview: its real tree, laid out by the map's own layout
 * (so it has the map's shape), shrunk into a 100 x 60 viewBox. The path from
 * the root to the newest node is strung in red: where the project left off.
 * Pure; drawn by CaseSketch. */

export type SketchPin = { x: number; y: number; parent: number | null; onPath: boolean };

export const SKETCH_W = 100;
export const SKETCH_H = 60;
const PAD = 8;

export function sketchTree({ tree, nodes }: TreeResponse): SketchPin[] {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const children: Record<string, string[]> = {};
  for (const n of [...nodes].sort((a, b) => a.fork_index - b.fork_index)) {
    if (n.parent_id) (children[n.parent_id] ??= []).push(n.id);
  }
  const at = layoutTree(tree.root_node_id, children);
  const ids = Object.keys(at);
  if (ids.length === 0) return [];

  const xs = ids.map((id) => at[id].x);
  const ys = ids.map((id) => at[id].y);
  const [minX, spanX] = [Math.min(...xs), Math.max(...xs) - Math.min(...xs)];
  const spanY = Math.max(...ys);
  // fit inside the padding without stretching; a tiny tree stays small instead of filling the frame
  const scale = Math.min((SKETCH_W - 2 * PAD) / (spanX || 1), (SKETCH_H - 2 * PAD) / (spanY || 1), 0.12);
  const offX = (SKETCH_W - spanX * scale) / 2;
  const offY = (SKETCH_H - spanY * scale) / 2;

  const newest = ids.map((id) => byId.get(id)!).reduce((a: NodeMeta, b) => (b.created_at > a.created_at ? b : a));
  const path = new Set<string>();
  for (let n: NodeMeta | undefined = newest; n; n = n.parent_id ? byId.get(n.parent_id) : undefined) path.add(n.id);

  const index = new Map(ids.map((id, i) => [id, i]));
  return ids.map((id) => {
    const parent = byId.get(id)!.parent_id;
    return {
      x: offX + (at[id].x - minX) * scale,
      y: offY + at[id].y * scale,
      parent: parent && index.has(parent) ? index.get(parent)! : null,
      onPath: path.has(id),
    };
  });
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
