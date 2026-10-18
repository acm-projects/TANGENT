import { useEffect, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { api, apiClient, apiErrorMessage, getAccessToken, streamMessage } from "@/api";
import type { AvailableModel, ChatMessage, ModelUsage, NodeMeta } from "@/api/types";
import { selectBreadcrumb, selectIsLeaf, useTreeStore } from "@/store/treeStore";
import { forkNode } from "../mindmap/nodeActions";

/**
 * Everything the chat panel does, with no UI in it (DESIGN.md Rule 5).
 *
 * The panel shows the selected node's whole history: every node from the root
 * down to it, oldest first. That mirrors what the server sends the model
 * (ARCHITECTURE.md §4), so the user sees exactly the context their next prompt
 * gets. The client only DISPLAYS that history -- it never assembles context
 * itself; sending posts just `{content}` and the server rebuilds the rest.
 */

/** One node's slice of the visible history. */
export interface HistorySection {
  node: NodeMeta;
  /** undefined while this node's chats are still loading */
  messages: ChatMessage[] | undefined;
}

/** Why the message box is disabled, or null when the user can send. */
export type SendBlocker = "no-selection" | "not-leaf" | "streaming" | null;

export function useChat() {
  const activeNodeId = useTreeStore((s) => s.activeNodeId);
  const path = useTreeStore(useShallow((s) => (s.activeNodeId ? selectBreadcrumb(s, s.activeNodeId) : [])));
  const isLeaf = useTreeStore((s) => (s.activeNodeId ? selectIsLeaf(s, s.activeNodeId) : false));
  const chatsByNode = useTreeStore((s) => s.chatsByNode);
  // The active node's partial reply, or null when it isn't streaming. Other nodes' streams don't re-render this.
  const streaming = useTreeStore((s) => (s.activeNodeId ? (s.streaming[s.activeNodeId] ?? null) : null));
  const [error, setError] = useState<string | null>(null);
  const [models, setModels] = useState<AvailableModel[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [modelsLoading, setModelsLoading] = useState(true);
  const [usage, setUsage] = useState<ModelUsage | null>(null);
  const [usageUnavailable, setUsageUnavailable] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.chats
      .models()
      .then((available) => {
        if (cancelled) return;
        setModels(available);
        setSelectedModel(available[0]?.id ?? "");
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(apiErrorMessage(e, "Could not load models."));
      })
      .finally(() => {
        if (!cancelled) setModelsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Load chats for every node on the path that isn't loaded yet. Cached in the
  // store, so moving between siblings doesn't refetch their shared ancestors.
  const missing = path.filter((n) => chatsByNode[n.id] === undefined).map((n) => n.id);
  const missingKey = missing.join(",");
  useEffect(() => {
    if (!missingKey) return;
    let cancelled = false;
    for (const nodeId of missingKey.split(",")) {
      api.nodes
        .get(nodeId)
        .then((node) => {
          if (!cancelled) useTreeStore.getState().setChats(nodeId, node.chats);
        })
        .catch(() => {
          if (!cancelled) setError("Could not load this conversation.");
        });
    }
    return () => {
      cancelled = true;
    };
  }, [missingKey]);

  const history: HistorySection[] = path.map((node) => ({ node, messages: chatsByNode[node.id] }));

  const blocker: SendBlocker = !activeNodeId
    ? "no-selection"
    : streaming !== null
      ? "streaming"
      : // A UI hint only. The server is what actually enforces it (ARCHITECTURE.md §8).
        !isLeaf
        ? "not-leaf"
        : null;

  /** Send a prompt to the selected leaf and stream the reply into the store. */
  async function send(content: string, files: File[] = []) {
    const nodeId = useTreeStore.getState().activeNodeId;
    const text = content.trim();
    if (!nodeId || blocker || nodeId in useTreeStore.getState().streaming || !text) return;
    if (files.length > 0) {
      // The endpoint takes {content, model} only; there is no upload step yet (docs/HANDOFF.md).
      setError("Attachments aren't supported yet. Remove them to send.");
      return;
    }
    if (!selectedModel) {
      setError("Choose a model before sending a message.");
      return;
    }
    setError(null);
    setUsage(null);
    setUsageUnavailable(false);

    const store = useTreeStore.getState();
    const seq = store.chatsByNode[nodeId]?.length ?? 0;
    store.beginStream(nodeId, {
      role: "user",
      content: text,
      seq,
      branch_source: null,
      created_at: new Date().toISOString(),
    });

    // The server saves the exchange itself once the stream ends; this client only displays it.
    try {
      await streamMessage({
        baseURL: "/api",
        nodeId,
        content: text,
        model: selectedModel,
        getAccessToken,
        refresh: apiClient.refresh,
        onEvent: (e) => {
          const s = useTreeStore.getState();
          if (e.type === "token") s.appendToken(nodeId, e.text);
          else if (e.type === "done") {
            setUsage(e.usage ?? null);
            setUsageUnavailable(!e.usage);
            s.endStream(nodeId, {
              role: "assistant",
              content: s.streaming[nodeId] ?? "",
              seq: seq + 1,
              branch_source: null,
              created_at: new Date().toISOString(),
            });
          } else {
            s.abortStream(nodeId);
            setError(e.message);
          }
        },
      });
    } catch (e: unknown) {
      useTreeStore.getState().abortStream(nodeId);
      setError(e instanceof Error ? e.message : "The message could not be sent.");
      return;
    }

    // Re-read the node the server just saved: its title may have changed and its chats are the
    // persisted copy, which replaces the optimistic one built while streaming.
    const fresh = await api.nodes.get(nodeId).catch(() => null);
    if (fresh && !(nodeId in useTreeStore.getState().streaming)) {
      const { chats, ...meta } = fresh;
      useTreeStore.getState().updateNode(meta);
      useTreeStore.getState().setChats(nodeId, chats);
    }
  }

  /** Start a tangent: a new child of `nodeId`, selected and ready to prompt. */
  async function fork(nodeId: string) {
    setError(null);
    try {
      await forkNode(nodeId);
    } catch (e: unknown) {
      setError(apiErrorMessage(e, "Could not create a branch."));
    }
  }

  return {
    activeNodeId,
    history,
    streaming,
    blocker,
    error,
    models,
    selectedModel,
    modelsLoading,
    setSelectedModel,
    usage,
    usageUnavailable,
    send,
    fork,
  };
}
