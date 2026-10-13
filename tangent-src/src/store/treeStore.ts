import { create } from "zustand";
import type { ChatMessage, NodeMeta } from "@/api/types";

/**
 * Two slices, on purpose:
 *  - structure: nodesById / childrenByParent / activeNodeId. Graph + breadcrumb selectors read ONLY this.
 *  - content:   chatsByNode / streaming. Token appends touch ONLY this.
 * A token therefore never invalidates the ReactFlow node/edge derivation.
 */
interface StructureSlice {
  rootId: string | null;
  nodesById: Record<string, NodeMeta>;
  childrenByParent: Record<string, string[]>; // ordered by fork_index
  activeNodeId: string | null;
  hydrateTree(rootId: string | null, nodes: NodeMeta[]): void;
  addNode(node: NodeMeta): void;
  /** Replace an existing node's metadata (title, tags) without touching tree shape. */
  updateNode(node: NodeMeta): void;
  setActive(nodeId: string | null): void;
}

interface ContentSlice {
  chatsByNode: Record<string, ChatMessage[]>;
  streaming: { nodeId: string; text: string } | null;
  setChats(nodeId: string, chats: ChatMessage[]): void;
  beginStream(nodeId: string, userMessage: ChatMessage): void;
  appendToken(text: string): void;
  /** Commit the streamed text as an assistant message (server persists on stream end). */
  endStream(assistantMessage: ChatMessage): void;
  abortStream(): void;
}

export type TreeState = StructureSlice & ContentSlice;

const byForkIndex = (nodes: Record<string, NodeMeta>) => (a: string, b: string) =>
  (nodes[a]?.fork_index ?? 0) - (nodes[b]?.fork_index ?? 0);

export const useTreeStore = create<TreeState>()((set) => ({
  rootId: null,
  nodesById: {},
  childrenByParent: {},
  activeNodeId: null,
  chatsByNode: {},
  streaming: null,

  hydrateTree: (rootId, nodes) =>
    set(() => {
      const nodesById: Record<string, NodeMeta> = {};
      const childrenByParent: Record<string, string[]> = {};
      for (const n of nodes) {
        nodesById[n.id] = n;
        if (n.parent_id) (childrenByParent[n.parent_id] ??= []).push(n.id);
      }
      for (const k of Object.keys(childrenByParent)) childrenByParent[k]!.sort(byForkIndex(nodesById));
      return { rootId, nodesById, childrenByParent, activeNodeId: rootId, chatsByNode: {}, streaming: null };
    }),

  addNode: (node) =>
    set((s) => {
      const nodesById = { ...s.nodesById, [node.id]: node };
      const childrenByParent = { ...s.childrenByParent };
      if (node.parent_id) {
        childrenByParent[node.parent_id] = [...(childrenByParent[node.parent_id] ?? []), node.id].sort(
          byForkIndex(nodesById),
        );
      }
      return { nodesById, childrenByParent, rootId: s.rootId ?? (node.parent_id ? null : node.id) };
    }),

  updateNode: (node) =>
    set((s) => (s.nodesById[node.id] ? { nodesById: { ...s.nodesById, [node.id]: node } } : s)),

  setActive: (nodeId) => set({ activeNodeId: nodeId }),

  setChats: (nodeId, chats) => set((s) => ({ chatsByNode: { ...s.chatsByNode, [nodeId]: chats } })),

  beginStream: (nodeId, userMessage) =>
    set((s) => ({
      chatsByNode: { ...s.chatsByNode, [nodeId]: [...(s.chatsByNode[nodeId] ?? []), userMessage] },
      streaming: { nodeId, text: "" },
    })),

  appendToken: (text) =>
    set((s) => (s.streaming ? { streaming: { ...s.streaming, text: s.streaming.text + text } } : s)),

  endStream: (assistantMessage) =>
    set((s) => {
      if (!s.streaming) return s;
      const { nodeId } = s.streaming;
      return {
        chatsByNode: { ...s.chatsByNode, [nodeId]: [...(s.chatsByNode[nodeId] ?? []), assistantMessage] },
        streaming: null,
      };
    }),

  abortStream: () => set({ streaming: null }),
}));

// ---- Pure selectors (structure only). Usage: useTreeStore((s) => selectBreadcrumb(s, id)) with useShallow. ----

export const selectIsLeaf = (s: Pick<TreeState, "childrenByParent">, id: string): boolean =>
  !(s.childrenByParent[id]?.length);

/** root -> node. Guards against cycles from corrupt data. */
export function selectBreadcrumb(s: Pick<TreeState, "nodesById">, id: string): NodeMeta[] {
  const out: NodeMeta[] = [];
  const seen = new Set<string>();
  let cur: NodeMeta | undefined = s.nodesById[id];
  while (cur && !seen.has(cur.id)) {
    seen.add(cur.id);
    out.push(cur);
    cur = cur.parent_id ? s.nodesById[cur.parent_id] : undefined;
  }
  return out.reverse();
}
