import type { ProjectSummary } from "@/api/types";
import { Panel, Text } from "@/ui/library";
import { useTreePreview } from "../useTreePreview";
import { CaseSketch } from "./CaseSketch";

/* The look of a project card, shared by the grid and the folder it tucks into:
 * an instant photo pinned to the board, its picture the project's tree, the
 * name written underneath. Sized in em off its slot's width
 * (Board.css), so a card in a folder is the grid card, smaller: the flight
 * between them is a clean zoom. */

const created = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });

export function CardFace({ project }: { project: ProjectSummary }) {
  const pins = useTreePreview(project.id);
  const meta = pins ? `${pins.length} ${pins.length === 1 ? "card" : "cards"} · ${created(project.created_at)}` : created(project.created_at);
  return (
    <Panel elevation="floating" className="case-card">
      <span className="case-card-pin" aria-hidden="true" />
      <span className="case-card-photo">
        {pins && <CaseSketch pins={pins} />}
      </span>
      <Text as="h3" hierarchy="primary" className="case-card-name" content={project.project_name} />
      <Text size="xs" hierarchy="tertiary" className="case-card-meta" content={meta} />
      {project.role === "shared" && <Text as="span" className="case-card-stamp" content="Shared" />}
    </Panel>
  );
}
