"use client";

import { useEffect, useRef, useState } from "react";
import { apiErrorMessage } from "@/api";
import { speaking, visibleEntries, waiting, useDebateStore, type DebateEntry, type DebateTurn, type DebateView } from "@/store/debateStore";
import { useTreeStore } from "@/store/treeStore";
import { Button, DangerButton, Frame, Icon, Loading, Panel, Popup, Text } from "@/ui/library";
import { QuestionCard } from "./components/QuestionCard";
import { cancelDebate, dismissDebate, leaveDebate, resumeDebate, steerDebate } from "./debateActions";
import "./Debate.css";

/* The debate in session (FRONTEND_DEBATE_MODE.md §5-7): a sheet floating at the bottom of the board that
 * plays the proceedings back one speaker at a time, asks the user the court's questions, and offers the
 * levers (skip the typing, have the judge decide now, pick a side, throw it away). It picks up the
 * project's last debate on load, since a debate outlives the tab. When the verdict lands the new card is
 * on the map and this offers to open it.
 *
 * Drawn as a courtroom (§11): the bench and the two counsel tables up top, with whoever has the floor
 * lit, and the proceedings below as a court reporter's transcript. Model names stay hidden while it runs: the judge sees anonymised positions on purpose. */

type DebateProps = { projectId: string; className?: string };

const SPEAKER: Record<string, string> = { for: "For", against: "Against", judge: "The judge" };
/** Speaker names as the transcript prints them. */
const REPORTED: Record<string, string> = { for: "For", against: "Against", judge: "The Court" };
const PHASE: Record<string, string> = {
  intake: "Reading the case",
  frame: "Framing the question",
  research: "Counsel at the library",
  opening: "Opening statements",
  closing: "Closing statements",
  judging: "The judge deliberates",
};
const phaseLabel = (phase: string, round: number) => (phase === "rebuttal" ? `Rebuttal ${round}` : (PHASE[phase] ?? phase));

const FAILED: Record<string, string> = {
  expired: "This debate expired before it finished. Start a new one from the card.",
};

/** Seconds per playback frame. */
const FRAME = 0.05;

