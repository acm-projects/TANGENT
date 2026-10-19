import { create } from "zustand";
import type { ChatMessage, NodeMeta, ProjectDetail } from "@/api/types";

/**
 * Two slices, on purpose:
 *  - structure: nodesById / childrenByParent / activeNodeId. Graph + breadcrumb selectors read ONLY this.
 *  - content:   chatsByNode / streaming (partial reply text per node, so nodes stream independently).
 *               Token appends touch ONLY this.
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
  /** Drop a node and its subtree (the server cascades the same way). Selection moves to the parent. */
  removeNode(nodeId: string): void;
  /** Swap a childless node for another in the same place (an optimistic fork, once the server answers). */
  replaceNode(oldId: string, node: NodeMeta): void;
  setActive(nodeId: string | null): void;
}

interface ContentSlice {
  chatsByNode: Record<string, ChatMessage[]>;
  /** nodeId -> reply text so far; a key is present exactly while that node is streaming. */
  streaming: Record<string, string>;
  setChats(nodeId: string, chats: ChatMessage[]): void;
  beginStream(nodeId: string, userMessage: ChatMessage): void;
  appendToken(nodeId: string, text: string): void;
  /** Commit the streamed text as an assistant message (server persists on stream end). */
  endStream(nodeId: string, assistantMessage: ChatMessage): void;
  abortStream(nodeId: string): void;
}

/**
 * State that outlives a project switch (a sharee's first edit moves them into their own copy), so
 * hydrateTree leaves it alone. `useMindMap` performs the navigation and consumes `pendingSwitch`.
 */
interface SwitchSlice {
  project: ProjectDetail | null;
  /** Where to go next; nodeId is opened once that project's tree has loaded. */
  pendingSwitch: { slug: string; projectId: string; nodeId: string | null } | null;
  /** A message that must survive the navigation ("You already have your own copy.", a stream error). */
  notice: string | null;
  setProject(project: ProjectDetail | null): void;
  requestSwitch(target: { slug: string; projectId: string; nodeId: string | null }, notice?: string): void;
  clearSwitch(): void;
  setNotice(notice: string | null): void;
}

export type TreeState = StructureSlice & ContentSlice & SwitchSlice;

const byForkIndex = (nodes: Record<string, NodeMeta>) => (a: string, b: string) =>
  (nodes[a]?.fork_index ?? 0) - (nodes[b]?.fork_index ?? 0);

export const useTreeStore = create<TreeState>()((set) => ({
  rootId: null,
  nodesById: {},
  childrenByParent: {},
  activeNodeId: null,
  chatsByNode: {},
  streaming: {},
  project: null,
  pendingSwitch: null,
  notice: null,

  setProject: (project) => set({ project }),
  requestSwitch: (pendingSwitch, notice) => set((s) => ({ pendingSwitch, notice: notice ?? s.notice })),
  clearSwitch: () => set({ pendingSwitch: null }),
  setNotice: (notice) => set({ notice }),

  hydrateTree: (rootId, nodes) =>
    set(() => {
      const nodesById: Record<string, NodeMeta> = {};
      const childrenByParent: Record<string, string[]> = {};
      for (const n of nodes) {
        nodesById[n.id] = n;
        if (n.parent_id) (childrenByParent[n.parent_id] ??= []).push(n.id);
      }
      for (const k of Object.keys(childrenByParent)) childrenByParent[k]!.sort(byForkIndex(nodesById));
      return { rootId, nodesById, childrenByParent, activeNodeId: rootId, chatsByNode: {}, streaming: {} };
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

  removeNode: (nodeId) =>
    set((s) => {
      const node = s.nodesById[nodeId];
      if (!node) return s;
      const gone = new Set<string>();
      const stack = [nodeId];
      while (stack.length) {
        const id = stack.pop()!;
        gone.add(id);
        stack.push(...(s.childrenByParent[id] ?? []));
      }
      const keep = <T,>(r: Record<string, T>) => Object.fromEntries(Object.entries(r).filter(([k]) => !gone.has(k)));
      const childrenByParent = keep(s.childrenByParent);
      if (node.parent_id && childrenByParent[node.parent_id]) {
        childrenByParent[node.parent_id] = childrenByParent[node.parent_id]!.filter((id) => id !== nodeId);
      }
      return {
        nodesById: keep(s.nodesById),
        childrenByParent,
        chatsByNode: keep(s.chatsByNode),
        activeNodeId: s.activeNodeId && gone.has(s.activeNodeId) ? node.parent_id : s.activeNodeId,
      };
    }),

  replaceNode: (oldId, node) =>
    set((s) => {
      if (!s.nodesById[oldId]) return s;
      const nodesById = { ...s.nodesById, [node.id]: node };
      delete nodesById[oldId];
      const childrenByParent = { ...s.childrenByParent };
      if (node.parent_id) {
        childrenByParent[node.parent_id] = (childrenByParent[node.parent_id] ?? [])
          .map((id) => (id === oldId ? node.id : id))
          .sort(byForkIndex(nodesById));
      }
      const chatsByNode = { ...s.chatsByNode, [node.id]: s.chatsByNode[oldId] ?? [] };
      delete chatsByNode[oldId];
      return { nodesById, childrenByParent, chatsByNode, activeNodeId: s.activeNodeId === oldId ? node.id : s.activeNodeId };
    }),

  setActive: (nodeId) => set({ activeNodeId: nodeId }),

  setChats: (nodeId, chats) => set((s) => ({ chatsByNode: { ...s.chatsByNode, [nodeId]: chats } })),

  beginStream: (nodeId, userMessage) =>
    set((s) => ({
      chatsByNode: { ...s.chatsByNode, [nodeId]: [...(s.chatsByNode[nodeId] ?? []), userMessage] },
      streaming: { ...s.streaming, [nodeId]: "" },
    })),

  // Events for a node that is no longer streaming (e.g. the tree was re-hydrated) are dropped.
  appendToken: (nodeId, text) =>
    set((s) => (nodeId in s.streaming ? { streaming: { ...s.streaming, [nodeId]: s.streaming[nodeId] + text } } : s)),

  endStream: (nodeId, assistantMessage) =>
    set((s) => {
      if (!(nodeId in s.streaming)) return s;
      const streaming = { ...s.streaming };
      delete streaming[nodeId];
      return {
        chatsByNode: { ...s.chatsByNode, [nodeId]: [...(s.chatsByNode[nodeId] ?? []), assistantMessage] },
        streaming,
      };
    }),

  abortStream: (nodeId) =>
    set((s) => {
      if (!(nodeId in s.streaming)) return s;
      const streaming = { ...s.streaming };
      delete streaming[nodeId];
      return { streaming };
    }),
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
