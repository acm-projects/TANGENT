import { Panel } from "@/ui/library";
import { CaseBoard } from "@/ui/features/auth/CaseBoard";
import { OnboardingForm } from "@/ui/features/auth/OnboardingForm";
import "../login/Login.css";

/* The /onboarding screen: same centred, cork-board layout as /login. */
export function Onboarding({ next }: { next?: string }) {
  return (
    <Panel as="main" material="cork" className="login">
      <CaseBoard />
      <OnboardingForm next={next} />
    </Panel>
  );
}
