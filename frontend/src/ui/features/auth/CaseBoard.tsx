import { Decal, Frame, Panel, Text } from "@/ui/library";
import "./CaseBoard.css";

/* The backdrop behind the auth card: a detective board, out of focus (cards, pins, string and a scrap). Case
 * cards are pinned around the edges and string runs from each of them in to
 * the card at the centre. Decorative only, hidden from assistive tech, and
 * hidden on narrow screens where it would crowd the card. Positions and the
 * string paths are in CaseBoard.css, in percent of the screen, so they meet. */

const CASES = [
  { exhibit: "Exhibit A", title: "Why did Rome fall?" },
  { exhibit: "Exhibit B", title: "Is attention all you need?" },
  { exhibit: "Exhibit C", title: "Light roast vs dark roast" },
  { exhibit: "Exhibit D", title: "Sourdough starter timing" },
];

export function CaseBoard() {
  return (
    <Frame gap="0" className="case-board" aria-hidden="true">
      {CASES.map((c) => (
        <Panel key={c.exhibit} stock="card" edge="torn" elevation="floating" className="case-board-card">
          <span aria-hidden="true" className="case-board-pin" />
          <Frame gap="1">
            <Text as="span" face="stamp" size="xxs" hierarchy="tertiary" content={c.exhibit} />
            <Text as="h3" size="m" hierarchy="primary" content={c.title} />
          </Frame>
        </Panel>
      ))}
      <Decal kind="scrap" className="case-board-scrap" />
      <Frame gap="0" className="case-board-strings" />
    </Frame>
  );
}
