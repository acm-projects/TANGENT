import type { ProjectSummary } from "@/api/types";
import { Panel, Text } from "@/ui/library";
import { useIsLastCase } from "@/ui/features/last-case/lastCase";
import { fileNumber } from "@/ui/features/case-file/fileNumber";
import { lastWorked, tiltOf } from "../sketch";
import { useTreePreview } from "../useTreePreview";
import { CaseSketch } from "./CaseSketch";

/* The look of a project card, shared by the grid and the folder it tucks into:
 * a paper case card pinned to the board, its picture the project's tree, the
 * name written underneath, and when it was last worked on. A closed case is stamped so. Sized in em off its slot's width
 * (Board.css), so a card in a folder is the grid card, smaller: the flight
 * between them is a clean zoom. */

export function CardFace({ project }: { project: ProjectSummary }) {
  const last = useIsLastCase(project.id);
  const facts = useTreePreview(project.id);
  const worked = facts ? lastWorked(facts.lastActive) : null;
  const meta = facts ? `${facts.cards} ${facts.cards === 1 ? "card" : "cards"} · worked ${worked}` : "";
  // a one-card case has no tree to photograph yet: its photo says so instead of showing a lone card
  const fresh = facts !== null && facts !== undefined && facts.cards < 2;
  const stamp = facts?.status === "closed" ? "Closed" : project.role === "shared" ? "Shared" : null;
  return (
    <Panel
      material="paper"
      stock={tiltOf(project.id) === 1 ? "card" : "card-alt"}
      edge="torn"
      elevation="floating"
      className={last ? "case-card case-card-last" : "case-card"}
      data-status={facts?.status}
    >
      <span className="case-card-pin" aria-hidden="true" />
      <Text as="span" face="stamp" size="xxs" className="case-card-kicker" content={last ? `No. ${fileNumber(project.id)} · Last open` : `No. ${fileNumber(project.id)}`} />
      <span className="case-card-photo" data-fresh={fresh || undefined}>
        {fresh ? <Text as="span" face="stamp" size="xxs" className="case-card-fresh" content="A fresh case" /> : facts && <CaseSketch sketch={facts.sketch} />}
      </span>
      <Text as="h3" face="heading" hierarchy="primary" className="case-card-name" content={project.project_name} />
      <Text size="xs" hierarchy="tertiary" className="case-card-meta" content={meta} />
      {stamp && <Text as="span" face="stamp" className="case-card-stamp" data-stamp={stamp.toLowerCase()} content={stamp} />}
    </Panel>
  );
}
