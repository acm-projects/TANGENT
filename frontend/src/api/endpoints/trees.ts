import type { ApiClient } from "../client";
import type { TreeResponse } from "../types";

/** Tree structure, no chat bodies. */
export function createTreesApi({ http }: ApiClient) {
  return {
    get: (treeId: string) => http.get<TreeResponse>(`/trees/${treeId}`).then((r) => r.data),
    /** The owner's first visit creates the tree (one empty root node); a sharee gets 404 until then. */
    forProject: (projectId: string) =>
      http.get<TreeResponse>(`/projects/${projectId}/tree`).then((r) => r.data),
  };
}

export type TreesApi = ReturnType<typeof createTreesApi>;
