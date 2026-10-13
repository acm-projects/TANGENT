import { afterEach, describe, expect, it, vi } from "vitest";
import { sseFrames, streamModelCall } from "./stream";

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

describe("streamModelCall", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("forwards streamed text and final token usage", async () => {
    const enc = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(enc.encode('data: {"text":"Hello"}\n\n'));
        controller.enqueue(
          enc.encode('data: {"usage":{"prompt_tokens":3,"completion_tokens":2,"total_tokens":5},"model":"test/model"}\n\n'),
        );
        controller.close();
      },
    });
    const fetchMock = vi.fn().mockResolvedValue(new Response(body, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const events: unknown[] = [];

    await streamModelCall({
      prompt: "Hi",
      model: "test/model",
      onEvent: (event) => events.push(event),
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/model_call_stream",
      expect.objectContaining({ method: "POST", headers: { Accept: "text/event-stream" } }),
    );
    const form = fetchMock.mock.calls[0]?.[1]?.body as FormData;
    expect(form.get("prompt")).toBe("Hi");
    expect(form.get("model")).toBe("test/model");
    expect(events).toEqual([
      { type: "token", text: "Hello" },
      {
        type: "usage",
        usage: { prompt_tokens: 3, completion_tokens: 2, total_tokens: 5 },
        model: "test/model",
      },
      { type: "done" },
    ]);
  });

  it("surfaces HTTP failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("Bad request", { status: 400 })));
    await expect(
      streamModelCall({ prompt: "Hi", model: "test/model", onEvent: () => undefined }),
    ).rejects.toThrow("Model request failed (400): Bad request");
  });
});
