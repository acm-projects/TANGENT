"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { AxiosError } from "axios";
import { apiClient } from "../../api/session";
import { createAuthApi } from "./api";
import { useAccessToken } from "./useAccessToken";
import "./auth.css";

const authApi = createAuthApi(apiClient);

export default function OnboardingPage() {
  const router = useRouter();
  const session = useAccessToken();
  const [workspaceName, setWorkspaceName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { redirect } = await authApi.onboarding(workspaceName.trim());
      router.replace(redirect);
    } catch (err) {
      const detail = err instanceof AxiosError ? err.response?.data?.detail : null;
      setError(typeof detail === "string" ? detail : "Something went wrong. Please try again.");
      setBusy(false);
    }
  };

  if (session === "loading") return <main className="auth-page" />;

  return (
    <main className="auth-page">
      <form className="auth-card" onSubmit={onSubmit}>
        <h1 className="auth-title">Name your workspace</h1>
        <p className="auth-muted">You can change this later.</p>
        <label className="auth-label">
          Workspace name
          <input
            className="auth-input"
            value={workspaceName}
            onChange={(e) => setWorkspaceName(e.target.value)}
            required
            autoFocus
          />
        </label>
        {error && <p className="auth-error" role="alert">{error}</p>}
        <button type="submit" className="auth-button" disabled={busy || !workspaceName.trim()}>
          Continue
        </button>
      </form>
    </main>
  );
}
