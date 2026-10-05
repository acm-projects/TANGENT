"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { AxiosError } from "axios";
import { apiClient } from "@/api/session";
import { createAuthApi } from "@/features/auth";

/* All the app logic for this feature: state, validation, the API call, the
 * redirect. The component below it only renders (DESIGN.md Rule 5). */

const authApi = createAuthApi(apiClient);

export function useWorkspaceSetup() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const canSubmit = !busy && name.trim().length > 0;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { redirect } = await authApi.onboarding(name.trim());
      router.replace(redirect);
    } catch (err) {
      const detail = err instanceof AxiosError ? err.response?.data?.detail : null;
      setError(typeof detail === "string" ? detail : "Something went wrong. Please try again.");
      setBusy(false);
    }
  };

  return { name, setName, error, busy, canSubmit, submit };
}
