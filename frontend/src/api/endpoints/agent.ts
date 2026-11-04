import type { ApiClient } from "../client";
import type { AgentMessage, AgentReply, AgentRunState } from "../types";

/** The agent. `chat` is the stateless test bench (one request runs the whole tool loop); the run endpoints are the
 * persistent runtime, whose live view is the SSE stream (streamAgentRun), not part of this. */
export function createAgentApi({ http }: ApiClient) {
  const runs = (projectId: string) => `/projects/${projectId}/agent/runs`;
  return {
    chat: (projectId: string, body: { messages: AgentMessage[]; model?: string; active_node_id?: string | null }) =>
      http.post<AgentReply>(`/projects/${projectId}/agent`, body).then((r) => r.data),
    createRun: (projectId: string, body: { goal: string; model?: string; active_node_id?: string | null }) =>
      http.post<AgentRunState>(runs(projectId), body).then((r) => r.data),
    getRun: (projectId: string, runId: string) => http.get<AgentRunState>(`${runs(projectId)}/${runId}`).then((r) => r.data),
    /** Answer the open questions; keys are question ids, values the chosen option labels or free text. */
    answerRun: (projectId: string, runId: string, answers: Record<string, string | string[]>) =>
      http.post<AgentRunState>(`${runs(projectId)}/${runId}/answer`, { answers }).then((r) => r.data),
    cancelRun: (projectId: string, runId: string) =>
      http.post<AgentRunState>(`${runs(projectId)}/${runId}/cancel`).then((r) => r.data),
  };
}

export type AgentApi = ReturnType<typeof createAgentApi>;
