import { Decal, Panel } from "@/ui/library";
import { Board } from "./features/board/Board";
import "./Dashboard.css";

/* The /{slug}/dashboard screen: the board of projects, with every workspace
 * as a folder along the bottom. A server component -- it only arranges; the
 * board is the client feature that loads data (Rule 8). The page is cork,
 * with the clutter of a working board on it: scraps, a coffee ring, tape, a note,
 * a loose pin and a paperclip. */

type DashboardProps = { slug: string };

export function Dashboard({ slug }: DashboardProps) {
  return (
    <Panel as="main" material="cork" className="dashboard">
      <Decal kind="scrap" className="dashboard-decal dashboard-scrap" />
      <Decal kind="coffee-ring" className="dashboard-decal dashboard-ring" />
      <Decal kind="scrap" className="dashboard-decal dashboard-scrap-low" />
      <Decal kind="shape" className="dashboard-decal dashboard-tape" />
      <Decal kind="shape" className="dashboard-decal dashboard-note" />
      <Decal kind="shape" className="dashboard-decal dashboard-pin" />
      <Decal kind="paperclip" className="dashboard-decal dashboard-clip" />
      <Board slug={slug} />
    </Panel>
  );
}
