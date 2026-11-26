import { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/api";
import { caseFacts, type CaseFacts } from "./sketch";

/* Each card's photo and filing come from its project's real tree. A card can be drawn twice
 * (in its folder and in the grid), and the board files every case by them, so trees are fetched once per project and
 * shared through this cache, which Board makes fresh each visit: coming back
 * from a workspace shows the case as it is now.
 *
 * Fetching a tree the owner has never opened creates it (one empty root), the
 * same as opening the project would. A sharee gets 404 until the owner has
 * opened it; that card shows no photo and is filed as open. */

export type TreeCache = Map<string, Promise<CaseFacts | null>>;
export const TreePreviews = createContext<TreeCache>(new Map());

/** The case's facts, fetched once per board visit. */
export function factsFor(cache: TreeCache, projectId: string) {
  if (!cache.has(projectId)) {
    cache.set(projectId, api.trees.forProject(projectId).then((t) => caseFacts(t), () => null));
  }
  return cache.get(projectId)!;
}

/** One card's facts: undefined while loading, null when there is no tree to read. */
export function useTreePreview(projectId: string) {
  const cache = useContext(TreePreviews);
  const [facts, setFacts] = useState<CaseFacts | null | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    void factsFor(cache, projectId).then((f) => !cancelled && setFacts(f));
    return () => {
      cancelled = true;
    };
  }, [cache, projectId]);

  return facts;
}

/** Every case's facts at once, for filing the board: null until all of them are in. */
export function useCaseFiling(cache: TreeCache, projectIds: string[]) {
  const [filed, setFiled] = useState<{ key: string; facts: Map<string, CaseFacts | null> } | null>(null);
  const key = projectIds.join(",");
  useEffect(() => {
    let cancelled = false;
    const ids = key ? key.split(",") : [];
    void Promise.all(ids.map((id) => factsFor(cache, id))).then((all) => {
      if (!cancelled) setFiled({ key, facts: new Map(ids.map((id, i) => [id, all[i] ?? null])) });
    });
    return () => {
      cancelled = true;
    };
  }, [cache, key]);
  return filed?.key === key ? filed.facts : null;
}
