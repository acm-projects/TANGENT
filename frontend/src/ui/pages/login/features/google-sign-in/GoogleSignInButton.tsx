"use client";

import { Button } from "@/ui/components";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/* Page-scoped feature: only the login page uses it, so it lives under that page
 * rather than in src/features/ (DESIGN.md §2). Promote it if a second page
 * ever needs it. */

export function GoogleSignInButton() {
  // Full-page navigation (not axios): the backend 302s to Google. Signup and login are the same button.
  const onClick = () => {
    window.location.assign(`${API_BASE}/auth/login/google`);
  };

  return <Button onClick={onClick}>Continue with Google</Button>;
}
