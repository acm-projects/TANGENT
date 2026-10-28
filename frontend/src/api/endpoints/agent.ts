import type { ApiClient } from "../client";
import type { AgentMessage, AgentReply } from "../types";

/** The agent test bench: one request runs the model's whole tool loop. */
export function createAgentApi({ http }: ApiClient) {
  return {
    chat: (projectId: string, body: { messages: AgentMessage[]; model?: string; active_node_id?: string | null }) =>
      http.post<AgentReply>(`/projects/${projectId}/agent`, body).then((r) => r.data),
  };
}

export type AgentApi = ReturnType<typeof createAgentApi>;
