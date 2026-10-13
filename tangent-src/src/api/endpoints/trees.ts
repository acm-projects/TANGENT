import type { ApiClient } from "../client";
import type { TreeResponse } from "../types";

/** GET /trees/* -- tree structure, no chat bodies. */
export function createTreesApi({ http }: ApiClient) {
  return {
    get: (treeId: string) => http.get<TreeResponse>(`/trees/${treeId}`).then((r) => r.data),
  };
}

export type TreesApi = ReturnType<typeof createTreesApi>;
