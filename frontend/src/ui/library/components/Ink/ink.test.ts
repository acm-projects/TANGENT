import { describe, expect, it } from "vitest";
import { inkSeconds, setInkPace } from "./ink";

describe("the ink's clock", () => {
  it("runs slowly at rest and speeds up (eased) while Gent works", () => {
    const step = (from: number, to: number) => {
      for (let t = from; t <= to; t += 50) inkSeconds(t);
      return inkSeconds(to);
    };
    const start = step(0, 0);
    expect(step(0, 1000) - start).toBeCloseTo(0.15, 2); // a second at rest
    expect(inkSeconds(1000 + 60_000) - inkSeconds(1000)).toBeLessThan(0.05); // a long pause doesn't jump
    setInkPace(1);
    const eased = step(61_000, 64_000);
    expect(step(64_000, 65_000) - eased).toBeGreaterThan(0.95); // full speed once eased in
  });
});
