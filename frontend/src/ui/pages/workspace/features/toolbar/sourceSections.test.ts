import { describe, expect, it } from "vitest";
import type { Source } from "@/api/types";
import { sourceSections } from "./sourceSections";

const src = (id: string, status: Source["status"]): Source => ({
  id, name: id, kind: "pdf", origin: "s2", scope: "global", node_id: null, url: null, thumbnail_url: null, use_count: 0, status,
});

describe("sourceSections", () => {
  it("puts abstract-only sources in their own list and keeps the order within each", () => {
    const { globalReadable, globalAbstractOnly } = sourceSections([
      src("a", "unavailable"), src("b", "ready"), src("c", "processing"), src("d", "unavailable"), src("e", "on_demand"),
    ]);
    expect(globalReadable.map((s) => s.id)).toEqual(["b", "c", "e"]);
    expect(globalAbstractOnly.map((s) => s.id)).toEqual(["a", "d"]);
  });

  it("treats a source with no status as readable", () => {
    expect(sourceSections([src("a", undefined)]).globalReadable).toHaveLength(1);
  });

  it("keeps node-level sources in their own section regardless of status", () => {
    const node = { ...src("node", "processing"), scope: "node" as const };
    const sections = sourceSections([node, src("project", "ready")]);
    expect(sections.nodeLevel.map((s) => s.id)).toEqual(["node"]);
    expect(sections.globalReadable.map((s) => s.id)).toEqual(["project"]);
  });
});
