import { describe, expect, it } from "vitest";
import { splitMatches } from "./highlight";

describe("splitMatches", () => {
  it("marks each occurrence, keeping the text's own case", () => {
    expect(splitMatches("Foo bar foo", "foo")).toEqual([
      { text: "Foo", hit: true },
      { text: " bar ", hit: false },
      { text: "foo", hit: true },
    ]);
  });
  it("returns the text whole when nothing matches or there are no words", () => {
    expect(splitMatches("abc", "x")).toEqual([{ text: "abc", hit: false }]);
    expect(splitMatches("abc", "")).toEqual([{ text: "abc", hit: false }]);
  });
});
