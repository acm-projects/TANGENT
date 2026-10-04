import type { ApiClient } from "../../api/client";
import type { OnboardingResponse } from "../../api/types";

export function createAuthApi({ http }: ApiClient) {
  return {
    onboarding: (workspaceName: string) =>
      http.post<OnboardingResponse>("/auth/onboarding", { workspace_name: workspaceName }).then((r) => r.data),
    logout: () => http.post("/auth/logout").then((r) => r.data),
  };
}
