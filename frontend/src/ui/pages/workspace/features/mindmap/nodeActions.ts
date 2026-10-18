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

/** Start a tangent: a new child of `nodeId`, selected and ready to prompt. */
export async function forkNode(nodeId: string) {
  let res;
  try {
    res = await api.nodes.fork(nodeId);
  } catch (e) {
    const copyId = forkedProjectIdOf(e);
    if (copyId) return redirectToCopy(copyId);
    throw e;
  }
  const { fork, ...child } = res;
  // The new node already lives in the copy; the switch loads that tree and opens it.
  if (fork) return switchToFork(fork, child.id);
  const store = useTreeStore.getState();
  store.addNode(child);
  store.setChats(child.id, []);
  store.setActive(child.id);
}

/** Delete a node and everything branching from it. */
export async function deleteNode(nodeId: string) {
  await api.nodes.delete(nodeId);
  useTreeStore.getState().removeNode(nodeId);
}
