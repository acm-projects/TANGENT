import { api, forkedProjectIdOf } from "@/api";
import type { ForkInfo } from "@/api";
import { useTreeStore } from "@/store/treeStore";

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

const PENDING = "pending:";

/** A fork the server hasn't confirmed yet: it can't be sent to, forked or deleted until it has a real id. */
export const isPending = (nodeId: string | null) => Boolean(nodeId?.startsWith(PENDING));

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
    });
    store.setChats(tempId, []);
    store.setActive(tempId);
  }
  const drop = () => {
    const s = useTreeStore.getState();
    const wasActive = s.activeNodeId === tempId;
    s.removeNode(tempId);
    if (wasActive) s.setActive(previous);
  };

  let res;
  try {
    res = await api.nodes.fork(nodeId);
  } catch (e) {
    drop();
    const copyId = forkedProjectIdOf(e);
    if (copyId) return redirectToCopy(copyId);
    throw e;
  }
  const { fork, ...child } = res;
  // The new node already lives in the copy; the switch loads that tree and opens it.
  if (fork) {
    drop();
    return switchToFork(fork, child.id);
  }
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

/** Delete a node and everything branching from it. Optimistic: the branch goes at once and is put
 * back (with its chats, and the selection if it was inside) if the server refuses. */
export async function deleteNode(nodeId: string) {
  const store = useTreeStore.getState();
  // parents before children, so each restored node has its parent back already
  const ids = [nodeId];
  for (let i = 0; i < ids.length; i++) ids.push(...(store.childrenByParent[ids[i]!] ?? []));
  const nodes = ids.flatMap((id) => store.nodesById[id] ?? []);
  const chats = ids.flatMap((id) => (store.chatsByNode[id] ? [[id, store.chatsByNode[id]] as const] : []));
  const previous = store.activeNodeId;
  store.removeNode(nodeId);
  try {
    await api.nodes.delete(nodeId);
  } catch (e) {
    const now = () => useTreeStore.getState(); // each add changes the state, so read it fresh
    for (const n of nodes) if (n.parent_id && now().nodesById[n.parent_id] && !now().nodesById[n.id]) now().addNode(n);
    for (const [id, c] of chats) if (now().nodesById[id]) now().setChats(id, c);
    // removeNode moved a selection inside the branch to its parent; put it back unless the user has moved on
    const parent = nodes[0]?.parent_id ?? null;
    if (previous && ids.includes(previous) && now().activeNodeId === parent) now().setActive(previous);
    throw e;
  }
}
