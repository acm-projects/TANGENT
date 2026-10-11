"use client";

import { Button, Frame, Link, Panel, Text } from "@/ui/library";
import { googleLoginUrl, loginPath, signupPath } from "./paths";
import "./Auth.css";

/* The sign-in / sign-up card. A shared feature (ui/features/) because a second
 * user is planned — e.g. a re-auth dialog when a session expires in the workspace.
 *
 * Login and signup are the same flow: the button is a full-page navigation (not
 * axios) to the backend's GET /auth/login/google, which creates the account if
 * it doesn't exist, runs the OAuth flow and redirects back to /onboarding (new
 * user) or /{slug} (returning user) with ?access_token=. Only the copy differs.
 * `next` (an /invite/... path) is handed to the backend so the flow returns there. */

type AuthProps = { mode: "login" | "signup"; next?: string };

const COPY = {
  login: {
    heading: "Welcome back",
    subtext: "Sign in to continue to your workspace.",
    switchText: "New to Tangent? Sign up",
    switchTo: signupPath,
  },
  signup: {
    heading: "Create your account",
    subtext: "Sign up to start your first workspace.",
    switchText: "Already have an account? Log in",
    switchTo: loginPath,
  },
};

export function Auth({ mode, next }: AuthProps) {
  const copy = COPY[mode];
  return (
    <Panel as="section" hierarchy="secondary" elevation="floating" className="auth">
      <Frame gap="6">
        <Frame as="header" gap="2" align="center" className="auth-header">
          <Text as="span" size="s" hierarchy="primary" content="TANGENT" className="auth-wordmark" />
          <Text as="h1" size="xl" content={copy.heading} />
          <Text size="s" hierarchy="tertiary" content={copy.subtext} />
        </Frame>

        <Button
          hierarchy="primary"
          label="Continue with Google"
          icon="chevron_right"
          showIcon
          iconAlign="right"
          className="auth-google"
          // Absolute URL to the backend (see .env.example), not an internal Next page.
          onClick={() => window.location.assign(googleLoginUrl(process.env.NEXT_PUBLIC_API_BASE_URL!, next))}
        />

        <Link href={copy.switchTo(next)} className="auth-switch">
          <Text size="s" hierarchy="tertiary" content={copy.switchText} />
        </Link>

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
