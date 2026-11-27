import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { api, apiClient, apiErrorMessage, forkedProjectIdOf, getAccessToken, isNetworkError, OFFLINE, streamMessage } from "@/api";
import type { AvailableModel, ChatMessage, ModelUsage, NodeMeta } from "@/api/types";
import { selectExhibits, selectIsLeaf, selectThreadPlan, type ThreadPlanItem, useTreeStore } from "@/store/treeStore";
import { selectCardInCourt } from "@/store/debateStore";
import { forkNode, isPending, redirectToCopy, refreshTree, splitNode, switchToFork } from "../mindmap/nodeActions";
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
export type SendBlocker = "no-selection" | "question" | "debate" | "streaming" | "pending" | null;

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
  const inCourt = useTreeStore((s) => selectCardInCourt(s.activeNodeId)(s));
  // ...and its tool calls and quick thinking so far
  const streamWork = useTreeStore((s) => (s.activeNodeId ? s.streamWork[s.activeNodeId] : undefined));
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
  // the context window of the model this card uses (or would use), for the sheet's context bar
  const contextLength = usageContextLength ?? models.find((model) => model.id === activeModel)?.context_length ?? null;

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
  // Under a compact card the model's context starts at its summary, so the history does too: the cards above it fold.
  const compactAt = history.findLastIndex((item) => item.kind === "node" && item.node.node_type === "compact");
  const foldedCount = Math.max(0, compactAt);

  const blocker: SendBlocker = !activeNodeId
    ? "no-selection"
    : isPending(activeNodeId)
      ? "pending"
      : streaming !== null
      ? "streaming"
      : // a question card is answered on its card, not written on
        nodesById[activeNodeId]?.node_type === "question"
        ? "question"
        : // a debate's card takes nothing until its verdict is in
          inCourt
          ? "debate"
          : null;
  // A card with branches takes no more messages of its own (the server enforces it, ARCHITECTURE.md §8): a message
  // sent there goes on a new branch from its last reply instead, so the user can always just ask.
  const branchesOnSend = blocker === null && !isLeaf;

  /** Send a prompt to the selected card and stream the reply into the store. On a card with branches, a new branch is
   * made from its last reply first, and the prompt goes there. */
  async function send(content: string, files: File[] = []) {
    let nodeId = useTreeStore.getState().activeNodeId;
    const text = content.trim();
    if (!nodeId || blocker || nodeId in useTreeStore.getState().streaming || !text) return;
    if (branchesOnSend) {
      try {
        await forkNode(nodeId);
      } catch (e: unknown) {
        setError(apiErrorMessage(e, "Could not start a new branch; nothing was sent."));
        return;
      }
      // the new branch is picked once the server has made it (still a placeholder: it moved to a copy, or failed)
      const made = useTreeStore.getState().activeNodeId;
      if (!made || isPending(made) || made === nodeId) return;
      nodeId = made;
    }
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
  const canRetry = blocker === null && isLeaf && lastChats !== undefined && lastChats.length >= 2 && lastChats.at(-1)!.role === "assistant" && lastChats.at(-2)!.role === "user";

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
          else if (e.type === "tool") s.addStreamTool(nodeId, { name: e.name, brief: e.brief, ok: e.ok });
          else if (e.type === "reasoning") s.appendReasoning(nodeId, e.text);
          else if (e.type === "question") {
            // the model asked instead of answering: its question card goes on the map now, not at the next reload
            const projectId = s.nodesById[nodeId]?.project_id;
            if (projectId) void refreshTree(projectId).catch(() => {});
          }
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
              content: e.content ?? s.streaming[nodeId] ?? "",
              seq: seq + 1,
              created_at: new Date().toISOString(),
              citations: e.citations,
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
      else setError(isNetworkError(e) ? OFFLINE : e instanceof Error ? e.message : "The message could not be sent.");
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

  /** Edit the question `seq` of `nodeId`: the original stays, and the edited question is asked on a new branch
   * beside it (the conversation up to that question, then the new wording). A node's first question branches from
   * its parent; anywhere later, the node is cut just before the question. The case's own first question can't be. */
  // Resolves whether the new branch was made (the caller keeps the reworded text until it was). Refused only while
  // this card's own reply streams: the server can't cut a card mid-reply, and that's when the Edit button hides too.
  async function edit(nodeId: string, seq: number, content: string): Promise<boolean> {
    const text = content.trim();
    const store = useTreeStore.getState();
    const chats = store.chatsByNode[nodeId] ?? [];
    const at = chats.findIndex((m) => m.seq === seq && m.role === "user");
    if (!text || at < 0 || nodeId in store.streaming) return false;
    setError(null);
    try {
      if (at > 0) await splitNode(nodeId, at - 1);
      else {
        const parent = store.nodesById[nodeId]?.parent_id;
        if (!parent) return false;
        await forkNode(parent);
      }
    } catch (e: unknown) {
      setError(apiErrorMessage(e, "Could not make the new branch."));
      return false;
    }
    // the new branch is selected once the server has made it (a placeholder id means it hasn't, or it moved to a copy)
    const id = useTreeStore.getState().activeNodeId;
    if (!id || isPending(id) || id === nodeId) return false;
    void ask(id, text, false);
    return true;
  }

  // Stable handles for the history's actions: MessageBubble is memoised, and a new function every render (every
  // streamed token re-renders this) would make every message re-parse its markdown and maths per token.
  const latest = useRef({ branch, retry, edit });
  useLayoutEffect(() => {
    latest.current = { branch, retry, edit };
  });
  const actions = useMemo(
    () => ({
      branch: (nodeId: string, seq: number) => latest.current.branch(nodeId, seq),
      retry: () => latest.current.retry(),
      edit: (nodeId: string, seq: number, content: string): Promise<boolean> => latest.current.edit(nodeId, seq, content),
    }),
    [],
  );

  return {
    activeNodeId,
    /** sending from this card goes on a new branch (it has branches of its own) */
    branchesOnSend,
    activeNode,
    activeExhibit: activeNodeId ? exhibits[activeNodeId] : undefined,
    historyIds,
    loadedMessageCount,
    history,
    /** how many history items above the nearest compact card are folded away (0: none) */
    foldedCount,
    nodeModel,
    nodeTokens,
    branchTokens,
    streaming,
    streamWork,
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
    contextLength,
    send,
    stop,
    canRetry,
    ...actions,
    /** A question card's last answer opened `nodeId`: the asking model continues its research there. */
    continueIn: (nodeId: string, prompt: string) => void ask(nodeId, prompt, false),
  };
}
