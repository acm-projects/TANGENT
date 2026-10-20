import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";
import { api, apiErrorMessage } from "@/api";
import type { ProjectSummary, WorkspaceSummary } from "@/api/types";

/* The dashboard's data: every workspace the user owns (the folders) and every
 * project (the cards), loading -> ready | error, plus the actions on them.
 *
 * The open folder is the URL's slug. Switching folders writes the URL with
 * history.pushState instead of navigating, so the page doesn't remount and
 * the cards can fly between folders; Next keeps usePathname in sync, and Back
 * reopens the previous folder.
 *
 * Renames and deletes are optimistic: the board changes at once, and if the
 * server refuses, the change is undone and `actionError` says why (the card or
 * title that started it may be gone by then). Creates wait for the server,
 * which hands out the id or slug they navigate to; they throw, and the
 * component that started one shows the error where it happened. */

export type BoardState =
  | { status: "loading" }
  | { status: "ready"; workspaces: WorkspaceSummary[]; projects: ProjectSummary[] }
  | { status: "error"; message: string };

const dashboardPath = (slug: string) => `/${encodeURIComponent(slug)}/dashboard`;

export function useBoard(initialSlug: string) {
  const [state, setState] = useState<BoardState>({ status: "loading" });
  const [actionError, setActionError] = useState<string | null>(null);
  const pathname = usePathname();
  const activeSlug = decodeURIComponent(pathname.split("/")[1] ?? "") || initialSlug;

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.workspaces.list(), api.projects.list()])
      .then(([workspaces, projects]) => {
        if (!cancelled) setState({ status: "ready", workspaces, projects });
      })
      .catch((e: unknown) => {
        if (!cancelled) setState({ status: "error", message: apiErrorMessage(e, "Could not load your workspaces.") });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const ready = state.status === "ready" ? state : null;

  /** Each folder's projects, newest first. Shared projects carry their owner's slug, so they land in no folder of yours (docs/HANDOFF.md). */
  const projectsBySlug = useMemo(() => {
    const groups = new Map<string, ProjectSummary[]>();
    for (const p of [...(ready?.projects ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at))) {
      groups.set(p.workspace_slug, [...(groups.get(p.workspace_slug) ?? []), p]);
    }
    return groups;
  }, [ready?.projects]);

  const workspace = ready?.workspaces.find((w) => w.workspace_slug === activeSlug) ?? null;

  const open = useCallback((slug: string) => window.history.pushState(null, "", dashboardPath(slug)), []);

  const update = (fn: (s: Extract<BoardState, { status: "ready" }>) => Partial<Extract<BoardState, { status: "ready" }>>) =>
    setState((s) => (s.status === "ready" ? { ...s, ...fn(s) } : s));

  async function createProject(name: string) {
    if (!workspace) throw new Error("Workspace not found.");
    const project = await api.projects.create(workspace.workspace_id, name);
    update((s) => ({ projects: [project, ...s.projects] }));
    return project;
  }

  /** Shows `change` now and sends `request`; if that fails, applies `undo` and reports. */
  function optimistic(change: Parameters<typeof update>[0], undo: Parameters<typeof update>[0], request: () => Promise<unknown>, fallback: string) {
    setActionError(null);
    update(change);
    request().catch((e: unknown) => {
      update(undo);
      setActionError(apiErrorMessage(e, fallback));
    });
  }

  const setProjectName = (id: string, from: string, to: string) => (s: Extract<BoardState, { status: "ready" }>) => ({
    // only if it still reads `from`: a later rename wins
    projects: s.projects.map((p) => (p.id === id && p.project_name === from ? { ...p, project_name: to } : p)),
  });

  async function renameProject(id: string, name: string) {
    const old = ready?.projects.find((p) => p.id === id)?.project_name;
    if (old === undefined) return;
    optimistic(
      setProjectName(id, old, name),
      setProjectName(id, name, old),
      // the server may tidy the name
      () => api.projects.rename(id, name).then((r) => update(setProjectName(id, name, r.project_name))),
      "Could not rename the project.",
    );
  }

  async function deleteProject(id: string) {
    const gone = ready?.projects.find((p) => p.id === id);
    if (!gone) return;
    optimistic(
      (s) => ({ projects: s.projects.filter((p) => p.id !== id) }),
      (s) => ({ projects: [gone, ...s.projects] }),
      () => api.projects.delete(id),
      "Could not delete the project.",
    );
  }

  /** Makes a folder and opens it. The POST answer has no id, which creating a project needs, so the list is read again. */
  async function createWorkspace(name: string) {
    const { workspace_slug } = await api.workspaces.create(name);
    const workspaces = await api.workspaces.list();
    update(() => ({ workspaces }));
    open(workspace_slug);
  }

  /** Renaming changes the slug, so once the server has made it, the folder's projects and the URL follow. The name shows at once. */
  async function renameWorkspace(name: string) {
    if (!workspace) return;
    const { workspace_id, workspace_name: old, workspace_slug: oldSlug } = workspace;
    const setName = (from: string, to: string) => (s: Extract<BoardState, { status: "ready" }>) => ({
      workspaces: s.workspaces.map((w) => (w.workspace_id === workspace_id && w.workspace_name === from ? { ...w, workspace_name: to } : w)),
    });
    optimistic(
      setName(old, name),
      setName(name, old),
      async () => {
        const { workspace_slug } = await api.workspaces.rename(oldSlug, name);
        update((s) => ({
          workspaces: s.workspaces.map((w) => (w.workspace_id === workspace_id ? { ...w, workspace_slug } : w)),
          projects: s.projects.map((p) => (p.workspace_id === workspace_id ? { ...p, workspace_slug } : p)),
        }));
        // only if this folder is still the open one
        if (window.location.pathname === dashboardPath(oldSlug)) window.history.replaceState(null, "", dashboardPath(workspace_slug));
      },
      "Could not rename the workspace.",
    );
  }

  return {
    state,
    actionError,
    activeSlug,
    workspace,
    projectsBySlug,
    open,
    createProject,
    renameProject,
    deleteProject,
    createWorkspace,
    renameWorkspace,
  };
}
