import { api, forkedProjectIdOf } from "@/api";
import type { ForkInfo } from "@/api";
import type { NodeMeta } from "@/api/types";
import { selectIsLeaf, useTreeStore } from "@/store/treeStore";

/* The map's per-node actions, shared with the chat's "branch" button.
 * Both throw on failure; the caller decides where the error shows. */

/** The write landed in the user's new copy of a shared project: go there and open `nodeId` (the copy's id). */
export function switchToFork(fork: ForkInfo, nodeId: string | null, notice?: string) {
  useTreeStore.getState().requestSwitch({ slug: fork.workspace_slug, projectId: fork.project_id, nodeId }, notice);
}

/** The user already has a copy and the ids they sent belong to the original: send them to it, don't retry. */
export async function redirectToCopy(copyId: string) {
  const { workspace_slug } = await api.projects.get(copyId);
  useTreeStore.getState().requestSwitch({ slug: workspace_slug, projectId: copyId, nodeId: null }, "You already have your own copy.");
}

/** A node's chats: from the store, or the first time this visit from the server, which the store then keeps. */
export async function loadChats(nodeId: string) {
  const cached = useTreeStore.getState().chatsByNode[nodeId];
  if (cached) return cached;
  const { chats } = await api.nodes.get(nodeId);
  // the chat panel may have loaded them meanwhile (and a send started): keep what it has
  if (!useTreeStore.getState().chatsByNode[nodeId]) useTreeStore.getState().setChats(nodeId, chats);
  return useTreeStore.getState().chatsByNode[nodeId] ?? chats;
}

const PENDING = "pending:";

/** A fork the server hasn't confirmed yet: it can't be sent to or forked until it has a real id.
 * Deleting it is queued instead (deleteNode). */
export const isPending = (nodeId: string | null) => Boolean(nodeId?.startsWith(PENDING));

/** Placeholders deleted before the server answered: each waits for the real node (or null if none was made). */
const queuedDeletes = new Map<string, (node: NodeMeta | null) => void>();

/** Real ids that replaced a pending fork. Their card is already on the map, so it doesn't pin in again. */
export const confirmedForks = new Set<string>();

/** Start a tangent: a new child of `nodeId`, selected and ready to prompt.
 * Optimistic: a placeholder child appears at once and is swapped for the server's node when it
 * answers, or removed (selection restored) if the fork fails. */
export async function forkNode(nodeId: string) {
  const store = useTreeStore.getState();
  const parent = store.nodesById[nodeId];
  const previous = store.activeNodeId;
  const tempId = PENDING + crypto.randomUUID();
  if (parent) {
    const siblings = store.childrenByParent[nodeId] ?? [];
    const forkIndex = Math.max(-1, ...siblings.map((id) => store.nodesById[id]?.fork_index ?? 0)) + 1;
    store.addNode({
      ...parent,
      id: tempId,
      parent_id: nodeId,
      fork_index: forkIndex,
      node_type: null,
      title: null,
      summary: null,
      created_at: new Date().toISOString(),
      attachment_kinds: [],
      // a new card, not a copy: the parent may be a merge, and its tokens are its own
      merge_source_ids: [],
      tokens: 0,
    });
    store.setChats(tempId, []);
    store.setActive(tempId);
    store.requestCompose();
  }
  const drop = () => {
    const s = useTreeStore.getState();
    const wasActive = s.activeNodeId === tempId;
    s.removeNode(tempId);
    if (wasActive) s.setActive(previous);
  };

  // the placeholder was deleted meanwhile: hand the outcome to that delete instead of showing it
  const takeQueued = () => {
    const waiting = queuedDeletes.get(tempId);
    queuedDeletes.delete(tempId);
    return waiting;
  };

  let res;
  try {
    res = await api.nodes.fork(nodeId);
  } catch (e) {
    const waiting = takeQueued();
    drop();
    if (waiting) return waiting(null); // nothing was made, so nothing to delete
    const copyId = forkedProjectIdOf(e);
    if (copyId) return redirectToCopy(copyId);
    throw e;
  }
  const { fork, ...child } = res;
  // The new node already lives in the copy; the switch loads that tree and opens it.
  if (fork) {
    takeQueued()?.(null); // shortcut: a fork that landed in a copy stays there; the switch shows it
    drop();
    return switchToFork(fork, child.id);
  }
  const waiting = takeQueued();
  if (waiting) return waiting(child);
  const s = useTreeStore.getState();
  if (!parent) {
    // the parent isn't in the store, so there was no placeholder: just add the node
    s.addNode(child);
    s.setChats(child.id, []);
    s.setActive(child.id);
    return;
  }
  // replaceNode ignores a placeholder that's gone (the tree reloaded, or the parent was deleted meanwhile)
  confirmedForks.add(child.id);
  s.replaceNode(tempId, child);
}

