import { describe, expect, it } from "vitest";
import type { NodeMeta, TreeResponse } from "@/api/types";
import { nextProjectName } from "./nextName";
import { caseFacts, lastWorked, leanOf, tiltOf } from "./sketch";

const node = (id: string, parent: string | null, fork_index: number, created_at: string): NodeMeta => ({
  id, tree_id: "t", project_id: "p", parent_id: parent, fork_index, node_type: null, status: "active",
  title: null, summary: null, model: null, tokens: 0, created_by_id: "u", created_at,
});
const tree = (root: string | null, nodes: NodeMeta[]): TreeResponse => ({
  tree: { id: "t", project_id: "p", root_node_id: root, created_at: "" },
  nodes,
});

const DAY = 86_400_000;
const NOW = Date.parse("2026-11-26T12:00:00Z");
const ago = (days: number) => new Date(NOW - days * DAY).toISOString();

describe("caseFacts", () => {
  it("draws every card inside the photo's frame, each string from a card down to its child", () => {
    const { sketch, cards } = caseFacts(tree("r", [
      node("r", null, 0, ago(3)), node("a", "r", 0, ago(2)), node("b", "r", 1, ago(2)), node("c", "a", 0, ago(1)),
    ]), NOW);
    expect(cards).toBe(4);
    expect(sketch.strings).toHaveLength(3);
    const { box } = sketch;
    for (const c of sketch.cards) {
      expect(c.x).toBeGreaterThanOrEqual(box.x);
      expect(c.x + c.w).toBeLessThanOrEqual(box.x + box.w);
      expect(c.y).toBeGreaterThanOrEqual(box.y);
      expect(c.y + c.h).toBeLessThanOrEqual(box.y + box.h);
    }
    expect(sketch.cards.filter((c) => c.root)).toHaveLength(1);
  });

  it("strings the thread to the newest card in red, through both sides of a merge", () => {
    const merged = { ...node("m", "a", 0, ago(0)), merge_source_ids: ["a", "b"] };
    const { sketch } = caseFacts(tree("r", [node("r", null, 0, ago(3)), node("a", "r", 0, ago(2)), node("b", "r", 1, ago(2)), merged]), NOW);
    expect(sketch.cards.filter((c) => c.onPath)).toHaveLength(4);
    expect(sketch.cards.find((c) => c.latest)?.onPath).toBe(true);
    // the merged card hangs from both the cards it joins
    expect(sketch.strings.filter((s) => s.onPath)).toHaveLength(4);
  });

  it("files a case: open while worked on, cold after three quiet weeks, closed once every branch has ended", () => {
    const ended = { by: "user" as const, at: ago(1) };
    expect(caseFacts(tree("r", [node("r", null, 0, ago(2)), node("a", "r", 0, ago(1))]), NOW).status).toBe("open");
    expect(caseFacts(tree("r", [node("r", null, 0, ago(40)), node("a", "r", 0, ago(30))]), NOW).status).toBe("cold");
    expect(caseFacts(tree("r", [node("r", null, 0, ago(40)), { ...node("a", "r", 0, ago(30)), resolved: ended }]), NOW).status).toBe("closed");
    // a case with only its first card is never closed
    expect(caseFacts(tree("r", [node("r", null, 0, ago(1))]), NOW).status).toBe("open");
  });

  it("draws nothing for no tree", () => {
    expect(caseFacts(tree(null, []), NOW).sketch.cards).toEqual([]);
  });
});

describe("lastWorked", () => {
  it("says it the way a note on a file would", () => {
    expect(lastWorked(ago(0), NOW)).toBe("today");
    expect(lastWorked(ago(1), NOW)).toBe("yesterday");
    expect(lastWorked(ago(4), NOW)).toBe("4 days ago");
  });
});

describe("nextProjectName", () => {
  it("takes the smallest free number", () => {
    expect(nextProjectName([])).toBe("Case (1)");
    expect(nextProjectName(["Case (1)", "Case (3)", "Gym"])).toBe("Case (2)");
  });
});

describe("leanOf", () => {
  it("tips each card its tilt's way by 0.6–2°, at most 4px off the row, the same every time", () => {
    for (const id of ["p1", "p2", "a-much-longer-project-id", "00000000-0000-0000-0000-000000000007"]) {
      const { rotate, y } = leanOf(id);
      expect(Math.sign(rotate)).toBe(tiltOf(id));
      expect(Math.abs(rotate)).toBeGreaterThanOrEqual(0.6);
      expect(Math.abs(rotate)).toBeLessThanOrEqual(2);
      expect(Math.abs(y)).toBeLessThanOrEqual(4);
      expect(leanOf(id)).toEqual({ rotate, y });
    }
  });
});
