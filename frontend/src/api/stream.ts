import { CopyExistsError } from "./errors";
import type { DebateInfo, ForkInfo, ModelUsage, StreamEvent } from "./types";

/** Parse an SSE byte stream into { event, data, id } frames (`id` only on frames that carry one). */
export async function* sseFrames(body: ReadableStream<Uint8Array>): AsyncGenerator<{ event: string; data: string; id?: string }> {
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
        let id: string | undefined;
        const data: string[] = [];
        for (const line of frame.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
          else if (line.startsWith("id:")) id = line.slice(3).trim();
        }
        if (data.length) yield { event, data: data.join("\n"), ...(id !== undefined && { id }) };
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
  /** A model id from GET /models; the server picks its default when omitted. */
  model?: string;
  /** Regenerate the node's last reply: the server re-asks its last question and replaces that exchange. */
  retry?: boolean;
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
      body: JSON.stringify({ content: opts.content, model: opts.model, retry: opts.retry }),
      signal: opts.signal,
    });

  let res = await send(opts.getAccessToken());
  if (res.status === 401) res = await send(await opts.refresh());
  if (!res.ok || !res.body) {
    // FastAPI errors are { detail: "..." }; show that instead of a bare status code.
    const detail = await res.json().then((b: { detail?: unknown }) => b.detail, () => undefined);
    if (typeof detail === "string") throw new Error(detail);
    const copy = detail as { message?: string; forked_project_id?: string } | undefined;
    if (res.status === 409 && copy?.forked_project_id) throw new CopyExistsError(copy.message ?? "You already have your own copy.", copy.forked_project_id);
    throw new Error(`stream failed: ${res.status}`);
  }

  for await (const { event, data } of sseFrames(res.body)) {
    if (event === "token") opts.onEvent({ type: "token", text: (JSON.parse(data) as { text: string }).text });
    else if (event === "done") return void opts.onEvent({ type: "done", ...(JSON.parse(data) as { usage?: ModelUsage; model?: string; fork?: ForkInfo; stopped?: boolean }) });
    else if (event === "error") {
      const { message, fork, forked_project_id } = JSON.parse(data) as { message: string; fork?: ForkInfo; forked_project_id?: string };
      return void opts.onEvent({ type: "error", message, fork, forkedProjectId: forked_project_id });
    }
  }
  // Stream closed with no terminal event: surface it instead of hanging the UI in "streaming".
  opts.onEvent({ type: "error", message: "stream ended unexpectedly" });
}

/** One frame of GET /debates/:id/events. `state` and `done` carry the debate itself; every other event
 * carries `{ payload, at }`, and stored ones an `id` to resume after. */
export type DebateStreamEvent =
  | { name: "state" | "done"; data: DebateInfo }
  | { name: string; id?: number; data: { payload: Record<string, unknown>; at: string } };

export interface DebateStreamOptions {
  baseURL: string;
  debateId: string;
  /** Resume after this event id; earlier ones are not replayed. */
  lastEventId(): number | null;
  getAccessToken(): string | null;
  refresh(): Promise<string>;
  onEvent(e: DebateStreamEvent): void;
  signal?: AbortSignal;
}

/** Thrown when the debate is gone or not ours (404): reconnecting won't help. */
export class DebateGoneError extends Error {}

/**
 * Follow a debate's events until `done`. A GET, so unlike streamMessage it is safe to re-send: a dropped
 * connection reconnects with Last-Event-ID (backing off, up to a minute apart) and the server replays only
 * what was missed. The debate outlives the tab, so this only ends at `done`, on abort, or on a 404.
 */
export async function streamDebate(opts: DebateStreamOptions): Promise<void> {
  const open = (token: string | null) => {
    const last = opts.lastEventId();
    return fetch(`${opts.baseURL}/debates/${opts.debateId}/events`, {
      headers: {
        Accept: "text/event-stream",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(last !== null ? { "Last-Event-ID": String(last) } : {}),
      },
      signal: opts.signal,
    });
  };

  for (let failures = 0; ; ) {
    try {
      let res = await open(opts.getAccessToken());
      if (res.status === 401) res = await open(await opts.refresh());
      if (res.status === 404) throw new DebateGoneError("This debate no longer exists.");
      if (!res.ok || !res.body) throw new Error(`stream failed: ${res.status}`);
      for await (const { event, data, id } of sseFrames(res.body)) {
        failures = 0;
        if (event === "state" || event === "done") opts.onEvent({ name: event, data: JSON.parse(data) as DebateInfo });
        else opts.onEvent({ name: event, id: id === undefined ? undefined : Number(id), data: JSON.parse(data) });
        if (event === "done") return;
      }
    } catch (e) {
      if (opts.signal?.aborted || e instanceof DebateGoneError) throw e;
    }
    // closed without `done` (a load balancer, a sleeping laptop): wait, then pick up where it left off
    failures++;
    await new Promise((r) => setTimeout(r, Math.min(60_000, 1000 * 2 ** failures)));
    if (opts.signal?.aborted) throw new DOMException("aborted", "AbortError");
  }
}
