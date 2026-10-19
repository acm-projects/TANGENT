"use client";

import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, Frame } from "@/ui/library";
import { spring } from "@/ui/library/tokens/motion";
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
 * chevron closes it. Panels swing out from the rail and tuck back into it;
 * More's tiles pop up out of it one by one and drop back in reverse. */

type Panel = "sources" | "share" | null;
type ToolbarProps = { slug: string; projectId: string; className?: string };

/* TODO(design): Add, History and Settings have no designs behind them yet.
 * They render as in Figma but disabled, so they don't look like broken buttons. */
const notDesignedYet = { disabled: true, onClick: () => {} };

const tucked = { opacity: 0, y: 24, scale: 0.5 };
const group = {
  tucked: { transition: { staggerChildren: 0.04, staggerDirection: -1, when: "afterChildren" } },
  shown: { transition: { staggerChildren: 0.06 } },
} as const;
const tile = { tucked: { ...tucked, transition: spring.lift }, shown: { opacity: 1, y: 0, scale: 1, transition: spring.pin } };

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

  const more = moreOpen
    ? [
        <Tile key="history" icon="history" label="History (not available yet)" {...notDesignedYet} />,
        <Tile key="settings" icon="settings" label="Settings (not available yet)" {...notDesignedYet} />,
        <Tile key="fewer" icon="expand_more" label="Fewer tools" onClick={() => setMoreOpen(false)} />,
      ]
    : [<Tile key="more" icon="more_vert" label="More tools" onClick={() => setMoreOpen(true)} />];

  return (
    <MotionConfig reducedMotion="user">
    <Frame direction="row" gap="2" className={["toolbar", className].filter(Boolean).join(" ")}>
      <Frame as="nav" justify="between" align="center" aria-label="Workspace tools" className="toolbar-rail">
        <Frame gap="2">
          <Tile icon="home" label="Dashboard" onClick={() => router.push(`/${slug}/dashboard`)} />
          <Tile icon="add_box" label="Add (not available yet)" {...notDesignedYet} />
          <Tile icon="folder" label="Sources" pressed={open === "sources"} onClick={() => toggle("sources")} />
        </Frame>

        <Frame gap="2">
          <Tile icon="ios_share" label="Share" pressed={open === "share"} onClick={() => toggle("share")} />
          <AnimatePresence mode="wait" initial={false}>
            <motion.div key={String(moreOpen)} className="toolbar-group" variants={group} initial="tucked" animate="shown" exit="tucked">
              {more.map((t) => (
                <motion.div key={t.key} variants={tile}>
                  {t}
                </motion.div>
              ))}
            </motion.div>
          </AnimatePresence>
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
            {open === "sources" && <SourcesPanel projectId={projectId} onClose={() => setOpen(null)} />}
            {open === "share" && <SharePanel slug={slug} projectId={projectId} onClose={() => setOpen(null)} />}
          </motion.div>
        )}
      </AnimatePresence>
    </Frame>
    </MotionConfig>
  );
}

/* Figma "ToolBar Tile": a round icon-only button (Default / Hover / Open). */
function Tile({ icon, label, pressed, disabled, onClick }: { icon: string; label: string; pressed?: boolean; disabled?: boolean; onClick(): void }) {
  return (
    <Button
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
    />
  );
}
