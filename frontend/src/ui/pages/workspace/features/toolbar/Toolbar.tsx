"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, Frame } from "@/ui/library";
import { SharePanel } from "./components/SharePanel";
import { SourcesPanel } from "./components/SourcesPanel";
import "./Toolbar.css";

/* The floating tool rail on the workspace's left edge (Figma "Toolbar",
 * 126:1115, built from "ToolBar Tile", 18:140).
 *
 *   top:     Home · Add · Sources
 *   bottom:  Share · More (⋮)   -- More expands to Share · History · Settings · collapse
 *
 * Sources and Share open a panel beside the rail; Escape or the panel's own
 * chevron closes it. */

type Panel = "sources" | "share" | null;
type ToolbarProps = { slug: string; projectId: string; className?: string };

/* TODO(design): Add, History and Settings have no designs behind them yet.
 * They render as in Figma and do nothing until the designer specifies them. */
const notDesignedYet = () => {};

export function Toolbar({ slug, projectId, className }: ToolbarProps) {
  const router = useRouter();
  const [open, setOpen] = useState<Panel>(null);
  const [moreOpen, setMoreOpen] = useState(false);

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
    <Frame direction="row" gap="2" className={["toolbar", className].filter(Boolean).join(" ")}>
      <Frame as="nav" justify="between" align="center" aria-label="Workspace tools" className="toolbar-rail">
        <Frame gap="2">
          <Tile icon="home" label="Dashboard" onClick={() => router.push(`/${slug}/dashboard`)} />
          <Tile icon="add_box" label="Add" onClick={notDesignedYet} />
          <Tile icon="folder" label="Sources" pressed={open === "sources"} onClick={() => toggle("sources")} />
        </Frame>

        <Frame gap="2">
          <Tile icon="ios_share" label="Share" pressed={open === "share"} onClick={() => toggle("share")} />
          {moreOpen ? (
            <>
              <Tile icon="history" label="History" onClick={notDesignedYet} />
              <Tile icon="settings" label="Settings" onClick={notDesignedYet} />
              <Tile icon="expand_more" label="Fewer tools" onClick={() => setMoreOpen(false)} />
            </>
          ) : (
            <Tile icon="more_vert" label="More tools" onClick={() => setMoreOpen(true)} />
          )}
        </Frame>
      </Frame>

      {open === "sources" && <SourcesPanel projectId={projectId} onClose={() => setOpen(null)} />}
      {open === "share" && <SharePanel projectId={projectId} onClose={() => setOpen(null)} />}
    </Frame>
  );
}

/* Figma "ToolBar Tile": a round icon-only button (Default / Hover / Open). */
function Tile({ icon, label, pressed, onClick }: { icon: string; label: string; pressed?: boolean; onClick(): void }) {
  return (
    <Button
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
    />
  );
}
