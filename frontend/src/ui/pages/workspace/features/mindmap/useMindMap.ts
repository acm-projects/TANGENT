import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, apiErrorMessage } from "@/api";
import { projectPath } from "@/ui/features/auth/paths";
import { useTreeStore } from "@/store/treeStore";
import { redirectToCopy } from "./nodeActions";

/* Loads a project's tree into the shared tree store. The map then renders
 * from the store, and so does every other feature on the page.
 *
 * It also owns project switching: a sharee's first edit lands in their own copy,
 * so anything that learns of the copy asks the store for a switch and this hook
 * navigates there, then opens the requested node once that tree has loaded. */

export type MindMapStatus = { status: "loading" } | { status: "ready" } | { status: "error"; message: string };

export function useMindMap(projectId: string): MindMapStatus {
  const router = useRouter();
  const [state, setState] = useState<MindMapStatus>({ status: "loading" });
  const pendingSwitch = useTreeStore((s) => s.pendingSwitch);

  useEffect(() => {
    // replace, not push: Back would land on the original, which only redirects here again.
    if (pendingSwitch && pendingSwitch.projectId !== projectId) {
      router.replace(projectPath(pendingSwitch.slug, pendingSwitch.projectId));
    }
  }, [pendingSwitch, projectId, router]);

  useEffect(() => {
    let cancelled = false;
    const treeRequest = api.trees.forProject(projectId);
    treeRequest.catch(() => {}); // awaited below; this only stops an unhandled rejection if we redirect first
    (async () => {
      const project = await api.projects.get(projectId);
      if (cancelled) return;
      // A sharee who already has a copy never edits the original (also covers a refresh on its URL).
      if (project.forked_project_id) return void (await redirectToCopy(project.forked_project_id));
      const { tree, nodes } = await treeRequest;
      if (cancelled) return;
      const store = useTreeStore.getState();
      store.hydrateTree(tree.root_node_id, nodes);
      store.setProject(project);
      const next = store.pendingSwitch;
      if (next?.projectId === projectId) {
        store.setActive(next.nodeId);
        store.clearSwitch();
      } else {
        // hydrateTree selects the root; the workspace opens with nothing
        // selected instead (Figma "Normal": "Select a node to start chatting.").
        store.setActive(null);
        store.setNotice(null);
      }
      setState({ status: "ready" });
    })().catch((e: unknown) => {
      if (!cancelled) setState({ status: "error", message: apiErrorMessage(e, "Could not load this tree.") });
    });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  return state;
}
