import { useEffect, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { api, streamModelCall } from "@/api";
import type { Attachment, AvailableModel, ChatMessage, ModelUsage, NodeMeta } from "@/api/types";
import { mockApi } from "@/mocks/mockApi";
import { selectBreadcrumb, selectIsLeaf, useTreeStore } from "@/store/treeStore";

/**
 * Everything the chat panel does, with no UI in it (DESIGN.md Rule 5).
 *
 * The panel shows the selected node's whole history: every node from the root
 * down to it, oldest first. The standalone model endpoint used for this demo
 * only receives the new prompt; node history is not sent or persisted.
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
  const streaming = useTreeStore((s) => s.streaming);
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
      .then((availableModels) => {
        if (cancelled) return;
        setModels(availableModels);
        setSelectedModel(availableModels[0]?.id ?? "");
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : "Could not load models.");
        }
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
      // TODO(backend): replace with api.nodes.get(nodeId) -> GET /nodes/:id
      mockApi.nodes
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
    : streaming
      ? "streaming"
      : // A UI hint only. The server is what actually enforces it (ARCHITECTURE.md §8).
        !isLeaf
        ? "not-leaf"
        : null;

  /** Send a prompt to the selected leaf and stream the reply into the store. */
  async function send(content: string, files: File[] = []) {
    const nodeId = useTreeStore.getState().activeNodeId;
    const text = content.trim();
    if (!nodeId || blocker || (!text && files.length === 0)) return;
    if (!selectedModel) {
      setError("Choose a model before sending a message.");
      return;
    }
    if (files.length > 1) {
      setError("Attach one file per message.");
      return;
    }
    const file = files[0];
    if (file && !file.type.startsWith("image/") && file.type !== "application/pdf") {
      setError("Only images and PDFs are supported.");
      return;
    }
    setError(null);
    setUsage(null);
    setUsageUnavailable(false);

    const attachments: Attachment[] = files.map((f, i) => ({
      id: `local-${Date.now()}-${i}`,
      name: f.name,
      kind: f.type === "application/pdf" ? "pdf" : f.type.startsWith("image/") ? "image" : "file",
      url: f.type.startsWith("image/") ? URL.createObjectURL(f) : null,
    }));

    const store = useTreeStore.getState();
    const seq = store.chatsByNode[nodeId]?.length ?? 0;
    store.beginStream(nodeId, {
      role: "user",
      content: text,
      seq,
      branch_source: null,
      created_at: new Date().toISOString(),
      attachments: attachments.length ? attachments : undefined,
    });

    let receivedUsage = false;
    try {
      await streamModelCall({
        prompt: text,
        model: selectedModel,
        file,
        onEvent: (event) => {
          const s = useTreeStore.getState();
          if (event.type === "token") s.appendToken(event.text);
          else if (event.type === "usage") {
            receivedUsage = true;
            setUsage(event.usage);
          } else if (event.type === "done") {
            setUsageUnavailable(!receivedUsage);
            s.endStream({
              role: "assistant",
              content: s.streaming?.text ?? "",
              seq: seq + 1,
              branch_source: null,
              created_at: new Date().toISOString(),
            });
          }
        },
      });
    } catch (cause: unknown) {
      useTreeStore.getState().abortStream();
      setError(cause instanceof Error ? cause.message : "The model request failed.");
      return;
    }

    // The standalone endpoint doesn't persist node metadata, so update the
    // visible mock tree locally with the first prompt as its node title.
    const node = useTreeStore.getState().nodesById[nodeId];
    if (node && !node.title) {
      useTreeStore.getState().updateNode({ ...node, title: text.slice(0, 40) });
    }
  }

  /** Start a tangent: a new child of `nodeId`, selected and ready to prompt. */
  async function fork(nodeId: string) {
    setError(null);
    try {
      // TODO(backend): replace with api.nodes.fork(nodeId) -> POST /nodes/:id/fork
      const child = await mockApi.nodes.fork(nodeId);
      const store = useTreeStore.getState();
      store.addNode(child);
      store.setChats(child.id, []);
      store.setActive(child.id);
    } catch {
      setError("Could not create a branch.");
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
