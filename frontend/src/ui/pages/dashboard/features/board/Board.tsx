"use client";

import { LayoutGroup, motion, MotionConfig } from "motion/react";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { apiErrorMessage } from "@/api";
import type { ProjectSummary } from "@/api/types";
import {
  Button,
  Frame,
  Icon,
  Input,
  Link,
  Loading,
  Panel,
  Text,
} from "@/ui/library";
import { spring } from "@/ui/library/tokens/motion";
import { FOLDER_CARDS, FolderDrawer } from "./components/FolderDrawer";
import { NewProjectTile } from "./components/NewProjectTile";
import { ProjectCard } from "./components/ProjectCard";
import { useBoard } from "./useBoard";
import { TreePreviews, useCaseFiling, type TreeCache } from "./useTreePreview";
import type { CaseFacts } from "./sketch";
import "./Board.css";

/* The dashboard board: the open workspace's name, its cases most recently worked on first, and the drawer of workspace folders along the bottom. The board lands with every folder
 * shut, then the open one deals its cards out onto the board, so even the first view shows where they live. */

/** The cases, most recently worked on first. */
function byLastActive(
  projects: ProjectSummary[],
  facts: Map<string, CaseFacts | null>,
) {
  const when = (p: ProjectSummary) =>
    facts.get(p.id)?.lastActive ?? p.created_at;
  return [...projects].sort((a, b) => when(b).localeCompare(when(a)));
}

type BoardProps = { slug: string };

export function Board({ slug }: BoardProps) {
  const board = useBoard(slug);
  const router = useRouter();
  const [landed, setLanded] = useState(false);
  const [trees] = useState<TreeCache>(() => new Map());
  const ready = board.state.status === "ready" ? board.state : null;

  const projects = board.projectsBySlug.get(board.activeSlug) ?? [];
  // every case's facts, to file them by; the cards wait in their folder until the filing is done
  const facts = useCaseFiling(trees, ready ? projects.map((p) => p.id) : []);
  const filed = ready && facts !== null;

  useEffect(() => {
    if (!filed) return;
    const t = setTimeout(() => setLanded(true), 350);
    return () => clearTimeout(t);
  }, [filed]);
  // the folder holds its newest FOLDER_CARDS; any other card drops in instead of flying out of it
  const inFolder = new Set(projects.slice(0, FOLDER_CARDS).map((p) => p.id));
  // each card numbered in the order it's dealt out of the folder
  const cases = byLastActive(projects, facts ?? new Map());
  const dealOrder = new Map(cases.map((p, i) => [p.id, i]));
  const title = board.workspace?.workspace_name ?? board.activeSlug;

  return (
    <MotionConfig reducedMotion="user">
      <TreePreviews value={trees}>
        <LayoutGroup>
          <Frame gap="6" className="board">
            <Link
              href={`/${encodeURIComponent(board.activeSlug)}/settings`}
              aria-label="Settings"
              title="Settings"
              className="board-settings"
            >
              <Icon icon="settings" size="l" />
            </Link>
            <BoardTitle
              key={title}
              title={title}
              count={board.state.status === "error" ? null : projects.length}
              canRename={Boolean(board.workspace)}
              onRename={board.renameWorkspace}
            />

            {board.actionError && (
              <Text role="alert" size="s" content={board.actionError} />
            )}
            {board.state.status === "loading" && <Loading size="base" />}
            {board.state.status === "error" && (
              <Frame direction="row" gap="3" align="center">
                <Text role="alert" content={board.state.message} />
                <Button
                  hierarchy="secondary"
                  size="s"
                  icon="refresh"
                  showIcon
                  label="Try again"
                  onClick={() => window.location.reload()}
                />
              </Frame>
            )}
            {ready && (
              <Frame
                as="ol"
                direction="row"
                className="board-grid"
                aria-label="Cases"
              >
                {landed &&
                  cases.map((p) => (
                    <motion.li
                      key={p.id}
                      layout="position"
                      transition={spring.fly}
                    >
                      <ProjectCard
                        project={p}
                        index={dealOrder.get(p.id) ?? 0}
                        dropIn={!inFolder.has(p.id)}
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
              </Frame>
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

type BoardTitleProps = {
  title: string;
  /** null while the cases couldn't be loaded: no count to give */ count:
    | number
    | null;
  canRename: boolean;
  onRename(name: string): Promise<void>;
};

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
      <Text
        as="span"
        face="stamp"
        size="xs"
        hierarchy="tertiary"
        className="board-kicker"
        content="Workspace"
      />
      {name === null ? (
        <Frame direction="row" gap="2" align="center">
          <Text
            as="h1"
            face="heading"
            size="display"
            hierarchy="primary"
            className="board-title"
            content={title}
          />
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
        <Frame
          as="form"
          gap="0"
          onSubmit={submit}
          onKeyDown={(e) => e.key === "Escape" && setName(null)}
        >
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
        </Frame>
      )}
      {error && <Text role="alert" size="s" content={error} />}
      {count !== null && (
        <Text
          size="s"
          hierarchy="tertiary"
          content={
            count === 0
              ? "Nothing pinned yet. Start a case with your first question."
              : `${count} ${count === 1 ? "case" : "cases"} on the board`
          }
        />
      )}
    </Frame>
  );
}
