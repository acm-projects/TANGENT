"use client";

import { useEffect, useRef, useState } from "react";
import { api, apiErrorMessage } from "@/api";
import type { DebateBranch, DebateResult } from "@/api/types";
import { useDebateStore } from "@/store/debateStore";
import { useTreeStore } from "@/store/treeStore";
import { Button, Frame, Icon, Input, Link, Loading, Panel, Text } from "@/ui/library";
import { createBranches, openDebateNode } from "../debateActions";
import "../Debate.css";

/* The structured verdict behind a debate card (GET /debates/node/:id), pinned above its chat
 * (FRONTEND_DEBATE_MODE.md §8-9). The chat already holds the readable verdict; this adds what prose can't:
 * how settled it is, the scores, and the branches -- the questions the debate couldn't settle, each a
 * checkbox that becomes a new card beside the debate's.
 *
 * The same card closes the courtroom's record (`inCourt`, Debate.tsx), with the judge's summary under the
 * stamp; above the chat it offers the way back into the courtroom instead.
 *
 * A contested verdict leads with the branches: on a near-tie they are the answer, and the scores are the
 * evidence that it is close. Older debate nodes have no rubric or branches; those sections just don't show. */

const SIDE: Record<string, string> = { for: "For", against: "Against" };
const KIND_ICON: Record<string, string> = { research: "search", debate: "balance", open: "psychology" };
const WARNINGS = ["No clear winner.", "Treat this verdict with caution."];

/** The bold warning line the verdict opens with when its scores and its prose disagree, if any. */
function warningOf(finalOutput: string) {
  const first = finalOutput.trimStart().split("\n", 1)[0] ?? "";
  if (!WARNINGS.some((w) => first.startsWith(`**${w}**`))) return null;
  return first.replace(/\*\*/g, "");
}

const pct = (x: number) => `${Math.round(x * 100)}%`;

