import type { ApiClient } from "../client";
import type { ForkedNode, Node } from "../types";

/** /nodes/* -- a single node with its chats, plus forking and merging. */
export function createNodesApi({ http }: ApiClient) {
  return {
    get: (nodeId: string) => http.get<Node>(`/nodes/${nodeId}`).then((r) => r.data),
    /** fork_index is assigned server-side (max sibling + 1, retry on unique violation). */
    fork: (nodeId: string) => http.post<ForkedNode>(`/nodes/${nodeId}/fork`).then((r) => r.data),
    /** Deletes the node and its whole subtree (the root refuses: 409). */
    delete: (nodeId: string) => http.delete(`/nodes/${nodeId}`).then(() => undefined),
    /** Stops the caller's reply streaming on this node; the stream then ends with `done {stopped: true}`. */
    stopMessage: (nodeId: string) => http.post(`/nodes/${nodeId}/messages/stop`).then(() => undefined),
    /** Server derives the LCA (the merge node's parent) and copies both branches' content. */
    merge: (sourceLeafIds: [string, string]) =>
      http.post<ForkedNode>("/nodes/merge", { source_leaf_ids: sourceLeafIds }).then((r) => r.data),
  };
}

export type NodesApi = ReturnType<typeof createNodesApi>;
