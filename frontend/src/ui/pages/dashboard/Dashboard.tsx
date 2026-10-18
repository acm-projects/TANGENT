import { Board } from "./features/board/Board";
import "./Dashboard.css";

/* The /{slug}/dashboard screen: the board of projects, with every workspace
 * as a folder along the bottom. A server component -- it only arranges; the
 * board is the client feature that loads data (Rule 8). */

type DashboardProps = { slug: string };

export function Dashboard({ slug }: DashboardProps) {
  return (
    <main className="dashboard">
      <Board slug={slug} />
    </main>
  );
}