export function Debate({ projectId, className }: DebateProps) {
  const view = useDebateStore((s) => s.view);
  const dispatch = useDebateStore((s) => s.dispatch);
  const [collapsed, setCollapsed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmingEnd, setConfirmingEnd] = useState(false);

  useEffect(() => {
    void resumeDebate(projectId);
    return leaveDebate;
  }, [projectId]);

  // Playback: type the speaker's text out a frame at a time. Reduced motion shows it as it arrives.
  const behind = view ? view.stage < view.log.length : false;
  useEffect(() => {
    if (!behind) return;
    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const timer = setInterval(() => dispatch({ type: "tick", dt: still ? Infinity : FRAME }), FRAME * 1000);
    return () => clearInterval(timer);
  }, [behind, dispatch]);

  // keep the newest line in view as the proceedings play
  const logRef = useRef<HTMLOListElement>(null);
  const speaker = view ? speaking(view) : null;
  const scrollKey = `${view?.stage}:${speaker?.shown}:${view?.notes.for.length}:${view?.notes.against.length}`;
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [scrollKey]);

  if (!view) return null;
  const classes = ["debate", className].filter(Boolean).join(" ");
  const status = view.info?.status;
  const live = !view.ended;

  if (collapsed) {
    return (
      <Frame className={classes} data-collapsed>
        <Button
          elevation="floating"
          icon="gavel"
          showIcon
          label={live ? "Debate in session" : "Debate finished"}
          onClick={() => setCollapsed(false)}
        />
      </Frame>
    );
  }

  const act = (action: () => Promise<unknown>, fallback: string) => () => {
    setError(null);
    action().catch((e: unknown) => setError(apiErrorMessage(e, fallback)));
  };
  const ready = waiting(view);

  return (
    <Panel as="section" elevation="floating" className={classes} aria-label="Debate">
      <Frame gap="3">
        <Frame as="header" gap="1" className="debate-caption">
          <Frame direction="row" justify="between" align="center">
            <Frame direction="row" gap="2" align="center">
              <Icon icon="balance" size="s" hierarchy="tertiary" />
              <Text as="span" size="xxs" className="debate-kicker" content={live ? "Court in session" : "Court adjourned"} />
              <Text as="span" size="xxs" className="debate-docket" content={`No. ${view.id.slice(0, 6).toUpperCase()}`} />
            </Frame>
            <Frame direction="row" gap="1">
              <Button size="s" hierarchy="tertiary" icon="expand_more" showIcon showLabel={false} label="Minimise debate" onClick={() => setCollapsed(true)} />
              {!live && (
                <Button size="s" hierarchy="tertiary" icon="close" showIcon showLabel={false} label="Dismiss debate" onClick={() => dismissDebate(projectId)} />
              )}
            </Frame>
          </Frame>
          <Frame gap="0" align="center" className="debate-matter">
            <Text as="span" size="xs" hierarchy="tertiary" className="debate-inre" content="In re" />
            <Text as="h2" size="m" hierarchy="primary" className="debate-title" content={view.info?.topic ?? "Debate"} />
          </Frame>
        </Frame>

        <Bench view={view} />

        <Frame as="ol" gap="2" ref={logRef} className="debate-log debate-transcript" aria-live="polite" aria-label="Proceedings">
          {(status === "queued" || !view.info) && live && view.log.length === 0 && (
            <Frame as="li">
              <Loading label="The court is assembling…" />
            </Frame>
          )}
          {visibleEntries(view).map((entry, i) => (
            <Entry key={i} entry={entry} view={view} />
          ))}
        </Frame>

        {live && ready.length > 0 && (
          <Text size="xs" hierarchy="tertiary" className="debate-ready" content={`${ready.map((t) => SPEAKER[t.side]).join(", ")} ready`} />
        )}

        {view.questions && view.questions.length > 0 && <QuestionCard key={view.questions.map((q) => q.id).join()} debateId={view.id} questions={view.questions} />}

        <Outcome view={view} />

        {error && <Text role="alert" size="s" className="debate-error" content={error} />}

        {live && (
          <Frame direction="row" gap="2" justify="between" align="center" className="debate-controls">
            {view.wrappingUp ? (
              <Loading label="Wrapping up…" />
            ) : (
              <Frame direction="row" gap="1">
                <Button size="s" icon="gavel" showIcon label="Judge now" title="Skip the rest: the judge decides on what has been argued" onClick={act(() => steerDebate(view.id, "stop"), "Could not stop the debate.")} />
                <Button size="s" label="Side with For" title="You decide: For closes, and the judge writes its case" onClick={act(() => steerDebate(view.id, "pick_side", "for"), "Could not pick a side.")} />
                <Button size="s" label="Side with Against" title="You decide: Against closes, and the judge writes its case" onClick={act(() => steerDebate(view.id, "pick_side", "against"), "Could not pick a side.")} />
              </Frame>
            )}
            <Frame direction="row" gap="1">
              {behind && <Button size="s" hierarchy="tertiary" icon="fast_forward" showIcon label="Skip" onClick={() => dispatch({ type: "tick", dt: Infinity })} />}
              <Button size="s" hierarchy="tertiary" icon="block" showIcon label="End" onClick={() => setConfirmingEnd(true)} />
            </Frame>
          </Frame>
        )}
      </Frame>

      <Popup open={confirmingEnd} onClose={() => setConfirmingEnd(false)} title="End this debate?">
        <Text content="Everything argued so far is thrown away and no verdict card is made. To keep a verdict, use Judge now instead." />
        <Frame direction="row" gap="2" justify="end">
          <Button label="Keep going" onClick={() => setConfirmingEnd(false)} />
          <DangerButton
            data-primary
            label="Hold to end"
            icon="block"
            commitTime={800}
            showIcon
            onHold={() => {
              setConfirmingEnd(false);
              act(() => cancelDebate(view.id), "Could not end the debate.")();
            }}
          />
        </Frame>
      </Popup>
    </Panel>
  );
}

/** The room: the judge on the bench, counsel at their tables with their latest working notes (both can
 * think while one speaks), and whoever has the floor lit. */
function Bench({ view }: { view: DebateView }) {
  const floor = speaking(view)?.side ?? null;
  const ready = new Set(waiting(view).map((t) => t.side));
  const phase = visibleEntries(view).findLast((e) => e.kind === "phase");
  const presiding = !view.ended && phase?.kind === "phase" ? phaseLabel(phase.phase, phase.round) : view.ended ? "Judgment entered" : "Presiding";
  const status = (side: "for" | "against") => (view.ended ? "Rests" : floor === side ? "Has the floor" : ready.has(side) ? "Ready to speak" : view.notes[side].length ? "Taking notes" : "Seated");
  return (
    <Frame className="debate-room" aria-label="The courtroom">
      <Frame align="center" gap="0" className="debate-bench" data-floor={floor === "judge" || undefined} data-ruled={view.ended || undefined}>
        <Icon icon="gavel" size="m" className="debate-bench-gavel" />
        <Text as="span" size="xxs" className="debate-kicker" content="The bench" />
        <Text as="span" size="xs" hierarchy="tertiary" content={presiding} />
      </Frame>
      <Frame direction="row" gap="3" className="debate-tables">
        {(["for", "against"] as const).map((side) => (
          <Frame key={side} gap="1" className="debate-table" data-side={side} data-floor={floor === side || undefined}>
            <Frame direction="row" gap="1" align="center" justify={side === "for" ? "start" : "end"} className="debate-placard">
              <Text as="span" size="xxs" className="debate-kicker" content={`Counsel ${SPEAKER[side]!.toLowerCase()}`} />
            </Frame>
            <Text as="span" size="xxs" hierarchy="tertiary" className="debate-table-status" content={status(side)} />
            {view.notes[side].length > 0 && (
              <Frame className="debate-pad">
                <Text size="xs" hierarchy="tertiary" content={view.notes[side].at(-1)!} />
              </Frame>
            )}
          </Frame>
        ))}
      </Frame>
    </Frame>
  );
}

