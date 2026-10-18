import { describe, expect, it } from "vitest";
import type { NodeMeta, TreeResponse } from "@/api/types";
import { nextProjectName } from "./nextName";
import { SKETCH_H, SKETCH_W, sketchTree } from "./sketch";

const node = (id: string, parent: string | null, fork_index: number, created_at: string): NodeMeta => ({
  id, tree_id: "t", project_id: "p", parent_id: parent, fork_index, node_type: null, status: "active",
  title: null, summary: null, created_by_id: "u", created_at,
});
const tree = (root: string | null, nodes: NodeMeta[]): TreeResponse => ({
  tree: { id: "t", project_id: "p", root_node_id: root, created_at: "" },
  nodes,
});

describe("sketchTree", () => {
  it("draws every node inside the frame, linked to its parent", () => {
    const pins = sketchTree(tree("r", [
      node("r", null, 0, "1"), node("a", "r", 0, "2"), node("b", "r", 1, "3"), node("c", "a", 0, "4"),
    ]));
    expect(pins).toHaveLength(4);
    for (const p of pins) {
      expect(p.x).toBeGreaterThanOrEqual(0);
      expect(p.x).toBeLessThanOrEqual(SKETCH_W);
      expect(p.y).toBeGreaterThanOrEqual(0);
      expect(p.y).toBeLessThanOrEqual(SKETCH_H);
    }
    expect(pins.filter((p) => p.parent === null)).toHaveLength(1);
  });

  it("strings the path from the root to the newest node in red", () => {
    const nodes = [node("r", null, 0, "1"), node("a", "r", 0, "2"), node("b", "r", 1, "5"), node("c", "a", 0, "4")];
    const pins = sketchTree(tree("r", nodes));
    const onPath = pins.filter((p) => p.onPath);
    expect(onPath).toHaveLength(2); // r and b
    expect(pins.find((p) => p.parent === null)!.onPath).toBe(true);
  });

  it("puts a lone root in the middle, and draws nothing for no tree", () => {
    expect(sketchTree(tree("r", [node("r", null, 0, "1")]))).toEqual([
      { x: SKETCH_W / 2, y: SKETCH_H / 2, parent: null, onPath: true },
    ]);
    expect(sketchTree(tree(null, []))).toEqual([]);
  });
});

describe("nextProjectName", () => {
  it("takes the smallest free number", () => {
    expect(nextProjectName([])).toBe("Project (1)");
    expect(nextProjectName(["Project (1)", "Project (3)", "Gym"])).toBe("Project (2)");
  });
});
