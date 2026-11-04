import type { Edge, Node as FlowNode } from "@xyflow/react";
import type { AttachmentKind, NodeMeta } from "@/api/types";
import type { TreeState } from "@/store/treeStore";
import { selectExhibits, selectThread } from "@/store/treeStore";
import { layoutTree, type Point } from "@/store/layout";

/**
 * The ReactFlow adapter: tree structure in, React Flow nodes and edges out.
 * (Listed as a blocking open item in DEVELOPMENT.md §6.)
 *
 * It reads ONLY the store's structure slice. A streamed chat token touches the
 * content slice, so it never reaches here and never re-renders the map
 * (ARCHITECTURE.md §7.2). Pure, so it is unit-tested without React.
 */

/** How a node is drawn. Figma "Node" variants: Default / Path / Selected (Hover is CSS). */
export type MindMapNodeState = "default" | "path" | "selected";

export interface MindMapNodeData extends Record<string, unknown> {
  title: string;
  state: MindMapNodeState;
  tags: AttachmentKind[];
  /** Draw the incoming-edge dot on top (every node but the root). */
  hasParent: boolean;
  /** Draw the outgoing-edge dot underneath (every node but a leaf). */
  hasChildren: boolean;
  /** Its place in the case, outline-numbered like exhibits: "1", "1.2", "1.2.1". */
  exhibit: string;
  /** The parent exhibit labels for a joint exhibit. */
  subtitle: string | null;
  /** This card is a parent of a merge (draw the outgoing dot). */
  feedsMerge: boolean;
  tokens: number;
  /** A debate's verdict card (node_type "debate"). */
  debate: boolean;
}

export type MindMapFlowNode = FlowNode<MindMapNodeData, "tangent">;

export type StructureSlice = Pick<TreeState, "rootId" | "nodesById" | "childrenByParent" | "activeNodeId">;

/** Shown for a node the summarizer hasn't titled yet (a fresh fork). */
export const UNTITLED = "New branch";
/** ...and for a merged node, until the same happens. */
export const UNTITLED_MERGE = "Merged branches";

/** The merged cards whose sources are on the map, each with those sources. */
function mergesOf(s: StructureSlice): Map<string, string[]> {
  const out = new Map<string, string[]>();
  for (const n of Object.values(s.nodesById)) {
    const sources = (n.merge_source_ids ?? []).filter((id) => s.nodesById[id]);
    if (sources.length) out.set(n.id, sources);
  }
  return out;
}

/** How merged cards are drawn: one row below the deepest card each joins, so it reads as coming after
 * everything it joins, and (centreMerges) centred between them. For the layout it hangs under its shallowest
 * source (ties: its first parent), which keeps a column for its own branches. Only the drawing moves;
 * `parent_id` is untouched. */
function drawnTree(s: StructureSlice, merges: Map<string, string[]>) {
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

/** Slide each merged card, and the branches under it, to the middle of its sources: halfway between the
 * leftmost and the rightmost, however many it joins. Shallowest merges first, so a merge of merges centres
 * on where they ended up.
 * shortcut: a card between the sources on the merge's row isn't moved aside, so the two can overlap; spread
 * the row if that turns up in real trees. */
function centreMerges(
  positions: Record<string, Point>,
  children: Record<string, string[]>,
  merges: Map<string, string[]>,
  rows: Record<string, number>,
) {
  for (const id of [...merges.keys()].sort((a, b) => rows[a]! - rows[b]!)) {
    const xs = merges.get(id)!.flatMap((source) => (positions[source] ? [positions[source].x] : []));
    if (!positions[id] || !xs.length) continue;
    const dx = (Math.min(...xs) + Math.max(...xs)) / 2 - positions[id].x;
    const seen = new Set<string>();
    const shift = (n: string) => {
      if (seen.has(n) || !positions[n]) return;
      seen.add(n);
      positions[n] = { ...positions[n], x: positions[n].x + dx };
      children[n]?.forEach(shift);
    };
    shift(id);
  }
}

export function toFlow(s: StructureSlice): { nodes: MindMapFlowNode[]; edges: Edge[] } {
  const merges = mergesOf(s);
  const drawn = drawnTree(s, merges);
  const positions = layoutTree(s.rootId, drawn.children, drawn.rows);
  centreMerges(positions, drawn.children, merges, drawn.rows);
  const feeding = new Set([...merges.values()].flat());
  // The selected node and its ancestors are "on the path" -- the history the
  // chat panel shows. Everything else is dimmed.
  // (through a merged node, both branches it merged: selectThread)
  const path = s.activeNodeId ? selectThread(s, s.activeNodeId) : new Set<string>();

  const stateOf = (id: string): MindMapNodeState =>
    id === s.activeNodeId ? "selected" : path.has(id) ? "path" : "default";

  const exhibits = selectExhibits(s);

  const nodes: MindMapFlowNode[] = [];
  const edges: Edge[] = [];

  for (const [id, position] of Object.entries(positions)) {
    const meta: NodeMeta | undefined = s.nodesById[id];
    if (!meta) continue;
    nodes.push({
      id,
      type: "tangent",
      position,
      data: {
        title: meta.title ?? (merges.has(id) ? UNTITLED_MERGE : UNTITLED),
        state: stateOf(id),
        tags: meta.attachment_kinds ?? [],
        hasParent: meta.parent_id !== null,
        hasChildren: (s.childrenByParent[id]?.length ?? 0) > 0 || feeding.has(id),
        exhibit: exhibits[id],
        subtitle: merges.has(id) ? merges.get(id)!.map((source) => exhibits[source]).filter(Boolean).join(" + ") : null,
        feedsMerge: feeding.has(id),
        tokens: meta.tokens,
        debate: meta.node_type === "debate",
      },
    });
    const sources = merges.get(id);
    if (sources) {
      // a merged card's strings come from both its sources, not from where they parted; red while it's on the path
      for (const source of sources) {
        edges.push({
          id: `${source}->${id}`,
          source,
          target: id,
          type: "string",
          className: path.has(id) ? "mindmap-edge mindmap-edge-merge mindmap-edge-path" : "mindmap-edge mindmap-edge-merge",
        });
      }
    } else if (meta.parent_id && positions[meta.parent_id]) {
      // An edge is on the path when both its ends are.
      const onPath = path.has(id) && path.has(meta.parent_id);
      edges.push({
        id: `${meta.parent_id}->${id}`,
        source: meta.parent_id,
        target: id,
        type: "string",
        className: onPath ? "mindmap-edge mindmap-edge-path" : "mindmap-edge",
      });
    }
  }

  // SVG paints in document order: path edges last, so red always crosses over grey.
  const onPath = (e: Edge) => Number(e.className?.includes("mindmap-edge-path") ?? false);
  edges.sort((a, b) => onPath(a) - onPath(b));
  return { nodes, edges };
}
