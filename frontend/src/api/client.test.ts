import { AxiosError, AxiosHeaders, InternalAxiosRequestConfig } from "axios";
import { describe, expect, it, vi } from "vitest";
import { createApiClient } from "./client";

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
