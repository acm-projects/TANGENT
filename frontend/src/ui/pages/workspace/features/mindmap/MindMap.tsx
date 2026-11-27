"use client";

import { ReactFlow, useReactFlow, type Viewport } from "@xyflow/react";
import "@xyflow/react/dist/base.css";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { apiErrorMessage, OFFLINE } from "@/api";
import { useShallow } from "zustand/react/shallow";
import { selectThread, useTreeStore } from "@/store/treeStore";
import { Button, Frame, Link, Loading, Panel, Text } from "@/ui/library";
import { glideMs, spring } from "@/ui/library/tokens/motion";
import { MapProject, Merge, MindMapNode, ReportMapError, StaggerPinIn } from "./components/MindMapNode";
import { mergeNodes, putCardBack } from "./nodeActions";
import { fileNumber } from "@/ui/features/case-file/fileNumber";
import { StringEdge } from "./components/StringEdge";
import { toFlow } from "./toFlow";
import { useMindMap } from "./useMindMap";
import "./MindMap.css";

/* The conversation tree as a pannable, zoomable graph (Figma "NodeGraph").
 * Clicking a node selects it; the chat panel follows the selection.
 *
 * Layout is derived (layout.ts), so nodes can't be dragged -- a dragged
 * position would have to be stored, and stored positions drift (§7.3). */

// Where the tree starts on the board: with a card picked the chat sheet covers the right ~40%; with none, the
// sheet is off the board and the tree centres in the whole of it (clear of the rail).
const VIEW_PADDING = { top: "20%", bottom: "20%", left: "8%", right: "40%" } as const;
const OPEN_PADDING = { top: "14%", bottom: "18%", left: "10%", right: "6%" } as const;
/** The gap the camera keeps between a card and anything covering the board, and the room kept under it for Gent's dock. */
const MARGIN = 48;
const DOCK_ROOM = 96;
/** A card's least size on the board, for one not measured yet, and the room its action tray takes under it. */
const CARD_MIN = { width: 200, height: 72 };
const TRAY_ROOM = 44;
/** The camera zooms out to bring search hits into the clear, but never past this: below it a card can't be read. */
const MIN_READABLE = 0.5;

type Box = { x: number; y: number; width: number; height: number };

/** The part of the board nothing covers, in the map pane's own pixels: right of the toolbar (and its open panel),
 * left of the chat sheet (when it's on the board), above Gent's dock. */
function clearArea(): Box | null {
  const pane = document.querySelector(".mindmap")?.getBoundingClientRect();
  if (!pane) return null;
  const tools = document.querySelector(".workspace-toolbar")?.getBoundingClientRect();
  const sheet = document.querySelector<HTMLElement>(".chat[data-layout='docked']");
  const left = (tools ? tools.right - pane.left : 0) + MARGIN;
  // the sheet may still be sliding in: its width is already final, so measure that, not where it is now
  const right = pane.width - (sheet ? sheet.offsetWidth + 16 : 0) - MARGIN;
  return { x: left, y: MARGIN, width: Math.max(0, right - left), height: Math.max(0, pane.height - MARGIN - DOCK_ROOM) };
}

/** Keeps what the user is looking for in the clear part of the board, gliding the camera only when it has to:
 *  - a picked card the sheet would cover is moved back into the open, at the same zoom;
 *  - search hits hidden under the search panel are brought out (zooming out a little if they don't fit);
 *  - a search result clicked (flyTo) is centred in the clear part, at a readable zoom. */
