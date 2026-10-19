import { describe, expect, it } from "vitest";
import { dragAction } from "./DragAction";

describe("dragAction", () => {
  const card = { top: 100, bottom: 160 };
  it("branches below the card", () => expect(dragAction(card, 161, true)).toBe("branch"));
  it("deletes above the card", () => expect(dragAction(card, 99, true)).toBe("delete"));
  it("does nothing above the card when it can't be deleted (the root)", () => expect(dragAction(card, 99, false)).toBeNull());
  it("cancels level with the card", () => expect(dragAction(card, 130, true)).toBeNull());
});
