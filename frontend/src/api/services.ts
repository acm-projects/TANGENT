import type { ApiClient } from "./client";
import type { Node, NodeMeta, TreeResponse } from "./types";

export function createServices({ http }: ApiClient) {
  return {
    trees: {
      get: (treeId: string) => http.get<TreeResponse>(`/trees/${treeId}`).then((r) => r.data),
    },
    nodes: {
      get: (nodeId: string) => http.get<Node>(`/nodes/${nodeId}`).then((r) => r.data),
      /** fork_index is assigned server-side (max sibling + 1, retry on unique violation). */
      fork: (nodeId: string) => http.post<NodeMeta>(`/nodes/${nodeId}/fork`).then((r) => r.data),
      /** Server derives the LCA (the merge node's parent) and copies both branches' content. */
      merge: (sourceLeafIds: [string, string]) =>
        http.post<NodeMeta>("/nodes/merge", { source_leaf_ids: sourceLeafIds }).then((r) => r.data),
    },
  };
}

export type Services = ReturnType<typeof createServices>;
