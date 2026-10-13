/**
 * Where each mind-map node sits, derived from tree shape alone.
 *
 * Positions are never stored (ARCHITECTURE.md §7.3): a stored x/y is a second
 * source of truth that drifts from the real tree. This runs on every structure
 * change instead, which is cheap -- it is one walk of the tree.
 *
 * The algorithm is a simple tidy tree: leaves take consecutive columns left to
 * right in fork_index order, and each parent sits centred over its first and
 * last child. Depth decides the row. Pure: no React, no store, no DOM.
 */

export interface Point {
  x: number;
  y: number;
}

/** Horizontal distance between neighbouring leaf columns, in flow units (px at zoom 1). */
export const COLUMN_WIDTH = 300;
/** Vertical distance between generations. Figma: ~220px from parent to child. */
export const ROW_HEIGHT = 220;

/**
 * @param rootId           the tree's root, or null for an empty tree
 * @param childrenByParent child ids per parent, already ordered by fork_index
 * @returns the top-centre point of every node reachable from the root
 */
export function layoutTree(rootId: string | null, childrenByParent: Record<string, string[]>): Record<string, Point> {
  const out: Record<string, Point> = {};
  if (!rootId) return out;

  let nextColumn = 0;
  const seen = new Set<string>();

  // Returns the node's x. Recursion depth = tree depth, which is fine for
  // conversation trees; the `seen` guard stops corrupt (cyclic) data looping.
  const place = (id: string, depth: number): number => {
    seen.add(id);
    const children = (childrenByParent[id] ?? []).filter((c) => !seen.has(c));
    let x: number;
    if (children.length === 0) {
      x = nextColumn++ * COLUMN_WIDTH;
    } else {
      const xs = children.map((c) => place(c, depth + 1));
      x = (xs[0]! + xs[xs.length - 1]!) / 2;
    }
    out[id] = { x, y: depth * ROW_HEIGHT };
    return x;
  };

  place(rootId, 0);
  return out;
}
