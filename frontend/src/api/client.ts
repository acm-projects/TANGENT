import axios, { AxiosAdapter, AxiosError, AxiosInstance, InternalAxiosRequestConfig } from "axios";

export interface AuthHooks {
  getAccessToken(): string | null;
  setAccessToken(token: string | null): void;
  /** Called once when refresh fails: clear app state and route to login. */
  onAuthFailure(): void;
}

export interface ApiClient {
  http: AxiosInstance;
  /** Single-flight refresh, shared with the SSE client. Resolves to the new access token. */
  refresh(): Promise<string>;
}

type RetriableConfig = InternalAxiosRequestConfig & { _retried?: boolean };

/**
 * Assumes refresh token lives in an httpOnly cookie (withCredentials) and
 * POST /auth/refresh rotates it and returns { access_token }.
 * Rotation + reuse detection (sessions.consumed_at) means two concurrent refreshes
 * can revoke the whole session, hence the single-flight promise.
 */
export function createApiClient(opts: { baseURL: string; auth: AuthHooks; adapter?: AxiosAdapter }): ApiClient {
  const { baseURL, auth, adapter } = opts;
  const http = axios.create({ baseURL, adapter });
  // Bare instance (no interceptors) so a failing refresh can't recurse into itself.
  const bare = axios.create({ baseURL, withCredentials: true, adapter });

  let inflight: Promise<string> | null = null;

  const refresh = (): Promise<string> => {
    inflight ??= bare
      .post<{ access_token: string }>("/auth/refresh")
      .then((r) => {
        auth.setAccessToken(r.data.access_token);
        return r.data.access_token;
      })
      .catch((e) => {
        auth.setAccessToken(null);
        auth.onAuthFailure();
        throw e;
      })
      .finally(() => {
        inflight = null;
      });
    return inflight;
  };

  http.interceptors.request.use((cfg) => {
    const token = auth.getAccessToken();
    if (token) cfg.headers.Authorization = `Bearer ${token}`;
    return cfg;
  });

  http.interceptors.response.use(
    (r) => r,
    async (err: AxiosError) => {
      const cfg = err.config as RetriableConfig | undefined;
      if (err.response?.status !== 401 || !cfg || cfg._retried) throw err;
      cfg._retried = true;

      // If another request already refreshed after this one was sent, just retry with the new token.
      const sent = String(cfg.headers.Authorization ?? "").replace(/^Bearer /, "");
      const current = auth.getAccessToken();
      const token = current && current !== sent ? current : await refresh();

      cfg.headers.Authorization = `Bearer ${token}`;
      return http(cfg);
    },
  );

  return { http, refresh };
}
