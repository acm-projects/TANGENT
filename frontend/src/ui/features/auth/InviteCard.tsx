"use client";

import { useRouter } from "next/navigation";
import { api, setAccessToken } from "@/api";
import { Button, Frame, Panel, Text } from "@/ui/library";
import { invitePath, loginPath, signupPath } from "./paths";
import { useInvite } from "./useInvite";
import "./Auth.css";

/* The invitation card (/invite/{token}). Reuses the .auth card styles, like
 * OnboardingForm. Signed out: offer login / signup, which come back here via
 * `next`. Signed in: offer Accept. */
export function InviteCard({ token }: { token: string }) {
  const router = useRouter();
  const invite = useInvite(token);
  const here = invitePath(token);

  // The backend's Google flow already uses prompt=select_account, so after our
  // session is cleared the visitor gets Google's account chooser.
  async function useDifferentAccount() {
    await api.auth.logout().catch(() => {});
    setAccessToken(null);
    router.push(loginPath(here));
  }

  return (
    <Panel as="section" hierarchy="secondary" elevation="floating" className="auth">
      <Frame gap="6">
        <Frame as="header" gap="2" align="center" className="auth-header">
          <Text as="span" size="s" hierarchy="primary" content="TANGENT" className="auth-wordmark" />
          {invite.status === "loading" && <Text as="h1" size="xl" content="Loading invitation…" />}
          {invite.status === "invalid" && (
            <>
              <Text as="h1" size="xl" content="Invitation unavailable" />
              <Text size="s" hierarchy="tertiary" content={invite.message} role="alert" />
            </>
          )}
          {invite.status === "ready" && (
            <>
              <Text as="h1" size="xl" content={`${invite.details.inviter_name} invited you to ${invite.details.project_name}`} />
              <Text size="s" hierarchy="tertiary" content={`Sent to ${invite.details.email}`} />
            </>
          )}
        </Frame>

        {invite.status === "ready" && invite.signedIn && (
          <Frame gap="2">
            <Button
              hierarchy="primary"
              label={invite.accepting ? "Accepting…" : "Accept invite"}
              disabled={invite.accepting}
              className="auth-google"
              onClick={invite.accept}
            />
            {invite.acceptError && (
              <>
                <Text size="s" content={invite.acceptError} role="alert" className="auth-legal" />
                <Button label="Use a different account" className="auth-google" onClick={useDifferentAccount} />
              </>
            )}
          </Frame>
        )}

        {invite.status === "ready" && !invite.signedIn && (
          <Frame gap="2">
            <Button
              hierarchy="primary"
              label="Log in to accept"
              className="auth-google"
              onClick={() => router.push(loginPath(here))}
            />
            <Button label="Sign up" className="auth-google" onClick={() => router.push(signupPath(here))} />
          </Frame>
        )}
      </Frame>
    </Panel>
  );
}