export function VerdictCard({ nodeId, inCourt = false }: { nodeId: string; inCourt?: boolean }) {
  const [result, setResult] = useState<DebateResult | null | undefined>(undefined);
  const [open, setOpen] = useState(false);
  const [entering, setEntering] = useState(false);
  const [enterError, setEnterError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.debates.result(nodeId).then(
      (r) => !cancelled && setResult(r),
      // 404: stopped before anyone argued, so there was nothing to judge. Any other failure just leaves the
      // card out: the chat below holds the readable verdict anyway.
      () => !cancelled && setResult(null),
    );
    return () => {
      cancelled = true;
    };
  }, [nodeId]);

  if (result === undefined) return <Loading label="Reading the verdict…" />;
  if (result === null) return null;

  const contested = result.winner === "no_clear_winner";
  const picked = result.end_reason === "user_picked";
  const rubric = result.scores?.rubric;
  const warning = warningOf(result.final_output ?? "");
  const judge = result.judge_would_have_chosen;
  const headline = contested
    ? "Contested"
    : picked
      ? `You chose ${SIDE[result.winner]}`
      : `${SIDE[result.winner]} wins${result.confidence < 0.65 ? ", narrowly" : ""}`;
  const subline = contested
    ? "Genuinely unsettled. The two sides came out close, and these are the questions that would decide it."
    : picked && judge && judge !== result.winner
      ? `The judge would have picked ${SIDE[judge] ?? "neither side"}.`
      : `Confidence ${pct(result.confidence)}`;

  const branches = result.branches?.length ? <Branches nodeId={nodeId} initial={result.branches} inCourt={inCourt} /> : null;

  return (
    <Panel as="section" className="verdict" data-winner={result.winner} data-in-court={inCourt || undefined} aria-label="Verdict">
      <Frame gap="3">
        {warning && (
          <Panel className="verdict-warning" role="note">
            <Frame direction="row" gap="2" align="center">
              <Icon icon="warning" size="s" />
              <Text size="s" content={warning} />
            </Frame>
          </Panel>
        )}
        <Frame gap="2" align="center" className="verdict-head">
          <Frame gap="0" align="center" className="debate-stamp" data-contested={contested || undefined} data-picked={picked || undefined}>
            <Text as="span" size="xxs" className="debate-kicker" content="Judgment of the court" />
            <Text as="h3" size="l" hierarchy="primary" className="debate-stamp-verdict" content={headline} />
          </Frame>
          <Text size="s" hierarchy="tertiary" className="verdict-subline" content={subline} />
          {inCourt && result.summary && <Text className="debate-summary" content={result.summary} />}
          {!inCourt && (
            <Button
              size="s"
              icon="balance"
              showIcon
              label={entering ? "Entering…" : "Enter the courtroom"}
              disabled={entering}
              onClick={() => {
                setEntering(true);
                setEnterError(null);
                openDebateNode(nodeId)
                  .catch((e: unknown) => setEnterError(apiErrorMessage(e, "Could not open the courtroom.")))
                  .finally(() => setEntering(false));
              }}
            />
          )}
          {enterError && <Text role="alert" size="s" className="debate-error" content={enterError} />}
        </Frame>

        {contested && branches}

        {result.scores && typeof result.scores.for === "number" && (
          <Frame gap="2" className="verdict-scores">
            <Frame direction="row" align="end" className="verdict-tally" aria-label="Scores out of 10">
              {(["for", "against"] as const).map((side) => (
                <Frame key={side} gap="0" align="center" className="verdict-side" data-lead={result.winner === side || undefined}>
                  <Text as="span" size="xxs" className="debate-kicker" content={`Counsel ${SIDE[side]!.toLowerCase()}`} />
                  <Text as="span" size="xxl" hierarchy="primary" className="verdict-score" content={result.scores?.[side]?.toFixed(1) ?? "–"} />
                </Frame>
              ))}
            </Frame>
            {rubric && (contested || result.confidence < 0.65) && (
              <Text
                size="xs"
                hierarchy="tertiary"
                className="verdict-rubric"
                content={[
                  rubric.gap !== undefined && `${rubric.gap.toFixed(2)} apart${rubric.margin !== undefined ? ` (a win needs ${rubric.margin})` : ""}`,
                  rubric.agreement !== undefined && rubric.judge_samples && `${Math.round(rubric.agreement * rubric.judge_samples)} of ${rubric.judge_samples} judge runs agreed`,
                ].filter(Boolean).join(" · ")}
              />
            )}
          </Frame>
        )}

        {!contested && branches}

        <Button size="s" hierarchy="tertiary" icon={open ? "expand_less" : "expand_more"} showIcon label={open ? "Hide the reasoning" : "Show the reasoning"} aria-expanded={open} onClick={() => setOpen(!open)} className="verdict-more" />
        {open && <Reasoning result={result} />}
      </Frame>
    </Panel>
  );
}

function Reasoning({ result }: { result: DebateResult }) {
  const criteria = result.scores?.rubric?.criteria;
  return (
    <Frame gap="3" className="verdict-reasoning">
      {criteria && (
        <List
          title="Scored on"
          items={Object.keys(criteria.for ?? {}).map((c) => `${c}: For ${criteria.for?.[c]?.toFixed(1)} · Against ${criteria.against?.[c]?.toFixed(1)}`)}
        />
      )}
      <List title="Strongest points against" items={result.strongest_counterpoints ?? []} />
      <List title="What would flip it" items={result.verdict_flips_if ?? []} />
      {!!result.citations?.length && (
        <Frame gap="1">
          <Text as="span" size="xxs" className="debate-kicker" content="Papers cited" />
          {result.citations.map((c, i) => (
            <Frame key={c.id ?? i} as="li" className="verdict-item">
              {c.url ? (
                <Link href={c.url} target="_blank" rel="noreferrer">
                  <Text as="span" size="xs" content={`${c.title}${c.year ? ` (${c.year})` : ""}`} />
                </Link>
              ) : (
                <Text size="xs" content={`${c.title}${c.year ? ` (${c.year})` : ""}`} />
              )}
            </Frame>
          ))}
        </Frame>
      )}
      <Text size="xs" hierarchy="tertiary" content={`For: ${result.for_model} · Against: ${result.against_model} · Judge: ${result.judge_model}`} />
    </Frame>
  );
}

