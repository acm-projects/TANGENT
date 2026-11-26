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
import type { CaseFacts, CaseStatus } from "./sketch";
import "./Board.css";

/* The dashboard board: the open workspace's name, its cases filed the way a detective files them (open cases, then
 * cold ones nobody has touched in weeks, then the closed), each pile under a strip of masking tape and the most
 * recently worked on first, and the drawer of workspace folders along the bottom. The board lands with every folder
 * shut, then the open one empties its cards out onto their piles, so even the first view shows where they live. */

const PILES: { status: CaseStatus; label: string; note: string }[] = [
  { status: "open", label: "Open cases", note: "" },
  { status: "cold", label: "Cold cases", note: "Nothing new in three weeks" },
  { status: "closed", label: "Closed", note: "Every branch has ended" },
];

/** The cases on each pile, most recently worked on first. A case whose tree can't be read is filed as open. */
function file(
  projects: ProjectSummary[],
  facts: Map<string, CaseFacts | null>,
) {
  const when = (p: ProjectSummary) =>
    facts.get(p.id)?.lastActive ?? p.created_at;
  const sorted = [...projects].sort((a, b) => when(b).localeCompare(when(a)));
  return PILES.map((pile) => ({
    ...pile,
    cases: sorted.filter(
      (p) => (facts.get(p.id)?.status ?? "open") === pile.status,
    ),
  }));
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
  // the piles, each card numbered in the order it's dealt out of the folder
  const piles = file(projects, facts ?? new Map());
  const dealOrder = new Map(
    piles.flatMap((pile) => pile.cases).map((p, i) => [p.id, i]),
  );
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
              // the piles sit side by side while they fit, and wrap under each other when they don't
              <Frame direction="row" gap="8" className="board-piles">
                {piles.map((pile) =>
                  pile.cases.length === 0 && pile.status !== "open" ? null : (
                    <Frame
                      as="section"
                      gap="4"
                      key={pile.status}
                      className="board-pile"
                      data-pile={pile.status}
                      aria-labelledby={`pile-${pile.status}`}
                    >
                      {/* the pile's name on a strip of masking tape stuck to the cork */}
                      <Frame
                        direction="row"
                        gap="3"
                        align="center"
                        className="board-pile-head"
                      >
                        <Text
                          as="h2"
                          id={`pile-${pile.status}`}
                          face="stamp"
                          size="xs"
                          className="board-pile-tape"
                          content={`${pile.label} · ${pile.cases.length}`}
                        />
                        {pile.note && (
                          <Text
                            as="span"
                            size="xs"
                            hierarchy="tertiary"
                            content={pile.note}
                          />
                        )}
                      </Frame>
                      <Frame
                        as="ol"
                        direction="row"
                        className="board-grid"
                        aria-labelledby={`pile-${pile.status}`}
                      >
                        {landed &&
                          pile.cases.map((p) => (
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
                                onRename={(name) =>
                                  board.renameProject(p.id, name)
                                }
                                onDelete={() => board.deleteProject(p.id)}
                              />
                            </motion.li>
                          ))}
                        {pile.status === "open" && (
                          <motion.li
                            key="new"
                            layout="position"
                            transition={spring.fly}
                          >
                            <NewProjectTile
                              names={projects.map((p) => p.project_name)}
                              onCreate={board.createProject}
                              onCreated={(id) =>
                                router.push(`/${board.activeSlug}/${id}`)
                              }
                            />
                          </motion.li>
                        )}
                      </Frame>
                    </Frame>
                  ),
                )}
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
