"use client";

import { MotionConfig } from "motion/react";
import { useEffect, useState } from "react";
import { PACE_REST, setInkPace } from "@/ui/library/components/Ink/ink";
import { useChatLayout } from "@/store/chatLayout";
import { useGentStore } from "@/store/gentStore";
import { useTreeStore } from "@/store/treeStore";
import { api } from "@/api";
import { refreshTree } from "../mindmap/nodeActions";
import { Tile } from "../toolbar/Toolbar";
import { FieldNotes } from "./FieldNotes";
import { GentDock } from "./GentDock";
import { GentPresence } from "./travel/GentPresence";
import { setFlightCanvas } from "./travel/traveller";

/* Gent's layer over the board, between the toolbar and the chat: his dock at the bottom centre, the Field Notes
 * on the bottom right, and Gent himself wherever he is working (GentPresence). His flight and his off-screen arrow
 * are drawn in this layer too, so they pass over the board and the toolbar but under the chat. */

const TREE_REFRESH_MS = 5000;

export function GentLayer({ className }: { className?: string }) {
  const [layer, setLayer] = useState<HTMLDivElement | null>(null);
  // his ink barely moves at rest and flows at full speed while he works
  const busy = useGentStore((s) => s.busy);
  useEffect(() => setInkPace(busy ? 1 : PACE_REST), [busy]);
  // while he works, tell him which card the user picks (his selected() tool); a new task sends it anyway
  const selected = useTreeStore((s) => s.activeNodeId);
  const projectId = useGentStore((s) => s.projectId);
  useEffect(() => {
    if (busy && projectId) api.gent.select(projectId, selected).catch(() => {});
  }, [busy, projectId, selected]);
  // while he works, the map re-reads the tree every few seconds too, so no change of his waits for a reload
  useEffect(() => {
    if (!busy || !projectId) return;
    const timer = setInterval(() => void refreshTree(projectId).catch(() => {}), TREE_REFRESH_MS);
    return () => clearInterval(timer);
  }, [busy, projectId]);
  const chatCollapsed = useChatLayout((s) => s.layout === "collapsed");
  // his springs (the dock, his questions, the Field Notes) calm down for prefers-reduced-motion, as the map's do
  return (
    <MotionConfig reducedMotion="user">
    <div ref={setLayer} className={["gent-layer", className].filter(Boolean).join(" ")}>
      {/* the board's bottom-right corner: the Field Notes, and the folded chat's reopen tile beside them */}
      <div className="gent-layer-corner">
        <FieldNotes />
        {chatCollapsed && <Tile icon="chevron_left" label="Open chat" tip="left" onClick={() => useChatLayout.getState().setLayout("docked")} />}
      </div>
      <GentDock />
      <canvas ref={setFlightCanvas} className="gent-flight" aria-hidden />
      <GentPresence layer={layer} />
    </div>
    </MotionConfig>
  );
}
