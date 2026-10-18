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
 * reopens the previous folder. Actions throw; the component that started one
 * shows the error where it happened. */

export type BoardState =
  | { status: "loading" }
  | { status: "ready"; workspaces: WorkspaceSummary[]; projects: ProjectSummary[] }
  | { status: "error"; message: string };

const dashboardPath = (slug: string) => `/${encodeURIComponent(slug)}/dashboard`;

export function useBoard(initialSlug: string) {
  const [state, setState] = useState<BoardState>({ status: "loading" });
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

  async function renameProject(id: string, name: string) {
    const renamed = await api.projects.rename(id, name);
    update((s) => ({ projects: s.projects.map((p) => (p.id === id ? { ...p, project_name: renamed.project_name } : p)) }));
  }

  async function deleteProject(id: string) {
    await api.projects.delete(id);
    update((s) => ({ projects: s.projects.filter((p) => p.id !== id) }));
  }

  /** Makes a folder and opens it. The POST answer has no id, which creating a project needs, so the list is read again. */
  async function createWorkspace(name: string) {
    const { workspace_slug } = await api.workspaces.create(name);
    const workspaces = await api.workspaces.list();
    update(() => ({ workspaces }));
    open(workspace_slug);
  }

  /** Renaming changes the slug, so the folder's projects and the URL follow it. */
  async function renameWorkspace(name: string) {
    if (!workspace) return;
    const { workspace_slug } = await api.workspaces.rename(workspace.workspace_slug, name);
    update((s) => ({
      workspaces: s.workspaces.map((w) =>
        w.workspace_id === workspace.workspace_id ? { ...w, workspace_name: name, workspace_slug } : w,
      ),
      projects: s.projects.map((p) => (p.workspace_id === workspace.workspace_id ? { ...p, workspace_slug } : p)),
    }));
    window.history.replaceState(null, "", dashboardPath(workspace_slug));
  }

  return {
    state,
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
