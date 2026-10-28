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
  /** Swap a node for another in the same place, its children and chats moving across (an optimistic fork or split, once the server answers). */
  replaceNode(oldId: string, node: NodeMeta): void;
  /** Cut a node after its message at `afterIndex`: `tail` (a new child) takes the messages after it and every
   * child the node had; `tangent`, if given, is a new empty child beside it. Mirrors POST /nodes/:id/split. */
  splitNode(nodeId: string, afterIndex: number, tail: NodeMeta, tangent: NodeMeta | null): void;
  /** Fold a node's only child back into it (splitNode undone): its messages are appended, its children
   * move up, and it goes. A selection on the child moves to the node. Mirrors POST /nodes/:id/join. */
  joinChild(nodeId: string): void;
  /** Selecting a node also marks its finished reply read. */
  setActive(nodeId: string | null): void;
}

interface ContentSlice {
  chatsByNode: Record<string, ChatMessage[]>;
  /** nodeId -> reply text so far; a key is present exactly while that node is streaming. */
  streaming: Record<string, string>;
  /** Nodes whose reply finished while another node was selected; cleared when the node is selected. */
  unread: Record<string, true>;
  setChats(nodeId: string, chats: ChatMessage[]): void;
  beginStream(nodeId: string, userMessage: ChatMessage): void;
  appendToken(nodeId: string, text: string): void;
  /** Commit the streamed text as an assistant message (server persists on stream end). */
  endStream(nodeId: string, assistantMessage: ChatMessage): void;
  abortStream(nodeId: string): void;
  /** Bumped to ask the message box for focus: a branch or merge just made a card to write on. */
  composeAt: number;
  requestCompose(): void;
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

/** Point every merge that names `from` as a source at `to` instead: the conversation it took now ends there. */
function moveSources(nodesById: Record<string, NodeMeta>, from: string, to: string) {
  for (const [id, n] of Object.entries(nodesById)) {
    if (n.merge_source_ids?.includes(from)) {
      nodesById[id] = { ...n, merge_source_ids: n.merge_source_ids.map((s) => (s === from ? to : s)) };
    }
  }
}

const byForkIndex = (nodes: Record<string, NodeMeta>) => (a: string, b: string) =>
  (nodes[a]?.fork_index ?? 0) - (nodes[b]?.fork_index ?? 0);

export const useTreeStore = create<TreeState>()((set) => ({
  rootId: null,
  nodesById: {},
  childrenByParent: {},
  activeNodeId: null,
  chatsByNode: {},
  streaming: {},
  unread: {},
  composeAt: 0,
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
      return { rootId, nodesById, childrenByParent, activeNodeId: rootId, chatsByNode: {}, streaming: {}, unread: {} };
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
    set((s) => {
      const old = s.nodesById[node.id];
      // merge sources are shape, and only the tree endpoints report them: a single node's read has none
      return old ? { nodesById: { ...s.nodesById, [node.id]: { ...node, merge_source_ids: old.merge_source_ids } } } : s;
    }),

  removeNode: (nodeId) =>
    set((s) => {
      const node = s.nodesById[nodeId];
      if (!node) return s;
      const gone = new Set<string>();
      const stack = [nodeId];
      while (stack.length) {
        const id = stack.pop()!;
        if (gone.has(id)) continue;
        gone.add(id);
        stack.push(...(s.childrenByParent[id] ?? []));
        for (const candidate of Object.values(s.nodesById)) {
          if (candidate.merge_source_ids?.includes(id)) stack.push(candidate.id);
        }
      }
      const keep = <T,>(r: Record<string, T>) => Object.fromEntries(Object.entries(r).filter(([k]) => !gone.has(k)));
      const childrenByParent = Object.fromEntries(
        Object.entries(keep(s.childrenByParent)).map(([parentId, childIds]) => [
          parentId,
          childIds.filter((id) => !gone.has(id)),
        ]),
      );
      if (node.parent_id && childrenByParent[node.parent_id]) {
        childrenByParent[node.parent_id] = childrenByParent[node.parent_id]!.filter((id) => id !== nodeId);
      }
      let nextActive = node.parent_id;
      while (nextActive && gone.has(nextActive)) {
        nextActive = s.nodesById[nextActive]?.parent_id ?? null;
      }
      return {
        nodesById: keep(s.nodesById),
        childrenByParent,
        chatsByNode: keep(s.chatsByNode),
        unread: keep(s.unread),
        activeNodeId: s.activeNodeId && gone.has(s.activeNodeId) ? nextActive : s.activeNodeId,
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
      moveSources(nodesById, oldId, node.id);
      const children = childrenByParent[oldId];
      if (children) {
        delete childrenByParent[oldId];
        childrenByParent[node.id] = children;
        for (const id of children) nodesById[id] = { ...nodesById[id]!, parent_id: node.id };
      }
      const chatsByNode = { ...s.chatsByNode, [node.id]: s.chatsByNode[oldId] ?? [] };
      delete chatsByNode[oldId];
      return { nodesById, childrenByParent, chatsByNode, activeNodeId: s.activeNodeId === oldId ? node.id : s.activeNodeId };
    }),

  joinChild: (nodeId) =>
    set((s) => {
      const [childId, ...others] = s.childrenByParent[nodeId] ?? [];
      const head = s.chatsByNode[nodeId];
      const rest = childId ? s.chatsByNode[childId] : undefined;
      if (!childId || others.length || !head || !rest) return s;
      if (
        s.nodesById[childId]?.merge_source_ids?.length ||
        Object.values(s.nodesById).some((n) => n.merge_source_ids?.includes(nodeId))
      ) {
        return s;
      }
      const moved = s.childrenByParent[childId] ?? [];
      const nodesById = { ...s.nodesById };
      delete nodesById[childId];
      for (const id of moved) nodesById[id] = { ...nodesById[id]!, parent_id: nodeId };
      moveSources(nodesById, childId, nodeId);
      const childrenByParent = { ...s.childrenByParent, [nodeId]: moved };
      delete childrenByParent[childId];
      const chatsByNode = { ...s.chatsByNode, [nodeId]: [...head, ...rest].map((m, i) => ({ ...m, seq: i })) };
      delete chatsByNode[childId];
      const unread = { ...s.unread };
      delete unread[childId];
      return { nodesById, childrenByParent, chatsByNode, unread, activeNodeId: s.activeNodeId === childId ? nodeId : s.activeNodeId };
    }),

  splitNode: (nodeId, afterIndex, tail, tangent) =>
    set((s) => {
      const chats = s.chatsByNode[nodeId];
      if (!s.nodesById[nodeId] || !chats) return s;
      const moved = s.childrenByParent[nodeId] ?? [];
      const nodesById = { ...s.nodesById, [tail.id]: tail, ...(tangent && { [tangent.id]: tangent }) };
      for (const id of moved) nodesById[id] = { ...nodesById[id]!, parent_id: tail.id };
      moveSources(nodesById, nodeId, tail.id);
      return {
        nodesById,
        childrenByParent: { ...s.childrenByParent, [nodeId]: tangent ? [tail.id, tangent.id] : [tail.id], [tail.id]: moved },
        chatsByNode: {
          ...s.chatsByNode,
          [nodeId]: chats.slice(0, afterIndex + 1),
          [tail.id]: chats.slice(afterIndex + 1).map((m, i) => ({ ...m, seq: i })),
          ...(tangent && { [tangent.id]: [] }),
        },
      };
    }),

  setActive: (nodeId) =>
    set((s) => {
      if (!nodeId || !s.unread[nodeId]) return { activeNodeId: nodeId };
      const unread = { ...s.unread };
      delete unread[nodeId];
      return { activeNodeId: nodeId, unread };
    }),

  requestCompose: () => set((s) => ({ composeAt: s.composeAt + 1 })),

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
        unread: nodeId === s.activeNodeId ? s.unread : { ...s.unread, [nodeId]: true },
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

export const selectIsLeaf = (s: Pick<TreeState, "childrenByParent" | "nodesById">, id: string): boolean =>
  !(s.childrenByParent[id]?.length) &&
  !Object.values(s.nodesById).some((node) => node.merge_source_ids?.includes(id));

export function parentsOf(s: Pick<TreeState, "nodesById">, id: string): string[] {
  const node = s.nodesById[id];
  if (!node) return [];
  const sources = node.merge_source_ids ?? [];
  if (sources.length) {
    return node.parent_id
      ? [node.parent_id, ...sources.filter((source) => source !== node.parent_id).sort()]
      : [...sources].sort();
  }
  return node.parent_id ? [node.parent_id] : [];
}

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

/** The ancestor set through every parent link. */
export function selectThread(s: Pick<TreeState, "nodesById">, id: string): Set<string> {
  const out = new Set<string>();
  const stack = [id];
  while (stack.length) {
    const n = s.nodesById[stack.pop()!];
    if (!n || out.has(n.id)) continue;
    out.add(n.id);
    stack.push(...parentsOf(s, n.id));
  }
  return out;
}

export type ThreadPlanItem = string | { merge: { from: string; plan: ThreadPlanItem[] }[] };

/** Same deterministic graph walk the backend uses; display only. */
export function selectThreadPlan(s: Pick<TreeState, "nodesById">, id: string): ThreadPlanItem[] {
  const ancestors = new Map<string, Set<string>>();
  const anc = (nodeId: string): Set<string> => {
    const cached = ancestors.get(nodeId);
    if (cached) return cached;
    const result = new Set([nodeId]);
    ancestors.set(nodeId, result);
    for (const parent of parentsOf(s, nodeId)) for (const ancestor of anc(parent)) result.add(ancestor);
    return result;
  };
  const order = (a: string, b: string) =>
    (s.nodesById[a]?.created_at ?? "").localeCompare(s.nodesById[b]?.created_at ?? "") || a.localeCompare(b);

  const thread = (nodeId: string, done: Set<string>): ThreadPlanItem[] => {
    if (done.has(nodeId)) return [];
    const parents = parentsOf(s, nodeId);
    if (parents.length === 0) return [nodeId];
    const prefix = parents.length === 1 ? thread(parents[0]!, done) : join(parents, done);
    return [...prefix, nodeId];
  };

  const join = (tips: string[], done: Set<string>): ThreadPlanItem[] => {
    const first = anc(tips[0]!);
    const common = new Set([...first].filter((candidate) => !done.has(candidate) && tips.every((tip) => anc(tip).has(candidate))));
    const heads = [...common]
      .filter((candidate) => ![...common].some((other) => candidate !== other && anc(other).has(candidate)))
      .sort(order);
    const shared = heads.length === 0
      ? []
      : heads.length === 1
        ? thread(heads[0]!, done)
        : join(heads, done);
    const seen = new Set([...done, ...common]);
    const branches: { from: string; plan: ThreadPlanItem[] }[] = [];
    for (const tip of tips) {
      const plan = thread(tip, seen);
      if (plan.length) branches.push({ from: tip, plan });
      for (const card of anc(tip)) seen.add(card);
    }
    return branches.length ? [...shared, { merge: branches }] : shared;
  };

  return thread(id, new Set());
}

/** Tree cards keep gapless outline numbers; merges use independent joint-exhibit labels. */
export function selectExhibits(
  s: Pick<TreeState, "rootId" | "nodesById" | "childrenByParent">,
): Record<string, string> {
  const out: Record<string, string> = {};
  const isMerge = (id: string) => (s.nodesById[id]?.merge_source_ids?.length ?? 0) > 0;
  const number = (id: string, label: string) => {
    if (id in out) return;
    out[id] = label;
    (s.childrenByParent[id] ?? []).filter((child) => !isMerge(child)).forEach((child, i) => number(child, `${label}.${i + 1}`));
  };
  if (s.rootId) number(s.rootId, "1");
  Object.values(s.nodesById)
    .filter((node) => isMerge(node.id))
    .sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id))
    .forEach((node, i) => number(node.id, `J${i + 1}`));
  return out;
}
