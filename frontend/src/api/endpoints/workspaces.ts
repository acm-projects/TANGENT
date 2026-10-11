import type { ApiClient } from "../client";
import type { WorkspaceSummary } from "../types";

/** GET /workspaces/ -- the workspaces the signed-in user owns. */
export function createWorkspacesApi({ http }: ApiClient) {
  return {
    list: () => http.get<WorkspaceSummary[]>("/workspaces/").then((r) => r.data),
  };
}

export type WorkspacesApi = ReturnType<typeof createWorkspacesApi>;
