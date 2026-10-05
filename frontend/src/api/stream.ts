import type { StreamEvent } from "./types";

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
