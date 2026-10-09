import { useEffect, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import type { Attachment, ChatMessage, NodeMeta } from "@/api/types";
import { mockApi } from "@/mocks/mockApi";
import { selectBreadcrumb, selectIsLeaf, useTreeStore } from "@/store/treeStore";

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
  const streaming = useTreeStore((s) => s.streaming);
  const [error, setError] = useState<string | null>(null);

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
    setError(null);

    // [proposed] attachments. Mock only: object URLs, never uploaded. The real
    // flow needs an upload endpoint first; see docs/HANDOFF.md.
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

    // TODO(backend): replace with streamMessage from "@/api":
    //   streamMessage({ baseURL: "/api", nodeId, content: text, getAccessToken,
    //                   refresh: apiClient.refresh, onEvent })
    // The real endpoint takes {content} only -- attachments need their own upload step.
    await mockApi.streamMessage({
      nodeId,
      content: text,
      attachments,
      onEvent: (e) => {
        const s = useTreeStore.getState();
        if (e.type === "token") s.appendToken(e.text);
        else if (e.type === "done") {
          s.endStream({
            role: "assistant",
            content: s.streaming?.text ?? "",
            seq: seq + 1,
            branch_source: null,
            created_at: new Date().toISOString(),
          });
        } else {
          s.abortStream();
          setError(e.message);
        }
      },
    });

    // Re-read the node the server just saved. Its metadata may have changed
    // (a new title, an attachment tag) and the map should show it; its chats
    // are the persisted copy, which replaces the optimistic one built while
    // streaming.
    // TODO(backend): replace with api.nodes.get(nodeId)
    const fresh = await mockApi.nodes.get(nodeId).catch(() => null);
    if (fresh && !useTreeStore.getState().streaming) {
      const { chats, ...meta } = fresh;
      useTreeStore.getState().updateNode(meta);
      useTreeStore.getState().setChats(nodeId, chats);
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

  return { activeNodeId, history, streaming, blocker, error, send, fork };
}
