import type { ApiClient } from "../client";
import type { DebateBranch, DebateBranchesCreated, DebateInfo, DebateModels, DebateResult, DebateStarted } from "../types";

/** /debates/* -- start a debate on a node, steer it, and read the verdict node it lands as.
 * The live view is the SSE stream (streamDebate), not part of this. */
export function createDebatesApi({ http }: ApiClient) {
  const debate = (id: string) => `/debates/${id}`;
  const node = (nodeId: string) => `/debates/node/${nodeId}`;

  return {
    models: () => http.get<DebateModels>("/debates/models").then((r) => r.data),
    /** One model argues both sides; two are assigned to sides at random by the server. */
    start: (projectId: string, nodeId: string, topic: string, models: string[], rounds: number) =>
      http
        .post<DebateStarted>("/debates", { project_id: projectId, node_id: nodeId, topic, models, rounds })
        .then((r) => r.data),
    get: (id: string) => http.get<DebateInfo>(debate(id)).then((r) => r.data),
    /** Answers are option labels or the user's own words, never positions; `skip` lets the debate decide. */
    answer: (id: string, answers: Record<string, string | string[]>, skip = false) =>
      http.post(`${debate(id)}/answer`, { answers, skip }).then(() => undefined),
    control: (id: string, action: "stop" | "pick_side", side?: "for" | "against") =>
      http.post(`${debate(id)}/control`, { action, side }).then(() => undefined),
    cancel: (id: string) => http.post(`${debate(id)}/cancel`).then(() => undefined),

    result: (nodeId: string) => http.get<DebateResult>(node(nodeId)).then((r) => r.data),
    /** The whole selection, not a delta: anything left out is unticked. */
    selectBranches: (nodeId: string, selected: string[]) =>
      http.patch<{ branches: DebateBranch[] }>(`${node(nodeId)}/branches`, { selected }).then((r) => r.data.branches),
    /** Idempotent: a branch that already has a node comes back with it, never a duplicate. */
    createBranches: (nodeId: string, ids: string[]) =>
      http.post<DebateBranchesCreated>(`${node(nodeId)}/branches`, { ids }).then((r) => r.data),
  };
}

export type DebatesApi = ReturnType<typeof createDebatesApi>;
