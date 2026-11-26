"use client";

import { useEffect, useState } from "react";
import { Frame, Link, Panel, Text } from "@/ui/library";
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

/* The case badge lockup: a stitched leather tab, CASE FILE, a pressed groove, then the name.
 * Shared by the sign-in, onboarding and invite cards. */
export function AuthLockup() {
  return (
    <Panel material="leather" stitch="all" round="all" className="auth-badge">
      <Text as="span" face="stamp" size="xxs" content="Case file" />
      <span aria-hidden="true" className="auth-badge-groove" />
      <Text as="span" face="heading" size="m" content="Tangent" className="auth-wordmark" />
    </Panel>
  );
}

export function Auth({ mode, next }: AuthProps) {
  const copy = COPY[mode];
  // Google's page can take a second to come up: hold the press until it does.
  const [leaving, setLeaving] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  // Back from Google, the browser may restore this page as it was left: let go of the press.
  useEffect(() => {
    const reset = () => setLeaving(false);
    window.addEventListener("pageshow", reset);
    return () => window.removeEventListener("pageshow", reset);
  }, []);
  return (
    <Panel as="section" edge="torn" elevation="floating" className="auth">
      <span aria-hidden="true" className="auth-pin" />
      <Frame gap="6">
        <Frame as="header" gap="2" align="center" className="auth-header">
          <AuthLockup />
          <Text as="h1" size="xl" content={copy.heading} />
          <Text size="s" hierarchy="tertiary" content={copy.subtext} />
        </Frame>

        {/* Google's "light" custom button: official four-colour G, unaltered, on a light surface. */}
        <Panel
          as="button"
          type="button"
          hierarchy="secondary"
          stock="composer"
          className="auth-gsi"
          data-busy={leaving || undefined}
          aria-busy={leaving}
          onClick={() => {
            setLeaving(true);
            // Absolute URL to the backend (see .env.example), not an internal Next page.
            const base = process.env.NEXT_PUBLIC_API_BASE_URL;
            // no backend address configured (a demo or local build): say so on the card, not a 404 page
            if (!base) {
              setLeaving(false);
              setUnavailable(true);
              return;
            }
            window.location.assign(googleLoginUrl(base, next));
          }}
        >
          <svg aria-hidden="true" viewBox="0 0 48 48" width="20" height="20">
            <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
            <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
            <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
            <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
          </svg>
          <Text as="span" size="s" content={leaving ? "Opening Google…" : "Continue with Google"} />
        </Panel>

        {unavailable && <Text role="alert" size="s" className="auth-error" content="Sign-in isn't set up on this server (no backend address configured)." />}

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
