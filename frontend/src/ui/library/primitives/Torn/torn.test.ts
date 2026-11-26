import { describe, expect, it } from "vitest";
import { tornPath } from "./torn";

const points = (d: string) => [...d.matchAll(/(-?[\d.]+) (-?[\d.]+)/g)].map((m) => [Number(m[1]), Number(m[2])]);

describe("tornPath", () => {
  it("is deterministic", () => expect(tornPath(300, 200, 5)).toBe(tornPath(300, 200, 5)));
  it("differs by seed", () => expect(tornPath(300, 200, 5)).not.toBe(tornPath(300, 200, 6)));
  it("keeps every point inside the box, closed", () => {
    for (const [w, h] of [[300, 200], [40, 30], [12, 500]]) for (let seed = 1; seed < 30; seed++) {
      const d = tornPath(w, h, seed);
      expect(d).toMatch(/^M.*Z$/);
      for (const [x, y] of points(d)) expect(x >= 0 && x <= w && y >= 0 && y <= h).toBe(true);
    }
  });
  it("gives corners their own shape", () => {
    const p = points(tornPath(300, 200, 9));
    expect(p.length).toBeGreaterThan(100);
    expect(new Set(p.map(([x]) => x)).size).toBeGreaterThan(20);
  });
});
