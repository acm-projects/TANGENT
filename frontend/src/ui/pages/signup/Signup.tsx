import { Panel } from "@/ui/library";
import { CaseBoard } from "@/ui/features/auth/CaseBoard";
import { Auth } from "@/ui/features/auth/Auth";
import "../login/Login.css";

/* The /signup screen: same centred, cork-board layout as /login. */
export function Signup({ next }: { next?: string }) {
  return (
    <Panel as="main" material="cork" className="login">
      <CaseBoard />
      <Auth mode="signup" next={next} />
    </Panel>
  );
}
