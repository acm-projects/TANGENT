import { SessionGate } from "@/features/auth";
import "./Dashboard.css";

/* Placeholder: the backend redirects here after login. The real workspace UI
 * (tree, chat, toolbar) is scaffolded separately under ui/pages/workspace/. */

export function Dashboard() {
  return (
    <main className="dashboard">
      <SessionGate>
        <h1 className="dashboard-title">Dashboard</h1>
      </SessionGate>
    </main>
  );
}
