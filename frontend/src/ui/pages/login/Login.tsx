import { Frame } from "@/ui/library";
import { Auth } from "@/ui/features/auth/Auth";
import "./Login.css";

/* The /login screen: centres the Auth feature on a dotted background. */
export function Login() {
  return (
    <Frame as="main" align="center" className="login">
      <Auth />
    </Frame>
  );
}
