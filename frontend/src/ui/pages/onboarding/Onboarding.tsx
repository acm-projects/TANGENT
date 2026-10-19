import { Frame } from "@/ui/library";
import { CaseBoard } from "@/ui/features/auth/CaseBoard";
import { OnboardingForm } from "@/ui/features/auth/OnboardingForm";
import "../login/Login.css";

/* The /onboarding screen: same centred, dotted layout as /login. */
export function Onboarding({ next }: { next?: string }) {
  return (
    <Frame as="main" align="center" className="login">
      <CaseBoard />
      <OnboardingForm next={next} />
    </Frame>
  );
}
