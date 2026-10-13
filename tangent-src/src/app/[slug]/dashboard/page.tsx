import { Dashboard } from "@/ui/pages/dashboard/Dashboard";

/* /{slug}/dashboard -- the path the backend's onboarding already redirects to
 * (POST /auth/onboarding -> { redirect }). */
export default async function DashboardPage({ params }: PageProps<"/[slug]/dashboard">) {
  const { slug } = await params;
  return <Dashboard slug={slug} />;
}
