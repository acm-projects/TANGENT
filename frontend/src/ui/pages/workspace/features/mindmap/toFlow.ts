import type { Edge, Node as FlowNode } from "@xyflow/react";
import type { AttachmentKind, NodeMeta } from "@/api/types";
import type { TreeState } from "@/store/treeStore";
import { selectExhibits, selectThread } from "@/store/treeStore";
import { layoutTree } from "@/store/layout";

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
  /** A merged card hangs below it (draw the outgoing dot). Not a child: deleting this card leaves the merge. */
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

/** The tree as it's drawn: a merged card is laid out under the deepest of its sources (the first, on a tie)
 * rather than under its real parent, so it sits below every card it joins and the join reads down the board.
 * Depth is the drawn one: a merged card is drawn deeper than its real depth, and so is everything under it. */
function drawnChildren(s: StructureSlice, merges: Map<string, string[]>): Record<string, string[]> {
  if (!merges.size) return s.childrenByParent;
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
  const out = { ...s.childrenByParent };
  for (const [id, sources] of merges) {
    const parent = s.nodesById[id]!.parent_id;
    const under = sources.reduce((a, b) => (depth(b) > depth(a) ? b : a));
    if (parent) out[parent] = (out[parent] ?? []).filter((c) => c !== id);
    out[under] = [...(out[under] ?? []), id];
  }
  return out;
}

export function toFlow(s: StructureSlice): { nodes: MindMapFlowNode[]; edges: Edge[] } {
  const merges = mergesOf(s);
  const positions = layoutTree(s.rootId, drawnChildren(s, merges));
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
        hasChildren: (s.childrenByParent[id]?.length ?? 0) > 0,
        exhibit: exhibits[id],
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
