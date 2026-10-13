import type { ModelCallStreamEvent, StreamEvent } from "./types";

/** Parse an SSE byte stream into { event, data } frames. */
export async function* sseFrames(body: ReadableStream<Uint8Array>): AsyncGenerator<{ event: string; data: string }> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let idx: number;
      while ((idx = buf.indexOf("\n\n")) !== -1) {
        const frame = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        let event = "message";
        const data: string[] = [];
        for (const line of frame.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
        }
        if (data.length) yield { event, data: data.join("\n") };
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export interface StreamOptions {
  baseURL: string;
  nodeId: string;
  content: string;
  getAccessToken(): string | null;
  refresh(): Promise<string>;
  onEvent(e: StreamEvent): void;
  signal?: AbortSignal;
}

export interface ModelCallStreamOptions {
  prompt: string;
  model: string;
  file?: File;
  onEvent(e: ModelCallStreamEvent): void;
  signal?: AbortSignal;
}

/**
 * POST a standalone prompt to chats_router.py and forward its SSE chunks.
 * This endpoint is intentionally separate from node chat: it does not load or
 * persist conversation history.
 */
export async function streamModelCall(opts: ModelCallStreamOptions): Promise<void> {
  const form = new FormData();
  form.set("prompt", opts.prompt);
  form.set("model", opts.model);
  if (opts.file) form.set("file", opts.file);

  const response = await fetch("/api/model_call_stream", {
    method: "POST",
    headers: { Accept: "text/event-stream" },
    body: form,
    signal: opts.signal,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Model request failed (${response.status})${detail ? `: ${detail}` : ""}`);
  }
  if (!response.body) throw new Error("The model response did not include a stream.");

  for await (const frame of sseFrames(response.body)) {
    let payload: unknown;
    try {
      payload = JSON.parse(frame.data);
    } catch {
      throw new Error("The model stream returned invalid JSON.");
    }
    if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
      throw new Error("The model stream returned an invalid event.");
    }

    const data = payload as Record<string, unknown>;
    if (data.error !== undefined) {
      const message =
        typeof data.error === "string" ? data.error : JSON.stringify(data.error);
      throw new Error(message || "The model returned an error.");
    }
    if (typeof data.text === "string") {
      opts.onEvent({ type: "token", text: data.text });
    }
    if (data.usage !== undefined) {
      if (typeof data.usage !== "object" || data.usage === null || Array.isArray(data.usage)) {
        throw new Error("The model stream returned invalid token usage.");
      }
      const usage = data.usage as Record<string, unknown>;
      const { prompt_tokens, completion_tokens, total_tokens } = usage;
      if (
        typeof prompt_tokens !== "number" ||
        typeof completion_tokens !== "number" ||
        typeof total_tokens !== "number"
      ) {
        throw new Error("The model stream returned incomplete token usage.");
      }
      opts.onEvent({
        type: "usage",
        usage: { prompt_tokens, completion_tokens, total_tokens },
        model: typeof data.model === "string" ? data.model : opts.model,
      });
    }
  }

  opts.onEvent({ type: "done" });
}

/**
 * Deliberately not @microsoft/fetch-event-source: it auto-retries on error, and
 * retrying a POST would re-send the user's message. We retry exactly once, and
 * only on 401 (request was rejected before any processing).
 */
export async function streamMessage(opts: StreamOptions): Promise<void> {
  const send = (token: string | null) =>
    fetch(`${opts.baseURL}/nodes/${opts.nodeId}/messages`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ content: opts.content }),
      signal: opts.signal,
    });

  let res = await send(opts.getAccessToken());
  if (res.status === 401) res = await send(await opts.refresh());
  if (!res.ok || !res.body) throw new Error(`stream failed: ${res.status}`);

  for await (const { event, data } of sseFrames(res.body)) {
    if (event === "token") opts.onEvent({ type: "token", text: (JSON.parse(data) as { text: string }).text });
    else if (event === "done") return void opts.onEvent({ type: "done" });
    else if (event === "error") return void opts.onEvent({ type: "error", message: (JSON.parse(data) as { message: string }).message });
  }
  // Stream closed with no terminal event: surface it instead of hanging the UI in "streaming".
  opts.onEvent({ type: "error", message: "stream ended unexpectedly" });
}
