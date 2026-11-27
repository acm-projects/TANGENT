import { describe, expect, it } from "vitest";
import { dragAction } from "./DragAction";

describe("dragAction", () => {
  const card = { top: 100, bottom: 160, left: 200, right: 400 };
  const all = { canDelete: true, canCompact: true };
  it("branches below the card", () => expect(dragAction(card, { x: 300, y: 161 }, all)).toBe("branch"));
  it("deletes above the card", () => expect(dragAction(card, { x: 300, y: 99 }, all)).toBe("delete"));
  it("does nothing above the card when it can't be deleted (the root)", () =>
    expect(dragAction(card, { x: 300, y: 99 }, { canDelete: false })).toBeNull());
  it("compacts to the left", () => expect(dragAction(card, { x: 199, y: 130 }, all)).toBe("compact"));
  it("does nothing to the right", () => expect(dragAction(card, { x: 401, y: 130 }, all)).toBeNull());
  it("below and above win over the sides", () => expect(dragAction(card, { x: 100, y: 170 }, all)).toBe("branch"));
  it("cancels on a side the card doesn't allow, and inside it", () => {
    expect(dragAction(card, { x: 199, y: 130 }, { canDelete: true })).toBeNull();
    expect(dragAction(card, { x: 300, y: 130 }, all)).toBeNull();
  });
  it("arms a side only past the arm distance", () => {
    expect(dragAction(card, { x: 300, y: 99 }, all, 24)).toBeNull();
    expect(dragAction(card, { x: 300, y: 75 }, all, 24)).toBe("delete");
    expect(dragAction(card, { x: 300, y: 184 }, all, 24)).toBeNull();
    expect(dragAction(card, { x: 300, y: 185 }, all, 24)).toBe("branch");
  });
});
