"use client";

import { LayoutGroup, motion, MotionConfig } from "motion/react";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { apiErrorMessage } from "@/api";
import { Button, Frame, Input, Panel, Text } from "@/ui/library";
import { spring } from "@/ui/library/tokens/motion";
import { FOLDER_CARDS, FolderDrawer } from "./components/FolderDrawer";
import { NewProjectTile } from "./components/NewProjectTile";
import { ProjectCard } from "./components/ProjectCard";
import { useBoard } from "./useBoard";
import { TreePreviews, type TreeCache } from "./useTreePreview";
import "./Board.css";

/* The dashboard board: the open workspace's name, its projects as cards in a
 * grid (the dashed + tile last), and the drawer of workspace folders along the
 * bottom. The board lands with every folder shut, then the open one empties
 * its cards out onto the grid, so even the first view shows where they live. */

type BoardProps = { slug: string };

export function Board({ slug }: BoardProps) {
  const board = useBoard(slug);
  const router = useRouter();
  const [landed, setLanded] = useState(false);
  const [trees] = useState<TreeCache>(() => new Map());
  const ready = board.state.status === "ready" ? board.state : null;

  useEffect(() => {
    if (!ready) return;
    const t = setTimeout(() => setLanded(true), 350);
    return () => clearTimeout(t);
  }, [ready]);

  const projects = board.projectsBySlug.get(board.activeSlug) ?? [];
  const title = board.workspace?.workspace_name ?? board.activeSlug;

  return (
    <MotionConfig reducedMotion="user">
      <TreePreviews value={trees}>
        <LayoutGroup>
          <Frame gap="6" className="board">
            <BoardTitle key={title} title={title} count={projects.length} canRename={Boolean(board.workspace)} onRename={board.renameWorkspace} />

            {board.state.status === "loading" && <Text hierarchy="tertiary" content="Loading…" />}
            {board.state.status === "error" && <Text role="alert" content={board.state.message} />}
            {ready && (
              <ol className="board-grid" aria-label={`Projects in ${title}`}>
                {landed &&
                  projects.map((p, i) => (
                    <motion.li key={p.id} layout="position" transition={spring.fly}>
                      <ProjectCard
                        project={p}
                        index={i}
                        dropIn={i >= FOLDER_CARDS}
                        slug={board.activeSlug}
                        onRename={(name) => board.renameProject(p.id, name)}
                        onDelete={() => board.deleteProject(p.id)}
                      />
                    </motion.li>
                  ))}
                <motion.li key="new" layout="position" transition={spring.fly}>
                  <NewProjectTile
                    names={projects.map((p) => p.project_name)}
                    onCreate={board.createProject}
                    onCreated={(id) => router.push(`/${board.activeSlug}/${id}`)}
                  />
                </motion.li>
              </ol>
            )}
          </Frame>

          {ready && (
            <FolderDrawer
              workspaces={ready.workspaces}
              projectsBySlug={board.projectsBySlug}
              openSlug={landed ? board.activeSlug : null}
              onOpen={board.open}
              onCreate={board.createWorkspace}
            />
          )}
        </LayoutGroup>
      </TreePreviews>
    </MotionConfig>
  );
}

type BoardTitleProps = { title: string; count: number; canRename: boolean; onRename(name: string): Promise<void> };

/** The open workspace's name, renamed in place: the pencil swaps it for a field; Enter saves, Escape puts it back. */
function BoardTitle({ title, count, canRename, onRename }: BoardTitleProps) {
  const [name, setName] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const trimmed = name?.trim();
    if (!trimmed || busy) return;
    if (trimmed === title) return setName(null);
    setBusy(true);
    setError(null);
    try {
      await onRename(trimmed); // the new title remounts this (keyed by title), closing the field
    } catch (err: unknown) {
      setError(apiErrorMessage(err, "Could not rename the workspace."));
      setBusy(false);
    }
  }

  return (
    <Frame as="header" gap="1" className="board-head">
      <Text as="span" size="xs" hierarchy="tertiary" className="board-kicker" content="Workspace" />
      {name === null ? (
        <Frame direction="row" gap="2" align="center">
          <Text as="h1" size="display" hierarchy="primary" className="board-title" content={title} />
          {canRename && (
            <Button
              hierarchy="tertiary"
              icon="edit"
              label="Rename workspace"
              showIcon
              showLabel={false}
              className="board-title-edit"
              onClick={() => setName(title)}
            />
          )}
        </Frame>
      ) : (
        <form onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && setName(null)}>
          <Panel className="board-title-field">
            <Input
              aria-label="Workspace name"
              value={name}
              maxLength={100}
              disabled={busy}
              autoFocus
              onFocus={(e) => e.currentTarget.select()}
              onChange={(e) => setName(e.target.value)}
              onBlur={() => !busy && setName(null)}
            />
          </Panel>
        </form>
      )}
      {error && <Text role="alert" size="s" content={error} />}
      <Text size="s" hierarchy="tertiary" content={`${count} ${count === 1 ? "tree" : "trees"} on the board`} />
    </Frame>
  );
}
