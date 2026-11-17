import { describe, expect, it } from "vitest";
import { noteSteps } from "./notesQueue";

const n = (id: string | null, text: string, done = false) => ({ id, text, done });

describe("Gent writing in the Field Notes", () => {
  it("adds his tasks one at a time, in his order", () => {
    const steps = noteSteps([], [n("n1", "Map"), n("n2", "Branch")]);
    expect(steps.map((s) => s.change)).toEqual([{ key: "n1", kind: "add" }, { key: "n2", kind: "add" }]);
    expect(steps.at(-1)!.notes).toEqual([n("n1", "Map"), n("n2", "Branch")]);
  });

  it("strikes before removing, then rewords and ticks", () => {
    const steps = noteSteps([n("n1", "Map"), n("n2", "Old")], [n("n1", "Map it", true)]);
    expect(steps.map((s) => s.change?.kind ?? null)).toEqual(["strike", null, "edit", "tick"]);
    expect(steps.at(-1)!.notes).toEqual([n("n1", "Map it", true)]);
  });

  it("matches the user's unsaved item to the id the server gave it", () => {
    const steps = noteSteps([n(null, "Check 1976")], [n("n4", "Check 1976")]);
    expect(steps.map((s) => s.change)).toEqual([null]);
    expect(steps.at(-1)!.notes).toEqual([n("n4", "Check 1976")]);
  });

  it("puts a new task after the one it follows", () => {
    const steps = noteSteps([n("n1", "A"), n("n3", "C")], [n("n1", "A"), n("n2", "B"), n("n3", "C")]);
    expect(steps.at(-1)!.notes.map((x) => x.id)).toEqual(["n1", "n2", "n3"]);
  });
});
