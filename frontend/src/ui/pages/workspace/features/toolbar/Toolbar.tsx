"use client";

import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { useRouter } from "next/navigation";
import { useEffect, useState, type Ref } from "react";
import { SEARCH, useGentStation } from "@/store/gentStations";
import { Button, Frame, Panel } from "@/ui/library";
import { spring } from "@/ui/library/tokens/motion";
import { SearchPanel } from "./components/SearchPanel";
import { SettingsPanel } from "./components/SettingsPanel";
import { SharePanel } from "./components/SharePanel";
import { SourcesPanel } from "./components/SourcesPanel";
import "./Toolbar.css";

/* The floating tool rail on the workspace's left edge (Figma "Toolbar",
 * 126:1115, built from "ToolBar Tile", 18:140).
 *
 *   top:     Home · Search · Sources · groove
 *   bottom:  Share · Settings
 *
 * Search, Sources, Share and Settings open a panel beside the rail; Escape or the panel's own
 * chevron closes it. Panels swing out from the rail and tuck back into it. */

type Panel = "search" | "sources" | "share" | "settings" | null;
type ToolbarProps = { slug: string; projectId: string; className?: string };

export function Toolbar({ slug, projectId, className }: ToolbarProps) {
  const router = useRouter();
  const [open, setOpen] = useState<Panel>(null);
  // Gent visits the search tile while he searches the tree
  const searchStation = useGentStation<HTMLButtonElement>(SEARCH);

  const toggle = (panel: Exclude<Panel, null>) => setOpen((cur) => (cur === panel ? null : panel));

  // ⌘K / Ctrl+K opens Search from anywhere in the workspace, the way most apps do
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== "k" || !(e.metaKey || e.ctrlKey) || e.altKey || e.shiftKey) return;
      e.preventDefault();
      setOpen("search");
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!open) return;
    // on document, ahead of the map's window listener: Escape closes the panel and nothing else
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      e.preventDefault();
      setOpen(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <MotionConfig reducedMotion="user">
    <Frame direction="row" gap="2" className={["toolbar", className].filter(Boolean).join(" ")}>
      <Panel as="nav" material="leather" stitch={["right"]} round={["top-right", "bottom-right"]} aria-label="Workspace tools" className="toolbar-rail">
        <Frame gap="2" align="center">
          <Tile material="leather" icon="home" label="Dashboard" onClick={() => router.push(`/${slug}/dashboard`)} />
          <Tile material="leather" icon="search" label="Search" pressed={open === "search"} onClick={() => toggle("search")} station={searchStation} />
          <Tile material="leather" icon="folder" label="Sources" pressed={open === "sources"} onClick={() => toggle("sources")} />
          <div className="toolbar-groove" aria-hidden="true" />
        </Frame>

        <Frame gap="2" align="center">
          <Tile material="leather" icon="ios_share" label="Share" pressed={open === "share"} onClick={() => toggle("share")} />
          <Tile material="leather" icon="settings" label="Settings" pressed={open === "settings"} onClick={() => toggle("settings")} />
        </Frame>
      </Panel>

      <AnimatePresence mode="wait">
        {open && (
          <motion.div
            key={open}
            className="toolbar-slot"
            data-panel={open}
            initial={{ opacity: 0, x: -40, scale: 0.85, rotate: -3 }}
            animate={{ opacity: 1, x: 0, scale: 1, rotate: 0, transition: spring.pin }}
            exit={{ opacity: 0, x: -32, scale: 0.9, rotate: -2, transition: spring.lift }}
          >
            {open === "search" && <SearchPanel projectId={projectId} onClose={() => setOpen(null)} />}
            {open === "sources" && <SourcesPanel projectId={projectId} onClose={() => setOpen(null)} />}
            {open === "share" && <SharePanel slug={slug} projectId={projectId} onClose={() => setOpen(null)} />}
            {open === "settings" && <SettingsPanel slug={slug} onClose={() => setOpen(null)} />}
          </motion.div>
        )}
      </AnimatePresence>
    </Frame>
    </MotionConfig>
  );
}

/* Figma "ToolBar Tile": a round icon-only button (Default / Hover / Open). Also the folded Field Notes. */
export function Tile({ icon, label, pressed, disabled, onClick, station, tip = "right", material }: {
  icon: string; label: string; pressed?: boolean; disabled?: boolean; onClick(): void; station?: Ref<HTMLButtonElement>;
  /** leather when the tile sits in the rail; paper (default) when it floats on the board */
  material?: "paper" | "leather";
  /** which side its name tag slides out: left for tiles at the board's right edge, so the chat doesn't cover it */
  tip?: "left" | "right";
}) {
  return (
    <Button
      ref={station}
      disabled={disabled}
      material={material}
      elevation={material === "leather" ? "flat" : "floating"}
      size="base"
      icon={icon}
      label={label}
      title={label}
      showIcon
      showLabel={false}
      pressed={pressed}
      onClick={onClick}
      className="toolbar-tile"
      data-tip={tip}
    />
  );
}
