import { useEffect, useMemo, useState } from "react";
import { api, apiClient, apiErrorMessage, forkedProjectIdOf, getAccessToken, streamMessage } from "@/api";
import type { AvailableModel, ChatMessage, ModelUsage, NodeMeta } from "@/api/types";
import { selectExhibits, selectIsLeaf, selectThreadPlan, type ThreadPlanItem, useTreeStore } from "@/store/treeStore";
import { forkNode, isPending, redirectToCopy, splitNode, switchToFork } from "../mindmap/nodeActions";
import { uploadAttachments } from "./attachments";

/**
 * Everything the chat panel does, with no UI in it (DESIGN.md Rule 5).
 *
 * The panel shows the selected node's whole history: every node from the root
 * down to it, oldest first. That mirrors what the server sends the model
 * (ARCHITECTURE.md §4), so the user sees exactly the context their next prompt
 * gets. The client only DISPLAYS that history -- it never assembles context
 * itself; sending posts just `{content}` and the server rebuilds the rest.
 */

export type HistoryItem =
  | {
      kind: "node";
      node: NodeMeta;
      exhibit: string;
      messages: ChatMessage[] | undefined;
    }
  | {
      kind: "merge";
      branches: { from: string; exhibit: string; title: string | null; items: HistoryItem[] }[];
    };

function planIds(plan: ThreadPlanItem[], result = new Set<string>()): Set<string> {
  for (const item of plan) {
    if (typeof item === "string") result.add(item);
    else for (const branch of item.merge) planIds(branch.plan, result);
  }
  return result;
}

function buildHistory(
  plan: ThreadPlanItem[],
  nodesById: Record<string, NodeMeta>,
  chatsByNode: Record<string, ChatMessage[]>,
  exhibits: Record<string, string>,
): HistoryItem[] {
  return plan.flatMap((item): HistoryItem[] => {
    if (typeof item === "string") {
      const node = nodesById[item];
      return node ? [{ kind: "node", node, exhibit: exhibits[item] ?? "", messages: chatsByNode[item] }] : [];
    }
    return [{
      kind: "merge",
      branches: item.merge.map((branch) => ({
        from: branch.from,
        exhibit: exhibits[branch.from] ?? "",
        title: nodesById[branch.from]?.title ?? null,
        items: buildHistory(branch.plan, nodesById, chatsByNode, exhibits),
      })),
    }];
  });
}

/** Why the message box is disabled, or null when the user can send. */
export type SendBlocker = "no-selection" | "not-leaf" | "streaming" | "pending" | null;

export function useChat() {
  const activeNodeId = useTreeStore((s) => s.activeNodeId);
  const nodesById = useTreeStore((s) => s.nodesById);
  const activeNode = activeNodeId ? nodesById[activeNodeId] : undefined;
  const plan = useMemo(
    () => (activeNodeId ? selectThreadPlan({ nodesById }, activeNodeId) : []),
    [activeNodeId, nodesById],
  );
  const nodeModel = activeNode?.model ?? null;
  const nodeTokens = activeNode?.tokens ?? 0;
  const historyIds = [...planIds(plan)];
  const branchTokens = historyIds.reduce((total, id) => total + (nodesById[id]?.tokens ?? 0), 0);
  const isLeaf = useTreeStore((s) => (s.activeNodeId ? selectIsLeaf(s, s.activeNodeId) : false));
  const chatsByNode = useTreeStore((s) => s.chatsByNode);
  const loadedMessageCount = historyIds.reduce((total, id) => total + (chatsByNode[id]?.length ?? 0), 0);
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
  const activeModel = nodeModel ?? selectedModel;
  const [modelsLoading, setModelsLoading] = useState(true);
  const [usage, setUsage] = useState<ModelUsage | null>(null);
  const [usageUnavailable, setUsageUnavailable] = useState(false);
  const [usageModel, setUsageModel] = useState<string | null>(null);
  const usageContextLength = models.find((model) => model.id === usageModel)?.context_length ?? null;

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
  const missing = historyIds.filter((id) => chatsByNode[id] === undefined);
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

  const exhibits = selectExhibits({ rootId, nodesById, childrenByParent });
  const history = buildHistory(plan, nodesById, chatsByNode, exhibits);

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
      const projectId = useTreeStore.getState().nodesById[nodeId]?.project_id;
      if (!projectId) return;
      try {
        await uploadAttachments(api.sources, projectId, nodeId, files);
      } catch (e) {
        setError(apiErrorMessage(e, "Could not attach the file; nothing was sent."));
        return;
      }
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
    if (!activeModel) {
      setError("Choose a model before sending a message.");
      return false;
    }
    setError(null);
    useTreeStore.getState().setNotice(null);
    setUsage(null);
    setUsageUnavailable(false);
    setUsageModel(null);

    const store = useTreeStore.getState();
    const seq = store.chatsByNode[nodeId]?.length ?? 0;
    store.beginStream(nodeId, {
      role: "user",
      content: text,
      seq,
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
        model: activeModel,
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
            setUsageModel(e.model ?? activeModel);
            s.endStream(nodeId, {
              role: "assistant",
              content: s.streaming[nodeId] ?? "",
              seq: seq + 1,
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
    activeNode,
    activeExhibit: activeNodeId ? exhibits[activeNodeId] : undefined,
    historyIds,
    loadedMessageCount,
    history,
    nodeModel,
    nodeTokens,
    branchTokens,
    streaming,
    blocker,
    error,
    models,
    selectedModel: activeModel,
    modelLocked: nodeModel !== null,
    modelsLoading,
    setSelectedModel,
    usage,
    usageUnavailable,
    usageContextLength,
    send,
    stop,
    canRetry,
    retry,
    branch,
  };
}
