import { Panel } from "@/ui/library";
import { CaseBoard } from "@/ui/features/auth/CaseBoard";
import { Auth } from "@/ui/features/auth/Auth";
import "./Login.css";

/* The /login screen: centres the Auth feature on the cork board. */
export function Login({ next }: { next?: string }) {
  return (
    <Panel as="main" material="cork" className="login">
      <CaseBoard />
      <Auth mode="login" next={next} />
    </Panel>
  );
}
