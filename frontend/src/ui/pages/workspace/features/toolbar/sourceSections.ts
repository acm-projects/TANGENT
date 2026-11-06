import type { Source } from "@/api/types";

/** Keep node-scoped uploads together so their visibility is clear in the Sources panel. */
export function sourceSections(sources: Source[]): {
  nodeLevel: Source[];
  globalReadable: Source[];
  globalAbstractOnly: Source[];
} {
  const nodeLevel = sources.filter((s) => s.scope === "node");
  const globalSources = sources.filter((s) => s.scope === "global");
  return {
    nodeLevel,
    globalReadable: globalSources.filter((s) => s.status !== "unavailable"),
    globalAbstractOnly: globalSources.filter((s) => s.status === "unavailable"),
  };
}
