import { useEffect, useState } from "react";
import { api, apiErrorMessage } from "@/api";
import type { Account, WorkspaceSummary } from "@/api/types";

/* The settings page's data: who is signed in, the workspaces they own and how
 * many projects each holds, loading -> ready | error, plus the actions on them.
 *
 * Every change is optimistic, as on the board: the page changes at once, and
 * if the server refuses, the change is undone and `actionError` says why.
 * The page's URL carries a workspace slug (the way back to the board), so
 * renaming or deleting that workspace moves the URL to one that still exists
 * (history.replaceState, like the board: the page doesn't remount mid-change). */

export type AccountState =
  | { status: "loading" }
  | { status: "ready"; account: Account; workspaces: WorkspaceSummary[]; projectCounts: Record<string, number> }
  | { status: "error"; message: string };

type Ready = Extract<AccountState, { status: "ready" }>;

const settingsPath = (slug: string) => `/${encodeURIComponent(slug)}/settings`;

/** Moves the page's URL from workspace `from` to `to`, if it's on `from`. The ?from= path back (Account.tsx) points
 * inside the same workspace, so it follows a rename (`keepBack`) and is dropped when the workspace is deleted. */
function moveUrl(from: string, to: string, keepBack: boolean) {
  if (window.location.pathname !== settingsPath(from)) return;
  const params = new URLSearchParams(window.location.search);
  const back = params.get("from");
  const prefix = `/${encodeURIComponent(from)}/`;
  if (back?.startsWith(prefix)) {
    if (keepBack) params.set("from", `/${encodeURIComponent(to)}/` + back.slice(prefix.length));
    else params.delete("from");
  }
  window.history.replaceState(null, "", settingsPath(to) + (params.size ? `?${params}` : ""));
}

export function useAccount() {
  const [state, setState] = useState<AccountState>({ status: "loading" });
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.auth.me(), api.workspaces.list(), api.projects.list()])
      .then(([account, workspaces, projects]) => {
        const projectCounts: Record<string, number> = {};
        for (const p of projects) projectCounts[p.workspace_id] = (projectCounts[p.workspace_id] ?? 0) + 1;
        if (!cancelled) setState({ status: "ready", account, workspaces, projectCounts });
      })
      .catch((e: unknown) => {
        if (!cancelled) setState({ status: "error", message: apiErrorMessage(e, "Could not load your account.") });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const update = (change: (s: Ready) => Partial<Ready>) =>
    setState((s) => (s.status === "ready" ? { ...s, ...change(s) } : s));

  function optimistic(change: (s: Ready) => Partial<Ready>, undo: (s: Ready) => Partial<Ready>, request: () => Promise<unknown>, fallback: string) {
    setActionError(null);
    update(change);
    request().catch((e: unknown) => {
      update(undo);
      setActionError(apiErrorMessage(e, fallback));
    });
  }

  const ready = state.status === "ready" ? state : null;

  function renameSelf(name: string) {
    const old = ready?.account.name;
    if (old === undefined) return;
    const setName = (to: string) => (s: Ready) => ({ account: { ...s.account, name: to } });
    optimistic(setName(name), setName(old), () => api.auth.updateMe({ name }), "Could not change your name.");
  }

  const setWorkspaces = (map: (w: WorkspaceSummary) => WorkspaceSummary) => (s: Ready) => ({ workspaces: s.workspaces.map(map) });

  /** Renaming changes the slug, so once the server has made it, the row (and the URL, if it's this one) follow. */
  function renameWorkspace(id: string, name: string) {
    const old = ready?.workspaces.find((w) => w.workspace_id === id);
    if (!old) return;
    const setName = (from: string, to: string) =>
      setWorkspaces((w) => (w.workspace_id === id && w.workspace_name === from ? { ...w, workspace_name: to } : w));
    optimistic(
      setName(old.workspace_name, name),
      setName(name, old.workspace_name),
      async () => {
        const { workspace_slug } = await api.workspaces.rename(old.workspace_slug, name);
        update(setWorkspaces((w) => (w.workspace_id === id ? { ...w, workspace_slug } : w)));
        moveUrl(old.workspace_slug, workspace_slug, true);
      },
      "Could not rename the workspace.",
    );
  }

  /** Deletes a workspace and its projects. The last one can't go: there'd be nowhere to sign in to (the backend redirects to one). */
  function deleteWorkspace(id: string) {
    const all = ready?.workspaces ?? [];
    const index = all.findIndex((w) => w.workspace_id === id);
    if (index < 0 || all.length < 2) return;
    const gone = all[index];
    const next = all.find((w) => w.workspace_id !== id)!;
    moveUrl(gone.workspace_slug, next.workspace_slug, false);
    optimistic(
      (s) => ({ workspaces: s.workspaces.filter((w) => w.workspace_id !== id) }),
      (s) => ({ workspaces: [...s.workspaces.slice(0, index), gone, ...s.workspaces.slice(index)] }),
      () => api.workspaces.remove(gone.workspace_slug),
      "Could not delete the workspace.",
    );
  }

  return { state, actionError, renameSelf, renameWorkspace, deleteWorkspace };
}
