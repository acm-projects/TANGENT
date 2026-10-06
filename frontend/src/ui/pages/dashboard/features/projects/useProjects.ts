import { useEffect, useState } from "react";
import type { ProjectSummary } from "@/api/types";
import { mockApi } from "@/mocks/mockApi";

/* The dashboard's project list: loading -> ready | error. */

export type ProjectsState =
  | { status: "loading" }
  | { status: "ready"; projects: ProjectSummary[] }
  | { status: "error"; message: string };

export function useProjects(slug: string): ProjectsState {
  const [state, setState] = useState<ProjectsState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    // TODO(backend): replace with api.projects.list() -> GET /projects/
    // (add src/api/endpoints/projects.ts). That endpoint returns every project
    // the user can see; keep the filter so only this workspace's show here.
    mockApi.projects
      .list()
      .then((projects) => {
        if (cancelled) return;
        const mine = projects
          .filter((p) => p.workspace_slug === slug)
          .sort((a, b) => b.created_at.localeCompare(a.created_at));
        setState({ status: "ready", projects: mine });
      })
      .catch((e: unknown) => {
        if (!cancelled) setState({ status: "error", message: e instanceof Error ? e.message : "Could not load projects." });
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  return state;
}
