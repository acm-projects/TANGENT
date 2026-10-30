import { useEffect, useState } from "react";
import { api, apiErrorMessage } from "@/api";
import type { AvailableModel, AgentToolCall } from "@/api/types";
import { useTreeStore } from "@/store/treeStore";

/**
 * The agent test bench, with no UI in it (DESIGN.md Rule 5). The conversation lives here, not on the server:
 * each send posts all of it, and the server runs the model's tool loop and answers once.
 */

export interface AgentTurn {
  role: "user" | "assistant";
  content: string;
  /** what the agent did before answering */
  toolCalls?: AgentToolCall[];
}

/** Tools that change the tree or a node's messages: when one succeeds the map must be read again
 *  (that also drops the cached chats, so the node's new exchange is fetched). */
const EDITS_TREE = new Set(["branch_node", "write_node", "merge_nodes", "delete_node", "ask_node"]);

/** Read the tree again after the agent changed it, keeping the selection if that node survived. */
async function refreshTree(projectId: string) {
  const { tree, nodes } = await api.trees.forProject(projectId);
  const store = useTreeStore.getState();
  const active = store.activeNodeId;
  store.hydrateTree(tree.root_node_id, nodes);
  store.setActive(active && nodes.some((n) => n.id === active) ? active : null);
}

export function useAgent() {
  const [turns, setTurns] = useState<AgentTurn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [models, setModels] = useState<AvailableModel[]>([]);
  const [model, setModel] = useState("");

  useEffect(() => {
    let cancelled = false;
    api.chats
      .models()
      .then((available) => {
        if (cancelled) return;
        setModels(available);
        setModel(available[0]?.id ?? "");
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(apiErrorMessage(e, "Could not load models."));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function send(content: string) {
    const text = content.trim();
    const { project, activeNodeId } = useTreeStore.getState();
    if (!text || busy || !model || !project) return;
    setError(null);
    setBusy(true);
    const next: AgentTurn[] = [...turns, { role: "user", content: text }];
    setTurns(next);
    try {
      const out = await api.agent.chat(project.id, {
        messages: next.map(({ role, content }) => ({ role, content })),
        model,
        active_node_id: activeNodeId,
      });
      setTurns([...next, { role: "assistant", content: out.reply || "Done.", toolCalls: out.tool_calls }]);
      if (out.tool_calls.some((c) => EDITS_TREE.has(c.name) && !c.result.error)) await refreshTree(project.id);
    } catch (e: unknown) {
      setError(apiErrorMessage(e, "The agent could not answer."));
    } finally {
      setBusy(false);
    }
  }

  return { turns, busy, error, models, model, setModel, send, clear: () => setTurns([]) };
}
