import { useCallback, useEffect, useState } from "react";
import { api, apiErrorMessage } from "@/api";
import type { ProjectSummary } from "@/api/types";

/* The dashboard's project list: loading -> ready | error, plus creating one. */

export type ProjectsState =
  | { status: "loading" }
  | { status: "ready"; projects: ProjectSummary[] }
  | { status: "error"; message: string };

export function useProjects(slug: string) {
  const [state, setState] = useState<ProjectsState>({ status: "loading" });
  const [createError, setCreateError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    // GET /projects/ returns every project the user can see; only this workspace's show here.
    api.projects
      .list()
      .then((projects) => {
        if (cancelled) return;
        const mine = projects
          .filter((p) => p.workspace_slug === slug)
          .sort((a, b) => b.created_at.localeCompare(a.created_at));
        setState({ status: "ready", projects: mine });
      })
      .catch((e: unknown) => {
        if (!cancelled) setState({ status: "error", message: apiErrorMessage(e, "Could not load projects.") });
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  /** Creates a project in this workspace and puts it first in the list. */
  const create = useCallback(
    async (name: string) => {
      setCreateError(null);
      try {
        const workspace = (await api.workspaces.list()).find((w) => w.workspace_slug === slug);
        if (!workspace) throw new Error("Workspace not found.");
        const project = await api.projects.create(workspace.workspace_id, name);
        setState((s) => (s.status === "ready" ? { status: "ready", projects: [project, ...s.projects] } : s));
      } catch (e: unknown) {
        setCreateError(apiErrorMessage(e, "Could not create the project."));
      }
    },
    [slug],
  );

  return { state, create, createError };
}
