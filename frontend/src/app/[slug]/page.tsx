import { SlugRedirect } from "@/ui/features/auth/SlugRedirect";

/* /{slug} -- where the backend redirects after login/onboarding. Forwards to /{slug}/dashboard. */
export default async function SlugPage({ params }: PageProps<"/[slug]">) {
  const { slug } = await params;
  return <SlugRedirect slug={slug} />;
}
