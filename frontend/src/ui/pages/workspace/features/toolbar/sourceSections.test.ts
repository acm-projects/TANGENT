import { describe, expect, it } from "vitest";
import type { Source } from "@/api/types";
import { sourceSections } from "./sourceSections";

const src = (id: string, status: Source["status"]): Source => ({
  id, name: id, kind: "pdf", origin: "s2", url: null, thumbnail_url: null, use_count: 0, status,
});

describe("sourceSections", () => {
  it("puts abstract-only sources in their own list and keeps the order within each", () => {
    const { readable, abstractOnly } = sourceSections([
      src("a", "unavailable"), src("b", "ready"), src("c", "processing"), src("d", "unavailable"), src("e", "on_demand"),
    ]);
    expect(readable.map((s) => s.id)).toEqual(["b", "c", "e"]);
    expect(abstractOnly.map((s) => s.id)).toEqual(["a", "d"]);
  });

  it("treats a source with no status as readable", () => {
    expect(sourceSections([src("a", undefined)]).readable).toHaveLength(1);
  });
});
