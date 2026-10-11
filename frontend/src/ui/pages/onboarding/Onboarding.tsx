import { Frame } from "@/ui/library";
import { OnboardingForm } from "@/ui/features/auth/OnboardingForm";
import "../login/Login.css";

/* The /onboarding screen: same centred, dotted layout as /login. */
export function Onboarding({ next }: { next?: string }) {
  return (
    <Frame as="main" align="center" className="login">
      <OnboardingForm next={next} />
    </Frame>
  );
}
