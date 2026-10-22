import type { ApiClient } from "../client";
import type { Account, OnboardingResponse } from "../types";

/**
 * /auth/* -- everything except refresh, which lives in `client.ts` because the
 * 401 interceptor has to own it (single-flight; see ARCHITECTURE.md).
 *
 * The login UI that consumed these was a throwaway spike and is gone. These
 * wrappers are kept because the contract is real and the backend implements it.
 */
export function createAuthApi({ http }: ApiClient) {
  return {
    /** `next` is an /invite/... path; the backend echoes it back as `redirect` instead of the dashboard. */
    onboarding: (workspaceName: string, next?: string) =>
      http.post<OnboardingResponse>("/auth/onboarding", { workspace_name: workspaceName, next }).then((r) => r.data),
    logout: () => http.post("/auth/logout").then((r) => r.data),
    me: () => http.get<Account>("/auth/me").then((r) => r.data),
    updateMe: (changes: { name: string }) => http.patch("/auth/me", changes).then((r) => r.data),
  };
}

export type AuthApi = ReturnType<typeof createAuthApi>;
