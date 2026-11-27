/* The people in the courtroom, as figures cut from the desk's paper: counsel standing at a lectern on either side,
 * the judge raised behind the bench in the middle. Flat shapes in the theme's paper and ink (Debate.css colours
 * them through --fig-* properties), so they sit in both Day and Night. Decorative: the placards and the transcript
 * say who is who.
 *
 * `speaking` lifts counsel's arm and leans them toward the room; the judge raises the gavel. Debate.css animates both. */

type CourtFigureProps = {
  role: "counsel" | "judge";
  /** which way counsel faces: For stands on the left facing right, Against the reverse */
  facing?: "left" | "right";
  speaking?: boolean;
};

export function CourtFigure({ role, facing = "right", speaking = false }: CourtFigureProps) {
  return role === "judge" ? <Judge speaking={speaking} /> : <Counsel facing={facing} speaking={speaking} />;
}

function Counsel({ facing, speaking }: { facing: "left" | "right"; speaking: boolean }) {
  return (
    <svg
      viewBox="0 0 120 170"
      className="court-figure"
      data-role="counsel"
      data-facing={facing}
      data-speaking={speaking || undefined}
      aria-hidden="true"
    >
      <g className="court-figure-body">
        {/* the cut's shadow on the wall, a step behind the paper */}
        <g className="court-figure-shadow" transform="translate(3 3)">
          <circle cx="60" cy="34" r="17" />
          <path d="M28 150 C28 92 36 64 60 62 C84 64 92 92 92 150 Z" />
        </g>
        <path className="court-figure-suit" d="M28 150 C28 92 36 64 60 62 C84 64 92 92 92 150 Z" />
        {/* shirt front and the lapels' V */}
        <path className="court-figure-shirt" d="M50 66 L60 96 L70 66 Z" />
        <path className="court-figure-line" d="M60 72 L60 96" />
        <circle className="court-figure-head" cx="60" cy="34" r="17" />
        {/* the arm that argues: down at rest, raised toward the room while speaking */}
        <g className="court-figure-arm">
          <path className="court-figure-suit" d="M84 76 C96 84 100 100 98 118 L88 118 C88 104 84 94 78 88 Z" />
          <circle className="court-figure-head" cx="93" cy="121" r="6" />
        </g>
      </g>
      {/* the lectern in front, its top edge catching the lamp */}
      <path className="court-figure-shadow" d="M23 117 L101 117 L95 170 L29 170 Z" />
      <path className="court-figure-wood" d="M20 114 L100 114 L94 170 L26 170 Z" />
      <path className="court-figure-edge" d="M18 112 L102 112 L102 118 L18 118 Z" />
    </svg>
  );
}

function Judge({ speaking }: { speaking: boolean }) {
  return (
    <svg viewBox="0 0 140 96" className="court-figure" data-role="judge" data-speaking={speaking || undefined} aria-hidden="true">
      <g className="court-figure-shadow" transform="translate(3 3)">
        <circle cx="70" cy="30" r="18" />
        <path d="M30 96 C30 66 44 52 70 50 C96 52 110 66 110 96 Z" />
      </g>
      {/* the robe, and the white bands at the collar */}
      <path className="court-figure-robe" d="M30 96 C30 66 44 52 70 50 C96 52 110 66 110 96 Z" />
      <path className="court-figure-shirt" d="M64 54 L70 72 L76 54 Z" />
      <path className="court-figure-line" d="M70 58 L70 72" />
      <circle className="court-figure-head" cx="70" cy="30" r="18" />
      {/* the gavel in hand, raised while the Court speaks */}
      <g className="court-figure-gavel">
        <path className="court-figure-wood" d="M104 74 L118 60 L121 63 L107 77 Z" />
        <path className="court-figure-wood" d="M112 50 L128 66 L122 72 L106 56 Z" />
      </g>
    </svg>
  );
}
