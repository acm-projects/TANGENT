import { describe, expect, it } from "vitest";
import { COLUMN_WIDTH, ROW_HEIGHT, layoutTree } from "./layout";

describe("layoutTree", () => {
  it("returns nothing for an empty tree", () => {
    expect(layoutTree(null, {})).toEqual({});
  });

  it("centres a parent over its children and puts each generation on its own row", () => {
    // r -> (a, b) ; b -> (c, d)  -- the Figma tree's shape
    const pos = layoutTree("r", { r: ["a", "b"], b: ["c", "d"] });
    expect(pos.a).toEqual({ x: 0, y: ROW_HEIGHT });
    expect(pos.c).toEqual({ x: COLUMN_WIDTH, y: 2 * ROW_HEIGHT });
    expect(pos.d).toEqual({ x: 2 * COLUMN_WIDTH, y: 2 * ROW_HEIGHT });
    expect(pos.b!.x).toBe((pos.c!.x + pos.d!.x) / 2);
    expect(pos.r!.x).toBe((pos.a!.x + pos.b!.x) / 2);
    expect(pos.r!.y).toBe(0);
  });

  it("keeps sibling order, so fork_index order reads left to right", () => {
    const pos = layoutTree("r", { r: ["first", "second", "third"] });
    expect(pos.first!.x).toBeLessThan(pos.second!.x);
    expect(pos.second!.x).toBeLessThan(pos.third!.x);
  });

  it("survives a cycle in corrupt data instead of looping forever", () => {
    const pos = layoutTree("r", { r: ["a"], a: ["r"] });
    expect(Object.keys(pos).sort()).toEqual(["a", "r"]);
  });
});
