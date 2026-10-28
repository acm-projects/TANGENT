import type { Source } from "@/api/types";

/** The Sources panel's two lists, each in server order: sources whose full text the agents can read (or
 * will be able to), then abstract-only ones, which are shown last under their own heading. */
export function sourceSections(sources: Source[]): { readable: Source[]; abstractOnly: Source[] } {
  const abstractOnly = sources.filter((s) => s.status === "unavailable");
  return { readable: sources.filter((s) => s.status !== "unavailable"), abstractOnly };
}
