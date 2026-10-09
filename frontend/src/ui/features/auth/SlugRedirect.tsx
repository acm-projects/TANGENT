"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSessionBoot } from "./useSessionBoot";

/* The backend sends a signed-in user to /{slug}?access_token=... (OAuth callback
 * and POST /auth/onboarding). Consume the token, then go to the dashboard. */
export function SlugRedirect({ slug }: { slug: string }) {
  const router = useRouter();
  const session = useSessionBoot();

  useEffect(() => {
    if (session === "ready") router.replace(`/${slug}/dashboard`);
  }, [session, slug, router]);

  return null;
}