/** Branch from a reply mid-way through a node: the node is cut after it (the rest, and every branch the
 * node had, move down into a new child) and a new tangent starts beside that child, selected.
 * Optimistic like forkNode: placeholders for both appear at once and are swapped for the server's nodes,
 * or the cut is undone if the server refuses. */
export async function splitNode(nodeId: string, afterIndex: number) {
  const store = useTreeStore.getState();
  const node = store.nodesById[nodeId];
  const chats = store.chatsByNode[nodeId];
  if (!node || !chats) return;
  const before = { nodesById: store.nodesById, childrenByParent: store.childrenByParent, activeNodeId: store.activeNodeId };
  const siblings = store.childrenByParent[nodeId] ?? [];
  const nextIndex = Math.max(0, ...siblings.map((id) => store.nodesById[id]?.fork_index ?? 0)) + 1;
  const question = chats.slice(afterIndex + 1).find((m) => m.role === "user")?.content;
  const placeholder = (forkIndex: number, title: string | null): NodeMeta => ({
    ...node,
    id: PENDING + crypto.randomUUID(),
    parent_id: nodeId,
    fork_index: forkIndex,
    title,
    summary: null,
    created_at: new Date().toISOString(),
    attachment_kinds: [],
    // a new card, not a copy: the node it was cut from may be a merge, and its tokens stay with it
    merge_source_ids: [],
    tokens: 0,
  });
  const tail = placeholder(nextIndex, question?.slice(0, 40) ?? null);
  const tangent = { ...placeholder(nextIndex + 1, null), node_type: null };
  store.splitNode(nodeId, afterIndex, tail, tangent);
  store.setActive(tangent.id);
  store.requestCompose();

  // a placeholder deleted meanwhile hands its real node (or null: none was made) to that delete
  const settle = (tempId: string, real: NodeMeta | null) => {
    const waiting = queuedDeletes.get(tempId);
    queuedDeletes.delete(tempId);
    if (waiting) waiting(real);
    return Boolean(waiting);
  };
  // shortcut: rollback restores the map as it was before the cut, so a structure change made elsewhere
  // during the request is lost with it; fine for one round trip, revisit if splits get slow
  const undo = () =>
    useTreeStore.setState((s) => {
      const chatsByNode = { ...s.chatsByNode, [nodeId]: chats };
      delete chatsByNode[tail.id];
      delete chatsByNode[tangent.id];
      const lost = s.activeNodeId === tail.id || s.activeNodeId === tangent.id;
      return { ...before, chatsByNode, activeNodeId: lost ? before.activeNodeId : s.activeNodeId };
    });

  let res;
  try {
    res = await api.nodes.split(nodeId, afterIndex, true);
  } catch (e) {
    settle(tail.id, null);
    settle(tangent.id, null);
    undo();
    const copyId = forkedProjectIdOf(e);
    if (copyId) return redirectToCopy(copyId);
    throw e;
  }
  if (res.fork) {
    // shortcut: like forkNode, a split that landed in a copy stays there; the switch shows it
    settle(tail.id, null);
    settle(tangent.id, null);
    undo();
    return switchToFork(res.fork, res.tangent?.id ?? res.tail.id);
  }
  const s = useTreeStore.getState();
  for (const [temp, real] of [[tail, res.tail], [tangent, res.tangent]] as const) {
    if (!real || settle(temp.id, real)) continue;
    confirmedForks.add(real.id);
    s.replaceNode(temp.id, real);
  }
}

