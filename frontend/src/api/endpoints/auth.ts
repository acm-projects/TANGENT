import type { ApiClient } from "../client";
import type { OnboardingResponse } from "../types";

/**
 * /auth/* -- everything except refresh, which lives in `client.ts` because the
 * 401 interceptor has to own it (single-flight; see ARCHITECTURE.md).
 *
 * The login UI that consumed these was a throwaway spike and is gone. These
 * wrappers are kept because the contract is real and the backend implements it.
 */
export function createAuthApi({ http }: ApiClient) {
  return {
    onboarding: (workspaceName: string) =>
      http.post<OnboardingResponse>("/auth/onboarding", { workspace_name: workspaceName }).then((r) => r.data),
    logout: () => http.post("/auth/logout").then((r) => r.data),
  };
}

export type AuthApi = ReturnType<typeof createAuthApi>;
