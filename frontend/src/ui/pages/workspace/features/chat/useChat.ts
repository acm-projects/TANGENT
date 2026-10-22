import { useEffect, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { api, apiClient, apiErrorMessage, forkedProjectIdOf, getAccessToken, streamMessage } from "@/api";
import type { AvailableModel, ChatMessage, ModelUsage, NodeMeta } from "@/api/types";
import { selectBreadcrumb, selectExhibits, selectIsLeaf, useTreeStore } from "@/store/treeStore";
import { forkNode, isPending, redirectToCopy, splitNode, switchToFork } from "../mindmap/nodeActions";

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
  /** its outline number on the board, as the map shows it: "1.2.1" */
  exhibit: string;
  /** undefined while this node's chats are still loading */
  messages: ChatMessage[] | undefined;
}

/** Why the message box is disabled, or null when the user can send. */
export type SendBlocker = "no-selection" | "not-leaf" | "streaming" | "pending" | null;

export function useChat() {
  const activeNodeId = useTreeStore((s) => s.activeNodeId);
  const path = useTreeStore(useShallow((s) => (s.activeNodeId ? selectBreadcrumb(s, s.activeNodeId) : [])));
  const isLeaf = useTreeStore((s) => (s.activeNodeId ? selectIsLeaf(s, s.activeNodeId) : false));
  const chatsByNode = useTreeStore((s) => s.chatsByNode);
  const rootId = useTreeStore((s) => s.rootId);
  const childrenByParent = useTreeStore((s) => s.childrenByParent);
  // The active node's partial reply, or null when it isn't streaming. Other nodes' streams don't re-render this.
  const streaming = useTreeStore((s) => (s.activeNodeId ? (s.streaming[s.activeNodeId] ?? null) : null));
  const [localError, setError] = useState<string | null>(null);
  // Survives a project switch, which remounts the page and drops local state.
  const notice = useTreeStore((s) => s.notice);
  const error = localError ?? notice;
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

  const exhibits = selectExhibits({ rootId, childrenByParent });
  const history: HistorySection[] = path.map((node) => ({ node, exhibit: exhibits[node.id], messages: chatsByNode[node.id] }));

  const blocker: SendBlocker = !activeNodeId
    ? "no-selection"
    : isPending(activeNodeId)
      ? "pending"
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
    await ask(nodeId, text, false);
  }

  /** The selected leaf's last reply can be regenerated (it ends in a question and its answer). */
  const lastChats = activeNodeId ? chatsByNode[activeNodeId] : undefined;
  const canRetry = blocker === null && lastChats !== undefined && lastChats.length >= 2 && lastChats.at(-1)!.role === "assistant" && lastChats.at(-2)!.role === "user";

  /** Regenerate the selected leaf's last reply. Optimistic: the old reply goes at once and the question is asked
   * again; if nothing new is saved (an error, or stopped before a token) the old exchange is put back. */
  async function retry() {
    const nodeId = useTreeStore.getState().activeNodeId;
    const before = nodeId ? useTreeStore.getState().chatsByNode[nodeId] : undefined;
    if (!nodeId || !canRetry || !before) return;
    const question = before.at(-2)!;
    useTreeStore.getState().setChats(nodeId, before.slice(0, -2));
    const saved = await ask(nodeId, question.content, true);
    // the server keeps the old exchange whenever it saved nothing; show it again, unless the user has moved on
    if (!saved && !(nodeId in useTreeStore.getState().streaming)) useTreeStore.getState().setChats(nodeId, before);
  }

  /** Ask `text` on `nodeId` (as a retry: in place of its last exchange) and stream the reply. Resolves to
   * whether a reply was saved. */
  async function ask(nodeId: string, text: string, isRetry: boolean): Promise<boolean> {
    if (!selectedModel) {
      setError("Choose a model before sending a message.");
      return false;
    }
    setError(null);
    useTreeStore.getState().setNotice(null);
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

    // The first write by a sharee moves them into their own copy; the original's node ids are meaningless there.
    let switched = false;
    let saved = false;
    const toCopy = (copyId: string) => {
      switched = true;
      return redirectToCopy(copyId).catch((e: unknown) => setError(apiErrorMessage(e, "Could not open your copy.")));
    };

    // The server saves the exchange itself once the stream ends; this client only displays it.
    try {
      await streamMessage({
        baseURL: "/api",
        nodeId,
        content: text,
        model: selectedModel,
        retry: isRetry,
        getAccessToken,
        refresh: apiClient.refresh,
        onEvent: (e) => {
          const s = useTreeStore.getState();
          if (e.type === "token") s.appendToken(nodeId, e.text);
          else if (e.type === "done" && e.fork) {
            switched = true;
            s.abortStream(nodeId);
            switchToFork(e.fork, e.fork.node_id ?? null);
          } else if (e.type === "done" && e.stopped && !s.streaming[nodeId]) {
            s.abortStream(nodeId); // stopped before the first token: nothing was saved (the re-read below drops the prompt)
          } else if (e.type === "done") {
            saved = true;
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
            // The copy exists even though the model failed; go there, and keep the message across the switch.
            if (e.fork) {
              switched = true;
              switchToFork(e.fork, e.fork.node_id ?? null, e.message);
            } else if (e.forkedProjectId) void toCopy(e.forkedProjectId);
          }
        },
      });
    } catch (e: unknown) {
      useTreeStore.getState().abortStream(nodeId);
      const copyId = forkedProjectIdOf(e);
      if (copyId) await toCopy(copyId);
      else setError(e instanceof Error ? e.message : "The message could not be sent.");
      return false;
    }
    if (switched) return saved;

    // Re-read the node the server just saved: its title may have changed and its chats are the
    // persisted copy, which replaces the optimistic one built while streaming.
    const fresh = await api.nodes.get(nodeId).catch(() => null);
    if (fresh && !(nodeId in useTreeStore.getState().streaming)) {
      const { chats, ...meta } = fresh;
      useTreeStore.getState().updateNode(meta);
      useTreeStore.getState().setChats(nodeId, chats);
    }
    return saved;
  }

  /** Stop the selected node's reply. The stream itself ends (`done`, stopped) and send() finishes as usual. */
  function stop() {
    if (!activeNodeId || streaming === null) return;
    api.nodes.stopMessage(activeNodeId).catch((e: unknown) => setError(apiErrorMessage(e, "Could not stop the reply.")));
  }

  /** Start a tangent from the reply `seq` of `nodeId`, selected and ready to prompt. From the node's last
   * reply that's a new child; from an earlier one the node is split there first (splitNode), so the tangent
   * carries only what came before. */
  async function branch(nodeId: string, seq: number) {
    setError(null);
    const chats = useTreeStore.getState().chatsByNode[nodeId] ?? [];
    const at = chats.findIndex((m) => m.seq === seq && m.role === "assistant");
    try {
      if (at < 0 || at === chats.length - 1) await forkNode(nodeId);
      else await splitNode(nodeId, at);
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
    stop,
    canRetry,
    retry,
    branch,
  };
}
