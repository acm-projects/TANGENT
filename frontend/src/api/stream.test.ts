import { describe, expect, it, vi } from "vitest";
import { sseFrames, streamMessage } from "./stream";
import type { StreamEvent } from "./types";

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

describe("streamMessage", () => {
  const sse = (...frames: string[]) =>
    new Response(frames.join(""), { status: 200, headers: { "Content-Type": "text/event-stream" } });
  const opts = { baseURL: "/api", nodeId: "n1", content: "hi", getAccessToken: () => "t", refresh: async () => "t2" };

  it("sends the model and forwards tokens, then usage from done", async () => {
    const usage = { prompt_tokens: 1, completion_tokens: 2, total_tokens: 3 };
    const fetchMock = vi.fn(async () =>
      sse('event: token\ndata: {"text":"a"}\n\n', `event: done\ndata: ${JSON.stringify({ usage, model: "m" })}\n\n`),
    );
    vi.stubGlobal("fetch", fetchMock);
    const events: StreamEvent[] = [];

    await streamMessage({ ...opts, model: "m", onEvent: (e) => events.push(e) });

    expect(JSON.parse((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body as string)).toEqual({ content: "hi", model: "m" });
    expect(events).toEqual([{ type: "token", text: "a" }, { type: "done", usage, model: "m" }]);
    vi.unstubAllGlobals();
  });

  it("surfaces an error event", async () => {
    vi.stubGlobal("fetch", async () => sse('event: error\ndata: {"message":"boom"}\n\n'));
    const events: StreamEvent[] = [];
    await streamMessage({ ...opts, onEvent: (e) => events.push(e) });
    expect(events).toEqual([{ type: "error", message: "boom" }]);
    vi.unstubAllGlobals();
  });

  it("two concurrent streams to different nodes overlap and finish independently", async () => {
    const enc = new TextEncoder();
    // One controllable SSE body per node, so the test decides how the two streams interleave.
    const bodies: Record<string, ReadableStreamDefaultController<Uint8Array>> = {};
    vi.stubGlobal("fetch", async (url: string) => {
      const nodeId = url.split("/")[3]!; // /api/nodes/<id>/messages
      return new Response(new ReadableStream<Uint8Array>({ start: (c) => void (bodies[nodeId] = c) }), { status: 200 });
    });
    const send = (c: ReadableStreamDefaultController<Uint8Array>, frame: string) => c.enqueue(enc.encode(frame));
    const seen: string[] = [];
    const run = (nodeId: string) =>
      streamMessage({ ...opts, nodeId, onEvent: (e) => seen.push(`${nodeId}:${e.type === "token" ? e.text : e.type}`) });

    const a = run("a");
    const b = run("b");
    await vi.waitFor(() => expect(Object.keys(bodies)).toHaveLength(2)); // both requests in flight at once

    send(bodies["a"]!, 'event: token\ndata: {"text":"A1"}\n\n');
    send(bodies["b"]!, 'event: token\ndata: {"text":"B1"}\n\n');
    send(bodies["b"]!, 'event: error\ndata: {"message":"boom"}\n\n');
    bodies["b"]!.close();
    await b; // b finished (errored) while a is still open
    send(bodies["a"]!, 'event: token\ndata: {"text":"A2"}\n\nevent: done\ndata: {}\n\n');
    bodies["a"]!.close();
    await a;

    expect(seen.filter((x) => x.startsWith("a:"))).toEqual(["a:A1", "a:A2", "a:done"]);
    expect(seen.filter((x) => x.startsWith("b:"))).toEqual(["b:B1", "b:error"]);
    vi.unstubAllGlobals();
  });

  it("throws the server's detail message when the request is refused", async () => {
    vi.stubGlobal("fetch", async () => new Response(JSON.stringify({ detail: "Only a leaf node can be prompted; fork it instead" }), { status: 409 }));
    await expect(streamMessage({ ...opts, onEvent: () => {} })).rejects.toThrow("Only a leaf node can be prompted");
    vi.unstubAllGlobals();
  });
});
