import type { ApiClient } from "../client";
import type { WorkspaceCreated, WorkspaceSummary } from "../types";

/** /workspaces/ -- the workspaces the signed-in user owns. */
export function createWorkspacesApi({ http }: ApiClient) {
  return {
    list: () => http.get<WorkspaceSummary[]>("/workspaces/").then((r) => r.data),
    create: (workspaceName: string) =>
      http.post<WorkspaceCreated>("/workspaces/", { workspace_name: workspaceName }).then((r) => r.data),
    /** Renaming also changes the slug; the new one is returned. */
    rename: (workspaceSlug: string, newName: string) =>
      http
        .patch<{ workspace_slug: string }>(`/workspaces/${workspaceSlug}/name`, { new_name: newName })
        .then((r) => r.data),
    /** Deletes the workspace and every project in it. */
    remove: (workspaceSlug: string) => http.delete(`/workspaces/${workspaceSlug}`).then((r) => r.data),
  };
}

export type WorkspacesApi = ReturnType<typeof createWorkspacesApi>;