/** Merge two cards. A card and its only branch, in a straight line, become one card: the deeper one's
 * messages are appended to the shallower (a split undone). Two cards at the ends of separate branches join
 * into a new card carrying both (mergeBranches). Optimistic either way: the map changes at once and goes
 * back if the server refuses. Anything else throws a message saying why it can't merge. */
export async function mergeNodes(a: string, b: string) {
  const store = useTreeStore.getState();
  const [na, nb] = [store.nodesById[a], store.nodesById[b]];
  if (!na || !nb || a === b) return;
  const [parent, child] = nb.parent_id === a ? [na, nb] : na.parent_id === b ? [nb, na] : [null, null];
  if (!parent || !child) return mergeBranches(a, b);
  if (child.merge_source_ids?.length) throw new Error("A merge can't be folded into one of its sources.");
  if (Object.values(store.nodesById).some((node) => node.merge_source_ids?.includes(parent.id))) {
    throw new Error("A card that feeds a merge can't take its child back in.");
  }
  if ((store.childrenByParent[parent.id] ?? []).length > 1) {
    throw new Error("Other tangents branch from that card, so it can't take this one back in.");
  }
  if (isPending(a) || isPending(b)) throw new Error("That card is still being made. Try again in a moment.");
  if (parent.id in store.streaming || child.id in store.streaming) throw new Error("Wait for the reply to finish first.");

  await Promise.all([loadChats(parent.id), loadChats(child.id)]);
  const now = useTreeStore.getState();
  const before = {
    nodesById: now.nodesById,
    childrenByParent: now.childrenByParent,
    chatsByNode: now.chatsByNode,
    activeNodeId: now.activeNodeId,
  };
  now.joinChild(parent.id);
  if (useTreeStore.getState().activeNodeId !== parent.id) useTreeStore.getState().setActive(parent.id);
  useTreeStore.getState().requestCompose();

  let res;
  try {
    res = await api.nodes.join(parent.id);
  } catch (e) {
    // shortcut: like splitNode's, the rollback restores the map as it was, dropping any other change meanwhile
    useTreeStore.setState(before);
    const copyId = forkedProjectIdOf(e);
    if (copyId) return redirectToCopy(copyId);
    throw e;
  }
  const { fork, ...joined } = res;
  if (fork) {
    useTreeStore.setState(before);
    return switchToFork(fork, joined.id);
  }
  useTreeStore.getState().updateNode(joined);
}

