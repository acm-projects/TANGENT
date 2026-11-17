"use client";

import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { useRouter } from "next/navigation";
import { useEffect, useState, type Ref } from "react";
import { SEARCH, useGentStation } from "@/store/gentStations";
import { Button, Frame } from "@/ui/library";
import { spring } from "@/ui/library/tokens/motion";
import { SearchPanel } from "./components/SearchPanel";
import { SettingsPanel } from "./components/SettingsPanel";
import { SharePanel } from "./components/SharePanel";
import { SourcesPanel } from "./components/SourcesPanel";
import "./Toolbar.css";

/* The floating tool rail on the workspace's left edge (Figma "Toolbar",
 * 126:1115, built from "ToolBar Tile", 18:140).
 *
 *   top:     Home · Search · Sources
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

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <MotionConfig reducedMotion="user">
    <Frame direction="row" gap="2" className={["toolbar", className].filter(Boolean).join(" ")}>
      <Frame as="nav" justify="between" align="center" aria-label="Workspace tools" className="toolbar-rail">
        <Frame gap="2">
          <Tile icon="home" label="Dashboard" onClick={() => router.push(`/${slug}/dashboard`)} />
          <Tile icon="search" label="Search" pressed={open === "search"} onClick={() => toggle("search")} station={searchStation} />
          <Tile icon="folder" label="Sources" pressed={open === "sources"} onClick={() => toggle("sources")} />
        </Frame>

        <Frame gap="2">
          <Tile icon="ios_share" label="Share" pressed={open === "share"} onClick={() => toggle("share")} />
          <Tile icon="settings" label="Settings" pressed={open === "settings"} onClick={() => toggle("settings")} />
        </Frame>
      </Frame>

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
export function Tile({ icon, label, pressed, disabled, onClick, station, tip = "right" }: {
  icon: string; label: string; pressed?: boolean; disabled?: boolean; onClick(): void; station?: Ref<HTMLButtonElement>;
  /** which side its name tag slides out: left for tiles at the board's right edge, so the chat doesn't cover it */
  tip?: "left" | "right";
}) {
  return (
    <Button
      ref={station}
      disabled={disabled}
      elevation="floating"
      size="l"
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
