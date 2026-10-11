import { Onboarding } from "@/ui/pages/onboarding/Onboarding";

export default async function OnboardingPage({ searchParams }: PageProps<"/onboarding">) {
  const { next } = await searchParams;
  return <Onboarding next={typeof next === "string" ? next : undefined} />;
}
