import type { ApiClient } from "../client";
import type { ProjectDetail, ProjectSearchResult, ProjectSummary, TagColor } from "../types";

/** /projects/ -- every project the user owns or has been shared. */
export function createProjectsApi({ http }: ApiClient) {
  return {
    list: () => http.get<ProjectSummary[]>("/projects/").then((r) => r.data),
    /** `role`, and `forked_project_id` when a sharee already has their own copy. */
    get: (projectId: string) => http.get<ProjectDetail>(`/projects/${projectId}`).then((r) => r.data),
    create: (workspaceId: string, projectName: string) =>
      http
        .post<ProjectSummary>("/projects/", { workspace_id: workspaceId, project_name: projectName })
        .then((r) => r.data),
    /** Owner only; 409 if the name is taken in its workspace. */
    /** Rename what tag colours mean in this case (owner only); returns the project with every colour's name. */
    setTagLabels: (projectId: string, labels: Partial<Record<TagColor, string>>) =>
      http.put<ProjectSummary>(`/projects/${projectId}/tag-labels`, { labels }).then((r) => r.data),
    rename: (projectId: string, projectName: string) =>
      http.patch<ProjectSummary>(`/projects/${projectId}`, { project_name: projectName }).then((r) => r.data),
    /** Owner only. */
    delete: (projectId: string) => http.delete(`/projects/${projectId}`).then(() => undefined),
    /** Cards whose title, summary or messages contain `q` (up to 20), each with a snippet round the match. */
    search: (projectId: string, q: string) =>
      http
        .get<{ results?: ProjectSearchResult[] }>(`/projects/${projectId}/search`, { params: { q } })
        .then((r) => r.data.results ?? []),
  };
}

export type ProjectsApi = ReturnType<typeof createProjectsApi>;
