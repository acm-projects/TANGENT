import { Frame } from "@/ui/library";
import { InviteCard } from "@/ui/features/auth/InviteCard";
import "../login/Login.css";

/* The /invite/{token} screen: same centred, dotted layout as /login. */
export function Invite({ token }: { token: string }) {
  return (
    <Frame as="main" align="center" className="login">
      <InviteCard token={token} />
    </Frame>
  );
}