function Camera() {
  const active = useTreeStore((s) => s.activeNodeId);
  const hits = useTreeStore((s) => s.search?.ids);
  const flyTo = useTreeStore((s) => s.flyTo);
  const { getInternalNode, getNodesBounds, getViewport, setViewport } = useReactFlow();
  // Where the board was before the sheet pushed it aside, and where the camera put it: when the sheet leaves,
  // the board glides back the way it came, unless the user has moved it since (then it stays where they put it).
  const pushed = useRef<{ from: Viewport; to: Viewport } | null>(null);
  const same = (a: Viewport, b: Viewport) => Math.abs(a.x - b.x) < 2 && Math.abs(a.y - b.y) < 2 && Math.abs(a.zoom - b.zoom) < 0.01;

  useEffect(() => {
    if (active || !pushed.current) return;
    const { from, to } = pushed.current;
    pushed.current = null;
    if (same(getViewport(), to)) void setViewport(from, { duration: glideMs() });
  }, [active, getViewport, setViewport]);

  // a picked card, or the search's hits: moved into the clear only if they're out of it
  useEffect(() => {
    if (!active && !hits?.length) return;
    // a frame later: the sheet and panels have their final widths (they're only sliding)
    const raf = requestAnimationFrame(() => {
      const clear = clearArea();
      if (!clear) return;
      const { x, y, zoom } = getViewport();
      // An open card and the search's hits: all of them in the clear if they fit at a readable zoom (the board
      // zooms out for them, as for hits alone), else the card alone at this zoom
      let ids = active ? [active] : (hits ?? []);
      let fitAll = !active;
      if (active && hits?.length) {
        const both = getNodesBounds([active, ...hits]);
        if (Math.min(clear.width / both.width, (clear.height - TRAY_ROOM) / both.height) >= MIN_READABLE) {
          ids = [active, ...hits];
          fitAll = true;
        }
      }
      const measured = getNodesBounds(ids);
      // A card made a moment ago (a merge, a branch) may not be measured yet: its bounds are then a point, and
      // it would "fit" anywhere. Give it at least a card's size, and a picked card the room its tray takes below.
      const b = {
        ...measured,
        width: Math.max(measured.width, CARD_MIN.width),
        height: Math.max(measured.height, CARD_MIN.height) + (active ? TRAY_ROOM : 0),
      };
      // zoom out only for a set of hits that can't fit at this zoom, never past readable
      const z = fitAll ? Math.max(MIN_READABLE, Math.min(zoom, clear.width / b.width, clear.height / b.height)) : zoom;
      // a zoom change scales the board about the pane's corner; then it pans
      const ox = x * (z / zoom);
      const oy = y * (z / zoom);
      const box = { x: b.x * z + ox, y: b.y * z + oy, width: b.width * z, height: b.height * z };
      // how far to move a span so it lies in the room (centred if it's too big for it)
      const nudge = (start: number, size: number, from: number, room: number) =>
        size > room ? from + (room - size) / 2 - start : start < from ? from - start : start + size > from + room ? from + room - (start + size) : 0;
      const dx = nudge(box.x, box.width, clear.x, clear.width);
      const dy = nudge(box.y, box.height, clear.y, clear.height);
      if (!dx && !dy && z === zoom) return;
      const to = { x: ox + dx, y: oy + dy, zoom: z };
      if (active) {
        // keep the first "from" across a run of picks; a pan the user made in between starts a new run
        const run = pushed.current && same({ x, y, zoom }, pushed.current.to) ? pushed.current.from : { x, y, zoom };
        pushed.current = { from: run, to };
      }
      void setViewport(to, { duration: glideMs() });
    });
    return () => cancelAnimationFrame(raf);
  }, [active, hits, getNodesBounds, getViewport, setViewport]);

  // a search result clicked: centred in the clear part at a readable zoom. After the effect above, so it wins
  // when the click also picks the card; flyTo carries a stamp, so the same card asked for twice glides again.
  useEffect(() => {
    if (!flyTo) return;
    const raf = requestAnimationFrame(() => {
      const clear = clearArea();
      const node = getInternalNode(flyTo.id);
      if (!clear || !node) return;
      const z = Math.min(1, Math.max(getViewport().zoom, 0.8));
      const cx = node.internals.positionAbsolute.x + (node.measured.width ?? 0) / 2;
      const cy = node.internals.positionAbsolute.y + (node.measured.height ?? 0) / 2;
      void setViewport({ x: clear.x + clear.width / 2 - cx * z, y: clear.y + clear.height / 2 - cy * z, zoom: z }, { duration: glideMs(1.3) });
    });
    return () => cancelAnimationFrame(raf);
  }, [flyTo, getInternalNode, getViewport, setViewport]);
  return null;
}

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
  // the plate's number: the first four digits of the project's id, upper-cased, stable per case
  const caseNumber = useTreeStore((s) => fileNumber(s.project?.id ?? ""));
  const cardCount = Object.keys(structure.nodesById).length;
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
  // Escape puts the picked card back on the board (and the sheet slides away with it), the same as clicking the
  // board: the way out of the sheet. Not while typing, not while a merge or a dialog has Escape for itself.
  const picked = structure.activeNodeId !== null;
  useEffect(() => {
    if (!picked || mergeFrom) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      const t = e.target as HTMLElement | null;
      if (t?.closest("input, textarea, select, [contenteditable], dialog[open], [role='dialog'], [role='menu']")) return;
      if (document.querySelector("dialog[open]")) return;
      putCardBack();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [picked, mergeFrom]);
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
      {load.status === "error" && (
        // a case that's gone (deleted, or a wrong link): say so and offer the way back. No connection is not a
        // missing case: say that instead, and offer to try again
        <Frame gap="3" align="center" className="mindmap-status mindmap-missing">
          <Text role="alert" face="heading" size="l" content={load.message === OFFLINE ? "Could not reach the board." : load.message} />
          <Text
            size="s"
            hierarchy="tertiary"
            content={load.message === OFFLINE ? "Your case is safe. Check your connection and try again." : "It may have been deleted, or the link is wrong."}
          />
          {load.message === OFFLINE && <Button hierarchy="secondary" size="s" icon="refresh" showIcon label="Try again" onClick={() => window.location.reload()} />}
          <Link href={`/${slug}/dashboard`} className="mindmap-missing-back">
            <Text as="span" size="s" content="Back to your cases" />
          </Link>
        </Frame>
      )}
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
        // the case's name plate, riveted to the board's corner
        // Two lines and no more: which file this is, then its name in full. The board is the subject.
        <Panel material="leather" elevation="floating" className="mindmap-case-label">
          <Text
            as="span"
            face="stamp"
            size="xxs"
            className="mindmap-case-kicker"
            content={`Case file No. ${caseNumber} · ${cardCount} ${cardCount === 1 ? "card" : "cards"}`}
          />
          <Text as="h1" face="heading" size="m" hierarchy="primary" className="mindmap-case-name" content={projectName} />
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
          // strings aren't stops for the keyboard: Tab goes card to card
          edgesFocusable={false}
          // the card itself takes focus (MindMapNode); React Flow's wrapper round it would be a second stop
          nodesFocusable={false}
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
          // the sheet is only on the board with a card picked: centre the tree in what it leaves
          fitViewOptions={{ padding: structure.activeNodeId ? VIEW_PADDING : OPEN_PADDING, minZoom: 0.5, maxZoom: 1 }}
          minZoom={0.25}
          maxZoom={2}
          // MIT allows this; React Flow asks commercial users who hide it to subscribe to Pro.
          proOptions={{ hideAttribution: true }}
        >
          <Camera />
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
