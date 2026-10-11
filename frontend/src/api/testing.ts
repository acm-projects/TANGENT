import type { AxiosAdapter } from "axios";
import { createApiClient, type ApiClient } from "./client";

/** Test helper: a real ApiClient whose network is a fake that records requests and answers 200. */
export function recordingClient(responseData: unknown) {
  const calls: { method: string | undefined; url: string | undefined; data: unknown }[] = [];
  const adapter: AxiosAdapter = async (config) => {
    calls.push({ method: config.method, url: config.url, data: config.data });
    return { data: responseData, status: 200, statusText: "OK", headers: {}, config };
  };
  const client: ApiClient = createApiClient({
    baseURL: "http://x",
    adapter,
    auth: { getAccessToken: () => null, setAccessToken: () => {}, onAuthFailure: () => {} },
  });
  return { client, calls };
}
