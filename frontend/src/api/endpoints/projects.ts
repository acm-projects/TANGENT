import type { ApiClient } from "../client";
import type { ProjectSummary } from "../types";

/** /projects/ -- every project the user owns or has been shared. */
export function createProjectsApi({ http }: ApiClient) {
  return {
    list: () => http.get<ProjectSummary[]>("/projects/").then((r) => r.data),
    create: (workspaceId: string, projectName: string) =>
      http
        .post<ProjectSummary>("/projects/", { workspace_id: workspaceId, project_name: projectName })
        .then((r) => r.data),
  };
}

export type ProjectsApi = ReturnType<typeof createProjectsApi>;