function Entry({ entry, view }: { entry: DebateEntry; view: DebateView }) {
  if (entry.kind === "phase") {
    return (
      <Frame as="li" direction="row" align="center" gap="2" className="debate-phase">
        <Text as="span" size="xxs" className="debate-kicker" content={phaseLabel(entry.phase, entry.round)} />
      </Frame>
    );
  }
  if (entry.kind === "search") {
    return (
      <Frame as="li" className="debate-search">
        <Text size="xs" hierarchy="tertiary" content={`(${SPEAKER[entry.side] ?? "Counsel"} consults the record: “${entry.query}”)`} />
      </Frame>
    );
  }
  if (entry.kind === "control") {
    const what = entry.action === "stop" ? "(The gallery calls for judgment: the Court rules on what has been argued.)" : `(The gallery sides with ${SPEAKER[entry.side ?? ""] ?? "a side"}.)`;
    return (
      <Frame as="li" className="debate-search">
        <Text size="xs" hierarchy="tertiary" content={what} />
      </Frame>
    );
  }
  return <Speech turn={view.turns[entry.id]!} speaking={speaking(view)?.id === entry.id} />;
}

function Speech({ turn, speaking }: { turn: DebateTurn; speaking: boolean }) {
  return (
    <Frame as="li" direction="row" gap="3" className="debate-turn" data-side={turn.side} data-speaking={speaking || undefined}>
      <Frame gap="0" className="debate-speaker">
        <Text as="span" size="xxs" className="debate-kicker" content={`${REPORTED[turn.side] ?? turn.side}:`} />
        {turn.truncated && <Text as="span" size="xxs" hierarchy="tertiary" content="(cut short)" />}
      </Frame>
      <Text size="s" className="debate-speech" content={turn.text.slice(0, turn.shown)} />
    </Frame>
  );
}

/** How it ended: the verdict and a way to its card, or why there is none. */
function Outcome({ view }: { view: DebateView }) {
  const setActive = useTreeStore((s) => s.setActive);
  const onMap = useTreeStore((s) => Boolean(view.nodeId && s.nodesById[view.nodeId]));
  if (!view.ended || !view.info) return null;
  const { status, error_code } = view.info;
  if (status === "cancelled") return <Text size="s" hierarchy="tertiary" content="Debate ended. Nothing was kept." />;
  if (status === "failed") {
    return <Text role="alert" size="s" className="debate-error" content={FAILED[error_code ?? ""] ?? `The debate failed${error_code ? ` (${error_code})` : ""}. Start it again from the card.`} />;
  }
  const v = view.verdict;
  const headline = !v
    ? "The verdict is in."
    : v.winner_side === "for" || v.winner_side === "against"
      ? `${SPEAKER[v.winner_side]} wins${v.confidence !== null && v.confidence < 0.65 ? ", narrowly" : ""}.`
      : "Genuinely unsettled: neither side carried it.";
  return (
    <Frame gap="2" align="center" className="debate-outcome">
      <Frame gap="0" align="center" className="debate-stamp" data-contested={v && v.winner_side !== "for" && v.winner_side !== "against" ? true : undefined}>
        <Text as="span" size="xxs" className="debate-kicker" content="Judgment" />
        <Text as="h3" size="l" hierarchy="primary" className="debate-stamp-verdict" content={headline} />
      </Frame>
      {v?.summary && <Text size="s" className="debate-summary" content={v.summary} />}
      {view.nodeId && (
        <Frame direction="row" justify="center">
          <Button
            hierarchy="primary"
            icon="arrow_forward"
            iconAlign="right"
            showIcon
            label="Open the verdict"
            disabled={!onMap}
            title={onMap ? undefined : "The verdict card is in another project"}
            onClick={() => view.nodeId && setActive(view.nodeId)}
          />
        </Frame>
      )}
    </Frame>
  );
}
