import type { Edge, Node as FlowNode } from "@xyflow/react";
import type { AttachmentKind, NodeMeta } from "@/api/types";
import type { TreeState } from "@/store/treeStore";
import { selectBreadcrumb } from "@/store/treeStore";
import { layoutTree } from "./layout";

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
}

export type MindMapFlowNode = FlowNode<MindMapNodeData, "tangent">;

export type StructureSlice = Pick<TreeState, "rootId" | "nodesById" | "childrenByParent" | "activeNodeId">;

/** Shown for a node the summarizer hasn't titled yet (a fresh fork). */
export const UNTITLED = "New branch";

export function toFlow(s: StructureSlice): { nodes: MindMapFlowNode[]; edges: Edge[] } {
  const positions = layoutTree(s.rootId, s.childrenByParent);
  // The selected node and its ancestors are "on the path" -- the history the
  // chat panel shows. Everything else is dimmed.
  const path = new Set(s.activeNodeId ? selectBreadcrumb(s, s.activeNodeId).map((n) => n.id) : []);

  const stateOf = (id: string): MindMapNodeState =>
    id === s.activeNodeId ? "selected" : path.has(id) ? "path" : "default";

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
        title: meta.title ?? UNTITLED,
        state: stateOf(id),
        tags: meta.attachment_kinds ?? [],
        hasParent: meta.parent_id !== null,
        hasChildren: (s.childrenByParent[id]?.length ?? 0) > 0,
      },
    });
    if (meta.parent_id && positions[meta.parent_id]) {
      // An edge is on the path when both its ends are.
      const onPath = path.has(id) && path.has(meta.parent_id);
      edges.push({
        id: `${meta.parent_id}->${id}`,
        source: meta.parent_id,
        target: id,
        className: onPath ? "mindmap-edge mindmap-edge-path" : "mindmap-edge",
      });
    }
  }

  return { nodes, edges };
}
