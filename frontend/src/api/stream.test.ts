import { describe, expect, it } from "vitest";
import { sseFrames } from "./stream";

describe("sseFrames", () => {
  it("parses frames split across chunk boundaries", async () => {
    const enc = new TextEncoder();
    const chunks = ['event: token\ndata: {"text":"he', 'llo"}\n\nevent: done\n', "data: {}\n\n"];
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        chunks.forEach((x) => c.enqueue(enc.encode(x)));
        c.close();
      },
    });
    const frames: { event: string; data: string }[] = [];
    for await (const f of sseFrames(body)) frames.push(f);
    expect(frames).toEqual([
      { event: "token", data: '{"text":"hello"}' },
      { event: "done", data: "{}" },
    ]);
  });
});
