/**
 * Where each mind-map node sits, derived from tree shape alone.
 *
 * Positions are never stored (ARCHITECTURE.md §7.3): a stored x/y is a second
 * source of truth that drifts from the real tree. This runs on every structure
 * change instead, which is cheap -- it is one walk of the tree. The map and the
 * dashboard's card previews both use it, so it lives in the foundation.
 *
 * The algorithm is a simple tidy tree: leaves take consecutive columns left to
 * right in fork_index order, and each parent sits centred over its first and
 * last child. Depth decides the row, unless `rows` pushes a node further down
 * (a merged card sits below the deepest card it joins: toFlow.ts); its subtree
 * moves down with it. Pure: no React, no store, no DOM.
 */

import type { NodeMeta } from "@/api/types";

export interface Point {
  x: number;
  y: number;
}

/** Horizontal distance between neighbouring leaf columns, in flow units (px at zoom 1): a 17rem card and ~70px of board between neighbours. */
export const COLUMN_WIDTH = 340;
/** Vertical distance between generations (Figma had ~220; more room for the strings to read as a tree). */
export const ROW_HEIGHT = 240;

/**
 * @param rootId           the tree's root, or null for an empty tree
 * @param childrenByParent child ids per parent, already ordered by fork_index
 * @param rows             the row to draw a node on in place of its depth, for the nodes that need one
 * @returns the top-centre point of every node reachable from the root
 */
export function layoutTree(
  rootId: string | null,
  childrenByParent: Record<string, string[]>,
  rows: Record<string, number> = {},
): Record<string, Point> {
  const out: Record<string, Point> = {};
  if (!rootId) return out;

  let nextColumn = 0;
  const seen = new Set<string>();

  // Returns the node's x. Recursion depth = tree depth, which is fine for
  // conversation trees; the `seen` guard stops corrupt (cyclic) data looping.
  const place = (id: string, parentRow: number): number => {
    seen.add(id);
    const depth = rows[id] ?? parentRow + 1;
    const children = (childrenByParent[id] ?? []).filter((c) => !seen.has(c));
    let x: number;
    if (children.length === 0) {
      x = nextColumn++ * COLUMN_WIDTH;
    } else {
      const xs = children.map((c) => place(c, depth));
      x = (xs[0]! + xs[xs.length - 1]!) / 2;
    }
    out[id] = { x, y: depth * ROW_HEIGHT };
    return x;
  };

  place(rootId, -1);
  return out;
}

/** What a case's drawing needs: its root, its cards, and each card's children in fork_index order. */
export type CaseShape = { rootId: string | null; nodesById: Record<string, NodeMeta>; childrenByParent: Record<string, string[]> };

/** The merged cards whose sources are on the map, each with those sources. */
function mergesOf(s: CaseShape): Map<string, string[]> {
  const out = new Map<string, string[]>();
  for (const n of Object.values(s.nodesById)) {
    const sources = (n.merge_source_ids ?? []).filter((id) => s.nodesById[id]);
    if (sources.length) out.set(n.id, sources);
  }
  return out;
}

/** How merged cards are drawn: each hangs under its shallowest source, so it sits in that source's column
 * (ties: its first parent), and one row below its deepest, so it reads as coming after everything it joins.
 * Its own branches hang under it as usual. Only the drawing moves; `parent_id` is untouched. */
function drawnTree(s: CaseShape, merges: Map<string, string[]>) {
  const rows: Record<string, number> = {};
  if (!merges.size) return { children: s.childrenByParent, rows };
  const depths = new Map<string, number>();
  const depth = (id: string): number => {
    const known = depths.get(id);
    if (known !== undefined) return known;
    depths.set(id, 0); // cycle guard: corrupt data mustn't recurse forever
    const sources = merges.get(id);
    const parent = s.nodesById[id]?.parent_id;
    const d = sources ? 1 + Math.max(...sources.map(depth)) : parent ? 1 + depth(parent) : 0;
    depths.set(id, d);
    return d;
  };
  const children = { ...s.childrenByParent };
  for (const [id, sources] of merges) {
    const parent = s.nodesById[id]!.parent_id;
    const under = sources.reduce((a, b) => (depth(b) < depth(a) ? b : a));
    rows[id] = depth(id);
    if (under === parent) continue;
    if (parent) children[parent] = (children[parent] ?? []).filter((c) => c !== id);
    children[under] = [...(children[under] ?? []), id];
  }
  return { children, rows };
}

/** Where every card of a case sits, merged cards included (each below everything it joins), and which cards each
 * merge joins. The map draws from this, and so does a case's photo on the dashboard, so the two always agree. */
export function caseLayout(s: CaseShape): { positions: Record<string, Point>; merges: Map<string, string[]> } {
  const merges = mergesOf(s);
  const drawn = drawnTree(s, merges);
  return { positions: layoutTree(s.rootId, drawn.children, drawn.rows), merges };
}
