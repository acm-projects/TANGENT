import { Panel } from "@/ui/components";
import { GoogleSignInButton } from "./features/google-sign-in";
import "./Login.css";

/* No "use client": this page only arranges. The one interactive piece is the
 * sign-in button, which carries the directive itself (DESIGN.md Rule 9). */

export function Login() {
  return (
    <main className="login">
      <Panel className="login-panel">
        <h1 className="login-title">Welcome to TANGENT</h1>
        <p className="login-subtitle">Sign in or create an account to continue.</p>
        <GoogleSignInButton />
      </Panel>
    </main>
  );
}
