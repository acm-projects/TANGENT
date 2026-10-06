"use client";

import { Background, BackgroundVariant, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/base.css";
import { useMemo } from "react";
import { useShallow } from "zustand/react/shallow";
import { useTreeStore } from "@/store/treeStore";
import { Frame, Text } from "@/ui/library";
import { MindMapNode } from "./components/MindMapNode";
import { toFlow } from "./toFlow";
import { useMindMap } from "./useMindMap";
import "./MindMap.css";

/* The conversation tree as a pannable, zoomable graph (Figma "NodeGraph").
 * Clicking a node selects it; the chat panel follows the selection.
 *
 * Layout is derived (layout.ts), so nodes can't be dragged -- a dragged
 * position would have to be stored, and stored positions drift (§7.3). */

// Module-level: React Flow re-mounts every node if this object changes identity.
const nodeTypes = { tangent: MindMapNode };

type MindMapProps = { projectId: string; className?: string };

export function MindMap({ projectId, className }: MindMapProps) {
  const load = useMindMap(projectId);
  // Structure slice only -- streamed tokens never re-render the map.
  const structure = useTreeStore(
    useShallow((s) => ({
      rootId: s.rootId,
      nodesById: s.nodesById,
      childrenByParent: s.childrenByParent,
      activeNodeId: s.activeNodeId,
    })),
  );
  const setActive = useTreeStore((s) => s.setActive);
  const { nodes, edges } = useMemo(() => toFlow(structure), [structure]);

  return (
    <Frame as="section" gap="0" className={["mindmap", className].filter(Boolean).join(" ")} aria-label="Conversation map">
      {load.status === "loading" && <Text hierarchy="tertiary" className="mindmap-status" content="Loading map…" />}
      {load.status === "error" && <Text role="alert" className="mindmap-status" content={load.message} />}
      {load.status === "ready" && (
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          nodeOrigin={[0.5, 0]}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          // Selection lives in the tree store, not in React Flow. Having a node
          // handler also matters mechanically: without one React Flow turns
          // pointer events off on non-selectable, non-draggable nodes.
          onNodeClick={(_, node) => setActive(node.id)}
          onPaneClick={() => setActive(null)}
          fitView
          // The chat panel covers the right half, so centre the tree in the left half.
          fitViewOptions={{ padding: { top: "20%", bottom: "20%", left: "6%", right: "52%" }, minZoom: 0.6, maxZoom: 1 }}
          minZoom={0.25}
          maxZoom={2}
        >
          <Background variant={BackgroundVariant.Dots} gap={16} size={1.5} patternClassName="mindmap-dots" />
        </ReactFlow>
      )}
    </Frame>
  );
}
