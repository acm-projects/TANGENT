import { SessionGate } from "@/features/auth";
import { Panel } from "@/ui/components";
import { WorkspaceSetupForm } from "./features/workspace-setup";
import "./Onboarding.css";

/* Server component: it arranges features and holds no state or fetching of its
 * own (DESIGN.md Rule 8). SessionGate and the form carry "use client". */

export function Onboarding() {
  return (
    <main className="onboarding">
      <SessionGate>
        <Panel className="onboarding-panel">
          <h1 className="onboarding-title">Name your workspace</h1>
          <p className="onboarding-subtitle">You can change this later.</p>
          <WorkspaceSetupForm />
        </Panel>
      </SessionGate>
    </main>
  );
}
