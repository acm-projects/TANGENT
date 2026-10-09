import { Frame } from "@/ui/library";
import { OnboardingForm } from "@/ui/features/auth/OnboardingForm";
import "../login/Login.css";

/* The /onboarding screen: same centred, dotted layout as /login. */
export function Onboarding() {
  return (
    <Frame as="main" align="center" className="login">
      <OnboardingForm />
    </Frame>
  );
}
