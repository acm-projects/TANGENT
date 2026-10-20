"use client";

import { motion } from "motion/react";
import { useState, type FormEvent } from "react";
import { apiErrorMessage } from "@/api";
import type { ProjectSummary, WorkspaceSummary } from "@/api/types";
import { Frame, Icon, Input, Panel, Text } from "@/ui/library";
import { spring } from "@/ui/library/tokens/motion";
import { CardFace } from "./CardFace";

/* The row of folders along the bottom of the screen, one per workspace, plus a
 * dashed one for a new workspace. A folder holds its project cards between its
 * back and its front flap. Hovering (or focusing) it lifts it, drops its flap
 * open and fans its top three cards up out of it. Clicking it opens it: its cards leave for the grid
 * (they share layoutIds with ProjectCard, so Motion flies them), and the open
 * folder sits out with its flap dipped and a red pin on its tab. */

/** shortcut: a folder holds its newest 12 cards; the rest drop into the grid instead of flying. Raise it if folders get big. */
export const FOLDER_CARDS = 12;

// The three cards that peek out on hover: front one leaning left, then right, then upright behind.
const FAN = [
  { x: "-38%", y: "-58%", rotate: -9 },
  { x: "36%", y: "-50%", rotate: 8 },
  { x: "0%", y: "-66%", rotate: -1 },
];

type FolderDrawerProps = {
  workspaces: WorkspaceSummary[];
  projectsBySlug: Map<string, ProjectSummary[]>;
  /** The folder whose cards are out on the grid; null while the board first lands. */
  openSlug: string | null;
  onOpen(slug: string): void;
  onCreate(name: string): Promise<void>;
};

export function FolderDrawer({ workspaces, projectsBySlug, openSlug, onOpen, onCreate }: FolderDrawerProps) {
  return (
    <Frame as="nav" gap="0" className="drawer" aria-label="Workspaces">
      <Frame as="ol" direction="row" align="end" gap="6" className="drawer-row">
        {workspaces.map((w) => (
          <Folder
            key={w.workspace_id}
            workspace={w}
            projects={projectsBySlug.get(w.workspace_slug) ?? []}
            open={w.workspace_slug === openSlug}
            onOpen={() => onOpen(w.workspace_slug)}
          />
        ))}
        <NewFolder onCreate={onCreate} />
      </Frame>
    </Frame>
  );
}

type FolderProps = { workspace: WorkspaceSummary; projects: ProjectSummary[]; open: boolean; onOpen(): void };

function Folder({ workspace, projects, open, onOpen }: FolderProps) {
  const [hover, setHover] = useState(false);
  const cards = open ? [] : projects.slice(0, FOLDER_CARDS);
  const count = projects.length;

  return (
    <motion.li
      className="folder"
      data-open={open || undefined}
      style={{ zIndex: hover ? 2 : 1 }}
      animate={{ y: open ? "-30%" : hover ? "-20%" : "0%" }}
      transition={spring.lift}
      onPointerEnter={() => setHover(true)}
      onPointerLeave={() => setHover(false)}
      onFocus={() => setHover(true)}
      onBlur={() => setHover(false)}
      // The button below is for keyboards; a mouse may press anywhere, the peeking cards included.
      onClick={onOpen}
    >
      <span className="folder-back" aria-hidden="true">
        <span className="folder-tab">
          {open && <span className="folder-tab-pin" />}
          <Text as="span" size="s" className="folder-tab-name" content={workspace.workspace_name} />
          {/* keyed, so a new or deleted project bumps the count */}
          <Text key={count} as="span" size="xxs" className="folder-tab-count" content={String(count)} />
        </span>
      </span>
      <span className="folder-stack" aria-hidden="true">
        {cards.map((p, i) => {
          const peek = hover && i < FAN.length;
          return (
            <motion.span
              key={p.id}
              layoutId={`card-${p.id}`}
              className="folder-card"
              style={{ zIndex: cards.length - i }}
              animate={peek ? FAN[i] : { x: "0%", y: "0%", rotate: i % 2 ? 2 : -2 }}
              transition={{ ...spring.pin, delay: hover ? i * 0.06 : 0, layout: { ...spring.fly, delay: i * 0.035 } }}
            >
              <CardFace project={p} />
            </motion.span>
          );
        })}
      </span>
      <span className="folder-front" aria-hidden="true" />
      <button
        type="button"
        className="folder-hit"
        aria-current={open ? "page" : undefined}
        aria-label={`${workspace.workspace_name}, ${count} ${count === 1 ? "project" : "projects"}`}
      />
    </motion.li>
  );
}

/** The dashed folder at the end of the row. Pressing it puts a name field on it; Enter makes the workspace. */
function NewFolder({ onCreate }: { onCreate(name: string): Promise<void> }) {
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setError(null);
    try {
      await onCreate(trimmed);
      setNaming(false);
      setName("");
    } catch (err: unknown) {
      setError(apiErrorMessage(err, "Could not create the workspace."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <motion.li
      className="folder folder-new"
      initial={false}
      animate={{ y: naming ? "-30%" : "0%" }}
      whileHover={{ y: "-20%" }}
      transition={spring.lift}
    >
      <span className="folder-back" aria-hidden="true" />
      {naming ? (
        <Frame as="form" gap="0" className="folder-new-form" onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && setNaming(false)}>
          <Panel className="folder-new-field">
            <Input
              aria-label="New workspace name"
              placeholder="Workspace name"
              value={name}
              maxLength={100}
              disabled={busy}
              autoFocus
              onChange={(e) => setName(e.target.value)}
              onBlur={() => !name.trim() && setNaming(false)}
            />
          </Panel>
          {error && <Text role="alert" size="xxs" className="folder-new-error" content={error} />}
        </Frame>
      ) : (
        <button type="button" className="folder-hit" aria-label="New workspace" onClick={() => setNaming(true)}>
          <Icon icon="create_new_folder" size="xl" className="folder-new-icon" />
        </button>
      )}
    </motion.li>
  );
}