function List({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <Frame as="ol" gap="1">
      <Text as="span" size="xxs" className="debate-kicker" content={title} />
      {items.map((item, i) => (
        <Frame key={i} as="li" className="verdict-item">
          <Text size="xs" content={item} />
        </Frame>
      ))}
    </Frame>
  );
}

/** "Where to go next": tick the questions worth a card, then make them. Ticks are saved on the server
 * (debounced, optimistic) so they survive a reload; a made branch becomes a link to its card. In the
 * courtroom, making cards or opening one steps back out to the board, where they are. */
function Branches({ nodeId, initial, inCourt }: { nodeId: string; initial: DebateBranch[]; inCourt: boolean }) {
  const [branches, setBranches] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const saved = useRef(initial);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const setActive = useTreeStore((s) => s.setActive);
  const onMap = useTreeStore((s) => s.nodesById);
  const toBoard = () => inCourt && useDebateStore.getState().setMinimised(true);
  useEffect(() => () => clearTimeout(timer.current), []);

  const toggle = (id: string, on: boolean) => {
    const next = branches.map((b) => (b.id === id ? { ...b, selected: on } : b));
    setBranches(next);
    setError(null);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      api.debates.selectBranches(nodeId, next.filter((b) => b.selected).map((b) => b.id)).then(
        (b) => (saved.current = b),
        (e: unknown) => {
          setBranches(saved.current);
          setError(apiErrorMessage(e, "Could not save your picks."));
        },
      );
    }, 400);
  };

  const chosen = branches.filter((b) => b.selected && !b.created_node_id);
  async function create() {
    if (busy || !chosen.length) return;
    setBusy(true);
    setError(null);
    try {
      const next = await createBranches(nodeId, chosen.map((b) => b.id));
      saved.current = next;
      setBranches(next);
      toBoard();
    } catch (e) {
      setError(apiErrorMessage(e, "Could not create the branches."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Frame gap="2" className="verdict-branches">
      <Frame gap="0">
        <Text as="h4" size="s" hierarchy="primary" className="verdict-headline" content="Matters left open" />
        <Text size="xs" hierarchy="tertiary" content="The court couldn't settle these. Each one you pick becomes a card beside it." />
      </Frame>
      <Frame as="ol" gap="2">
        {branches.map((b) => {
          const id = `branch-${nodeId}-${b.id}`;
          return (
            <Frame key={b.id} as="li" direction="row" gap="2" align="start" className="verdict-branch" data-done={b.created_node_id ? true : undefined}>
              {b.created_node_id ? (
                <Icon icon="check_circle" size="s" />
              ) : (
                <Input id={id} type="checkbox" checked={b.selected} onChange={(e) => toggle(b.id, e.target.checked)} />
              )}
              <Frame gap="0">
                <Frame direction="row" gap="1" align="center">
                  <Text as="label" htmlFor={b.created_node_id ? undefined : id} size="s" hierarchy="primary" content={b.title} />
                  <Icon icon={KIND_ICON[b.kind] ?? "help"} size="xs" hierarchy="tertiary" aria-label={b.kind} />
                  <Text as="span" size="xxs" hierarchy="tertiary" content={b.kind} />
                </Frame>
                <Text size="xs" content={b.question} />
                <Text size="xs" hierarchy="tertiary" className="verdict-why" content={b.why} />
                {b.created_node_id && (
                  <Button
                    size="s"
                    hierarchy="tertiary"
                    icon="arrow_forward"
                    iconAlign="right"
                    showIcon
                    label="Open card"
                    disabled={!onMap[b.created_node_id]}
                    onClick={() => {
                      setActive(b.created_node_id);
                      toBoard();
                    }}
                    className="verdict-open"
                  />
                )}
              </Frame>
            </Frame>
          );
        })}
      </Frame>
      {error && <Text role="alert" size="s" className="debate-error" content={error} />}
      <Frame direction="row" justify="end">
        <Button
          hierarchy="primary"
          icon="call_split"
          showIcon
          label={busy ? "Creating…" : chosen.length ? `Create ${chosen.length} card${chosen.length > 1 ? "s" : ""}` : "Pick a question"}
          disabled={busy || !chosen.length}
          onClick={() => void create()}
        />
      </Frame>
    </Frame>
  );
}
