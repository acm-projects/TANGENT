import { describe, expect, it } from "vitest";
import { appendChunk } from "./InkText";

describe("appendChunk", () => {
  it("starts from nothing", () => {
    expect(appendChunk([], "")).toEqual([]);
    expect(appendChunk([], "Hel")).toEqual(["Hel"]);
  });

  it("adds only the newly arrived slice", () => {
    expect(appendChunk(["Hel"], "Hello wor")).toEqual(["Hel", "lo wor"]);
  });

  it("returns the same array when nothing is new", () => {
    const chunks = ["Hel", "lo"];
    expect(appendChunk(chunks, "Hello")).toBe(chunks);
  });

  it("starts over when the text no longer extends what showed", () => {
    expect(appendChunk(["Hello"], "Bye")).toEqual(["Bye"]);
    expect(appendChunk(["Hello"], "Hel")).toEqual(["Hel"]);
    expect(appendChunk(["Hello"], "")).toEqual([]);
  });
});
