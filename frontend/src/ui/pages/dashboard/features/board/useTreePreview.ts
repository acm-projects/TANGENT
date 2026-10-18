import { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/api";
import { sketchTree, type SketchPin } from "./sketch";

/* Each card's preview is its project's real tree. A card can be drawn twice
 * (in its folder and in the grid), so trees are fetched once per project and
 * shared through this cache, which Board makes fresh each visit: coming back
 * from a workspace shows the tree as it is now.
 *
 * Fetching a tree the owner has never opened creates it (one empty root), the
 * same as opening the project would. A sharee gets 404 until the owner has
 * opened it; that card shows no preview. */

export type TreeCache = Map<string, Promise<SketchPin[] | null>>;
export const TreePreviews = createContext<TreeCache>(new Map());

export function useTreePreview(projectId: string) {
  const cache = useContext(TreePreviews);
  const [pins, setPins] = useState<SketchPin[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!cache.has(projectId)) {
      cache.set(projectId, api.trees.forProject(projectId).then(sketchTree, () => null));
    }
    void cache.get(projectId)!.then((p) => !cancelled && setPins(p));
    return () => {
      cancelled = true;
    };
  }, [cache, projectId]);

  return pins;
}
