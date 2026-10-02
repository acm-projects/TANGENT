import { AxiosError, AxiosHeaders, InternalAxiosRequestConfig } from "axios";
import { describe, expect, it, vi } from "vitest";
import { createApiClient } from "./api/client";
import { sseFrames } from "./api/stream";
import type { NodeMeta } from "./api/types";
import { selectBreadcrumb, selectIsLeaf, useTreeStore } from "./store/treeStore";

function makeAdapter(opts: { refreshOk: boolean }) {
  const calls = { refresh: 0, api: 0 };
  const respond = (config: InternalAxiosRequestConfig, status: number, data: unknown) => {
    const response = { data, status, statusText: "", headers: {}, config };
    if (status >= 400) throw new AxiosError("err", "ERR", config, null, response);
    return response;
  };
  const adapter = async (config: InternalAxiosRequestConfig) => {
    await new Promise((r) => setTimeout(r, 5));
    if (config.url === "/auth/refresh") {
      calls.refresh++;
      return respond(config, opts.refreshOk ? 200 : 401, { access_token: "new" });
    }
    calls.api++;
    const auth = new AxiosHeaders(config.headers).get("Authorization");
    return auth === "Bearer new" ? respond(config, 200, { ok: true }) : respond(config, 401, {});
  };
  return { adapter, calls };
}

describe("single-flight refresh", () => {
  it("issues exactly one refresh for concurrent 401s and retries all", async () => {
    const { adapter, calls } = makeAdapter({ refreshOk: true });
    let token: string | null = "old";
    const client = createApiClient({
      baseURL: "http://x",
      adapter,
      auth: { getAccessToken: () => token, setAccessToken: (t) => (token = t), onAuthFailure: vi.fn() },
    });
    const results = await Promise.all(Array.from({ length: 5 }, () => client.http.get("/n")));
    expect(results.every((r) => r.status === 200)).toBe(true);
    expect(calls.refresh).toBe(1);
    expect(calls.api).toBe(10); // 5 rejected + 5 retried
  });

  it("calls onAuthFailure once and rejects everything when refresh fails", async () => {
    const { adapter, calls } = makeAdapter({ refreshOk: false });
    let token: string | null = "old";
    const onAuthFailure = vi.fn();
    const client = createApiClient({
      baseURL: "http://x",
      adapter,
      auth: { getAccessToken: () => token, setAccessToken: (t) => (token = t), onAuthFailure },
    });
    const settled = await Promise.allSettled(Array.from({ length: 3 }, () => client.http.get("/n")));
    expect(settled.every((r) => r.status === "rejected")).toBe(true);
    expect(calls.refresh).toBe(1);
    expect(onAuthFailure).toHaveBeenCalledTimes(1);
    expect(token).toBeNull();
  });
});

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

const node = (id: string, parent: string | null, fork: number): NodeMeta => ({
  id, tree_id: "t", project_id: "p", parent_id: parent, fork_index: fork, node_type: null,
  status: "active", title: null, summary: null, created_by_id: "u", created_at: "",
});

describe("tree store", () => {
  it("orders children by fork_index, computes leaf + breadcrumb", () => {
    useTreeStore.getState().hydrateTree("r", [node("c2", "r", 2), node("r", null, 0), node("c1", "r", 1), node("g", "c1", 1)]);
    const s = useTreeStore.getState();
    expect(s.childrenByParent["r"]).toEqual(["c1", "c2"]);
    expect(selectIsLeaf(s, "c2")).toBe(true);
    expect(selectIsLeaf(s, "c1")).toBe(false);
    expect(selectBreadcrumb(s, "g").map((n) => n.id)).toEqual(["r", "c1", "g"]);
  });

  it("token appends leave structure references untouched", () => {
    useTreeStore.getState().hydrateTree("r", [node("r", null, 0)]);
    const before = useTreeStore.getState();
    before.beginStream("r", { role: "user", content: "q", seq: 0, branch_source: null, created_at: "" });
    useTreeStore.getState().appendToken("a");
    useTreeStore.getState().appendToken("b");
    const after = useTreeStore.getState();
    expect(after.streaming?.text).toBe("ab");
    expect(after.nodesById).toBe(before.nodesById);
    expect(after.childrenByParent).toBe(before.childrenByParent);
  });
});
