import { Panel } from "@/ui/library";
import { CaseBoard } from "@/ui/features/auth/CaseBoard";
import { InviteCard } from "@/ui/features/auth/InviteCard";
import "../login/Login.css";

/* The /invite/{token} screen: same centred, cork-board layout as /login. */
export function Invite({ token }: { token: string }) {
  return (
    <Panel as="main" material="cork" className="login">
      <CaseBoard />
      <InviteCard token={token} />
    </Panel>
  );
}
