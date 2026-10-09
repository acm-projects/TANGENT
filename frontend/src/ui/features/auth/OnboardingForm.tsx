"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/api";
import { Button, Frame, Panel, Text, Input } from "@/ui/library";
import { useSessionBoot } from "./useSessionBoot";
import "./Auth.css";

/* The workspace-name card shown to a brand-new user (POST /auth/onboarding).
 * Reuses the .auth card styles. On success the backend returns where to go
 * ("/{slug}"), which app/[slug]/page.tsx forwards to the dashboard. */
export function OnboardingForm() {
  const router = useRouter();
  const session = useSessionBoot();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.auth.onboarding(name.trim());
      router.replace(res.redirect);
    } catch {
      setError("Couldn't create your workspace. Please try again.");
      setBusy(false);
    }
  };

  return (
    <Panel as="section" hierarchy="secondary" elevation="floating" className="auth">
      <form onSubmit={submit}>
      <Frame gap="6">
        <Frame as="header" gap="2" align="center" className="auth-header">
          <Text as="span" size="s" hierarchy="primary" content="TANGENT" className="auth-wordmark" />
          <Text as="h1" size="xl" content="Name your workspace" />
          <Text size="s" hierarchy="tertiary" content="You can change this later." />
        </Frame>

        <Panel hierarchy="primary">
          <Input
            aria-label="Workspace name"
            placeholder="Workspace name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={100}
            required
            autoFocus
          />
        </Panel>

        {error && <Text size="s" content={error} role="alert" />}

        <Button
          type="submit"
          hierarchy="primary"
          label={busy ? "Creating…" : "Continue"}
          disabled={session !== "ready" || busy || !name.trim()}
          className="auth-google"
        />
      </Frame>
      </form>
    </Panel>
  );
}
