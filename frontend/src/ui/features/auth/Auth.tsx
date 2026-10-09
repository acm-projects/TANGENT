"use client";

import { Button, Frame, Panel, Text } from "@/ui/library";
import "./Auth.css";

/* The sign-in card. A shared feature (ui/features/) because a second user is
 * planned — e.g. a re-auth dialog when a session expires in the workspace.
 *
 * The button is a full-page navigation (not axios) to the backend's
 * GET /auth/login/google, which runs the OAuth flow and redirects back to
 * /onboarding (new user) or /{slug} (returning user) with ?access_token=. */
export function Auth() {
  return (
    <Panel as="section" hierarchy="secondary" elevation="floating" className="auth">
      <Frame gap="6">
        <Frame as="header" gap="2" align="center" className="auth-header">
          <Text as="span" size="s" hierarchy="primary" content="TANGENT" className="auth-wordmark" />
          <Text as="h1" size="xl" content="Welcome back" />
          <Text size="s" hierarchy="tertiary" content="Sign in to continue to your workspace." />
        </Frame>

        <Button
          hierarchy="primary"
          label="Continue with Google"
          icon="chevron_right"
          showIcon
          iconAlign="right"
          className="auth-google"
          // Absolute URL to the backend, not an internal Next page.
          // eslint-disable-next-line @next/next/no-location-assign-relative-destination
          onClick={() => window.location.assign(`${process.env.NEXT_PUBLIC_API_BASE_URL}/auth/login/google`)}
        />

        <Text
          size="xs"
          hierarchy="tertiary"
          content="By continuing, you agree to the Terms of Service and Privacy Policy."
          className="auth-legal"
        />
      </Frame>
    </Panel>
  );
}
