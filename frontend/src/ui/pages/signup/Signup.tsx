import { Frame } from "@/ui/library";
import { CaseBoard } from "@/ui/features/auth/CaseBoard";
import { Auth } from "@/ui/features/auth/Auth";
import "../login/Login.css";

/* The /signup screen: same centred, dotted layout as /login. */
export function Signup({ next }: { next?: string }) {
  return (
    <Frame as="main" align="center" className="login">
      <CaseBoard />
      <Auth mode="signup" next={next} />
    </Frame>
  );
}