/** Two leaves become a new two-parent card (POST /nodes/merge). */
async function mergeBranches(a: string, b: string) {
  const store = useTreeStore.getState();
  if (!selectIsLeaf(store, a) || !selectIsLeaf(store, b)) {
    throw new Error("Only cards at the ends of their branches can be merged.");
  }
  if (a === b) throw new Error("Pick two different cards to merge.");
  if (isPending(a) || isPending(b)) throw new Error("That card is still being made. Try again in a moment.");
  if (a in store.streaming || b in store.streaming) throw new Error("Wait for the reply to finish first.");
  const siblings = store.childrenByParent[a] ?? [];
  const temp: NodeMeta = {
    ...store.nodesById[a]!,
    id: PENDING + crypto.randomUUID(),
    parent_id: a,
    fork_index: Math.max(0, ...siblings.map((id) => store.nodesById[id]?.fork_index ?? 0)) + 1,
    title: null,
    summary: null,
    created_at: new Date().toISOString(),
    attachment_kinds: [],
    tokens: 0,
    merge_source_ids: [a, b],
  };
  const previous = store.activeNodeId;
  store.addNode(temp);
  store.setChats(temp.id, []);
  store.setActive(temp.id);
  store.requestCompose();

  const queued = () => {
    const waiting = queuedDeletes.get(temp.id);
    queuedDeletes.delete(temp.id);
    return waiting;
  };
  const drop = () => {
    const s = useTreeStore.getState();
    const wasActive = s.activeNodeId === temp.id;
    s.removeNode(temp.id);
    if (wasActive) s.setActive(previous);
  };

  let res;
  try {
    res = await api.nodes.merge([a, b]);
  } catch (e) {
    queued()?.(null);
    drop();
    const copyId = forkedProjectIdOf(e);
    if (copyId) return redirectToCopy(copyId);
    throw e;
  }
  const { fork, ...merged } = res;
  if (fork) {
    queued()?.(null);
    drop();
    return switchToFork(fork, merged.id);
  }
  const real = merged;
  const waiting = queued();
  if (waiting) return waiting(real);
  confirmedForks.add(real.id);
  useTreeStore.getState().replaceNode(temp.id, real);
}

/** Delete a node and everything branching from it. Optimistic: the branch goes at once and is put
 * back (with its chats, and the selection if it was inside) if the server refuses.
 * A placeholder fork goes at once too; its delete is sent as soon as the server confirms the real node. */
export async function deleteNode(nodeId: string) {
  const store = useTreeStore.getState();
  const gone = new Set([nodeId]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const id of gone) {
      for (const child of store.childrenByParent[id] ?? []) {
        if (!gone.has(child)) {
          gone.add(child);
          changed = true;
        }
      }
    }
    for (const node of Object.values(store.nodesById)) {
      if (!gone.has(node.id) && node.merge_source_ids?.some((source) => gone.has(source))) {
        gone.add(node.id);
        changed = true;
      }
    }
  }
  const ids = [...gone];
  const nodes = ids.flatMap((id) => store.nodesById[id] ?? []);
  const chats = ids.flatMap((id) => (store.chatsByNode[id] ? [[id, store.chatsByNode[id]] as const] : []));
  let previous = store.activeNodeId;
  store.removeNode(nodeId);
  if (isPending(nodeId)) {
    const real = await new Promise<NodeMeta | null>((res) => queuedDeletes.set(nodeId, res));
    if (!real) return;
    // a placeholder has no children: restoring means putting the real node back where it was
    nodes.splice(0, 1, real);
    if (chats.length) chats.splice(0, 1, [real.id, chats[0]![1]]);
    ids.splice(0, 1, real.id);
    if (previous === nodeId) previous = real.id;
    nodeId = real.id;
  }
  try {
    await api.nodes.delete(nodeId);
  } catch (e) {
    const now = () => useTreeStore.getState(); // each add changes the state, so read it fresh
    const remaining = new Map(nodes.map((node) => [node.id, node]));
    while (remaining.size) {
      const ready = [...remaining.values()].filter((node) => {
        const parents = [...(node.parent_id ? [node.parent_id] : []), ...(node.merge_source_ids ?? [])];
        return parents.every((parent) => !remaining.has(parent));
      });
      if (!ready.length) throw new Error("Could not restore the deleted branch because its parent graph is cyclic.");
      for (const n of ready) {
        if (n.parent_id && now().nodesById[n.parent_id] && !now().nodesById[n.id]) now().addNode(n);
        remaining.delete(n.id);
      }
    }
    for (const [id, c] of chats) if (now().nodesById[id]) now().setChats(id, c);
    // removeNode moved a selection inside the branch to its parent; put it back unless the user has moved on
    const parent = nodes[0]?.parent_id ?? null;
    if (previous && ids.includes(previous) && now().activeNodeId === parent) now().setActive(previous);
    throw e;
  }
}
