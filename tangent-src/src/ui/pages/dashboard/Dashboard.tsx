import { Frame, Icon, Panel, Text } from "@/ui/library";
import { Projects } from "./features/projects/Projects";
import "./Dashboard.css";

/* The /{slug}/dashboard screen (Figma "Dashboard", node 313:9882): a title
 * bar, then the project grid. A server component -- it only arranges; the
 * grid is the client feature that loads data (Rule 8). */

type DashboardProps = { slug: string };

export function Dashboard({ slug }: DashboardProps) {
  return (
    <Frame as="main" gap="4" className="dashboard">
      <Panel as="header" elevation="floating" className="dashboard-title">
        <Frame direction="row" gap="4" align="center">
          <Icon icon="home" size="display" hierarchy="primary" className="dashboard-title-icon" />
          <Text as="h1" size="display" hierarchy="primary" content="Dashboard" />
        </Frame>
      </Panel>

      <Frame as="section" gap="2" className="dashboard-projects" aria-labelledby="dashboard-projects-heading">
        {/* Figma says "Workspaces"; each card is a backend *project*. See docs/HANDOFF.md. */}
        <Text as="h2" id="dashboard-projects-heading" size="xl" className="dashboard-heading" content="Recent Workspaces" />
        <Projects slug={slug} />
      </Frame>
    </Frame>
  );
}
