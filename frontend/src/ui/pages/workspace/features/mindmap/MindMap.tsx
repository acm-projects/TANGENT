"use client";

import { Background, BackgroundVariant, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/base.css";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { useEffect, useMemo, useState } from "react";
import { apiErrorMessage } from "@/api";
import { useShallow } from "zustand/react/shallow";
import { selectThread, useTreeStore } from "@/store/treeStore";
import { Frame, Loading, Panel, Text } from "@/ui/library";
import { spring } from "@/ui/library/tokens/motion";
import { MapProject, Merge, MindMapNode, ReportMapError, StaggerPinIn } from "./components/MindMapNode";
import { mergeNodes } from "./nodeActions";
import { StringEdge } from "./components/StringEdge";
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
const edgeTypes = { string: StringEdge };

/** Marks the strings of `id`'s thread up to the root, through both branches of a merge (MindMap.css [data-traced]); null clears them. */
function traceThread(from: Element, id: string | null) {
  const map = from.closest(".mindmap");
  map?.querySelectorAll("[data-traced]").forEach((el) => el.removeAttribute("data-traced"));
  if (!map || !id) return;
  const thread = selectThread(useTreeStore.getState(), id);
  map.querySelectorAll(".react-flow__edge").forEach((edge) => {
    const [source, target] = (edge.getAttribute("data-id") ?? "").split("->");
    if (thread.has(source!) && thread.has(target!)) edge.setAttribute("data-traced", "");
  });
}

type MindMapProps = { slug: string; projectId: string; className?: string };

export function MindMap({ slug, projectId, className }: MindMapProps) {
  const project = useMemo(() => ({ slug, projectId }), [slug, projectId]);
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
  const projectName = useTreeStore((s) => s.project?.project_name);
  const { nodes, edges } = useMemo(() => toFlow(structure), [structure]);
  const [stagger, setStagger] = useState(true);
  const [actionError, setActionError] = useState<string | null>(null);
  // A failed action's reason is read once, not kept: it lifts off after a few seconds (a new one restarts the wait).
  useEffect(() => {
    if (!actionError) return;
    const t = setTimeout(() => setActionError(null), 5000);
    return () => clearTimeout(t);
  }, [actionError]);
  // A merge from the tray waits for a second card: the next card clicked joins it, the board or Escape cancels.
  const [mergeFrom, setMergeFrom] = useState<string | null>(null);
  useEffect(() => {
    if (!mergeFrom) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMergeFrom(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mergeFrom]);
  const merge = useMemo(
    () => ({
      from: mergeFrom,
      start: setMergeFrom,
      run(a: string, b: string) {
        setActionError(null);
        // the reasons it can't merge are plain Errors with a message to show; server refusals come through apiErrorMessage
        mergeNodes(a, b).catch((e: unknown) =>
          setActionError(e instanceof Error && !("isAxiosError" in e) ? e.message : apiErrorMessage(e, "Could not merge those cards.")),
        );
      },
    }),
    [mergeFrom],
  );

  useEffect(() => {
    if (load.status !== "ready") return;
    const t = setTimeout(() => setStagger(false), 1500);
    return () => clearTimeout(t);
  }, [load.status]);

  return (
    <Frame as="section" gap="0" className={["mindmap", className].filter(Boolean).join(" ")}
      // with a card picked, everything off its thread recedes (MindMap.css)
      data-focused={structure.activeNodeId ? true : undefined}
      data-merging={mergeFrom ? true : undefined}
      aria-label="Conversation map"
    >
      {load.status === "loading" && <Loading size="base" label="Loading map…" className="mindmap-status" />}
      {load.status === "error" && <Text role="alert" className="mindmap-status" content={load.message} />}
      <AnimatePresence>
        {actionError && (
          <motion.div
            key={actionError}
            className="mindmap-action-error"
            exit={{ opacity: 0, y: -12, scale: 0.96, transition: spring.lift }}
          >
            <Text role="alert" size="s" content={actionError} />
          </motion.div>
        )}
      </AnimatePresence>
      {mergeFrom && (
        <Text role="status" size="s" className="mindmap-merge-hint" content="Pick a card to merge with · Esc to cancel" />
      )}
      {load.status === "ready" && projectName && (
        // the case's label, pinned to the board's corner
        <Panel elevation="floating" className="mindmap-case-label">
          <Text as="span" size="xxs" className="mindmap-case-kicker" content="Case file" />
          <Text as="h1" size="l" hierarchy="primary" className="mindmap-case-name" content={projectName} />
        </Panel>
      )}
      {load.status === "ready" && (
        <MotionConfig reducedMotion="user">
        <StaggerPinIn value={stagger}>
        <ReportMapError value={setActionError}>
        <MapProject value={project}>
        <Merge value={merge}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          nodeOrigin={[0.5, 0]}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          // Selection lives in the tree store, not in React Flow. Having a node
          // handler also matters mechanically: without one React Flow turns
          // pointer events off on non-selectable, non-draggable nodes.
          onNodeClick={(_, node) => {
            if (!mergeFrom) return setActive(node.id);
            setMergeFrom(null);
            if (node.id !== mergeFrom) merge.run(mergeFrom, node.id);
          }}
          onPaneClick={() => (mergeFrom ? setMergeFrom(null) : setActive(null))}
          // Hovering a card traces its thread back to the case: the context a reply there would read.
          // Straight onto the DOM, so pointing around the board never re-renders the map.
          onNodeMouseEnter={(e, node) => traceThread(e.currentTarget, node.id)}
          onNodeMouseLeave={(e) => traceThread(e.currentTarget, null)}
          fitView
          // The chat panel covers the right half, so centre the tree in the left half.
          fitViewOptions={{ padding: { top: "20%", bottom: "20%", left: "8%", right: "52%" }, minZoom: 0.45, maxZoom: 1 }}
          minZoom={0.25}
          maxZoom={2}
          // MIT allows this; React Flow asks commercial users who hide it to subscribe to Pro.
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={16} size={1.5} patternClassName="mindmap-dots" />
        </ReactFlow>
        </Merge>
        </MapProject>
        </ReportMapError>
        </StaggerPinIn>
        </MotionConfig>
      )}
    </Frame>
  );
}
