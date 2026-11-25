import { Decal, Panel } from "@/ui/library";
import { Board } from "./features/board/Board";
import "./Dashboard.css";

/* The /{slug}/dashboard screen: the board of projects, with every workspace
 * as a folder along the bottom. A server component -- it only arranges; the
 * board is the client feature that loads data (Rule 8). The page is cork,
 * with a torn scrap and a coffee ring set down on it. */

type DashboardProps = { slug: string };

export function Dashboard({ slug }: DashboardProps) {
  return (
    <Panel as="main" material="cork" className="dashboard">
      <Decal kind="scrap" className="dashboard-decal dashboard-scrap" />
      <Decal kind="coffee-ring" className="dashboard-decal dashboard-ring" />
      <Board slug={slug} />
    </Panel>
  );
}
