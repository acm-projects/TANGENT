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
    /** Owner only; 409 if the name is taken in its workspace. */
    rename: (projectId: string, projectName: string) =>
      http.patch<ProjectSummary>(`/projects/${projectId}`, { project_name: projectName }).then((r) => r.data),
    /** Owner only. */
    delete: (projectId: string) => http.delete(`/projects/${projectId}`).then(() => undefined),
  };
}

export type ProjectsApi = ReturnType<typeof createProjectsApi>;
