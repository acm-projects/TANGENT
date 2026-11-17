import type { ApiClient } from "../client";
import type { AnswerResult, CompactResult, Ending, ForkedNode, Node, NodeTag, ResolveResult, SplitResult } from "../types";

/** /nodes/* -- a single node with its chats, plus forking and merging. */
export function createNodesApi({ http }: ApiClient) {
  return {
    get: (nodeId: string) => http.get<Node>(`/nodes/${nodeId}`).then((r) => r.data),
    /** fork_index is assigned server-side (max sibling + 1, retry on unique violation). */
    fork: (nodeId: string) => http.post<ForkedNode>(`/nodes/${nodeId}/fork`).then((r) => r.data),
    /** Cuts the node after the reply at `afterIndex`: a new child takes the rest and the node's children.
     * `tangent` also makes an empty child beside it to prompt. */
    split: (nodeId: string, afterIndex: number, tangent = false) =>
      http.post<SplitResult>(`/nodes/${nodeId}/split`, { after_seq: afterIndex, tangent }).then((r) => r.data),
    /** Folds the node's only child back into it --
     * a split undone: the child's chats are appended (renumbered), its children move up to the node, and the
     * child is deleted. 409 if the node has any other child. A sharee's first write forks the project, as for fork. */
    join: (nodeId: string) => http.post<ForkedNode>(`/nodes/${nodeId}/join`).then((r) => r.data),
    /** Starts the project over from its root: every branch goes and the root's conversation is cleared. Only the
     * root (409 otherwise). A sharee's reset is their first write: it forks, and the response carries `fork`. */
    reset: (rootId: string) => http.post<ForkedNode>(`/nodes/${rootId}/reset`).then((r) => r.data),
    /** Answer a question card: a label, the user's own words, or several for a multi question. A new answer opens a
     * branch; the same one again returns the branch it opened before. A sharee's first write forks, as for fork. */
    answer: (nodeId: string, answer: string | string[]) =>
      http.post<AnswerResult>(`/nodes/${nodeId}/answer`, { answer }).then((r) => r.data),
    /** Compact: the card's model summarises its thread into a new compact card under it, where the context starts
     * afresh from the summary. A sharee's first write forks, as for fork. */
    compact: (nodeId: string) => http.post<CompactResult>(`/nodes/${nodeId}/compact`).then((r) => r.data),
    /** Stamp how the card's branch ended (resolved, a dead lead, ...): a marker that it is settled. */
    resolve: (nodeId: string, kind: Ending = "resolved") =>
      http.post<ResolveResult>(`/nodes/${nodeId}/resolve`, { kind }).then((r) => r.data),
    /** Reopen a resolved card: the stamp comes off. */
    reopen: (nodeId: string) => http.post<ResolveResult>(`/nodes/${nodeId}/reopen`).then((r) => r.data),
    /** Pin a coloured tag on the card. */
    tag: (nodeId: string, tag: NodeTag) => http.put<ResolveResult>(`/nodes/${nodeId}/tag`, tag).then((r) => r.data),
    /** Take the card's tag off. */
    untag: (nodeId: string) => http.delete<ResolveResult>(`/nodes/${nodeId}/tag`).then((r) => r.data),
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
