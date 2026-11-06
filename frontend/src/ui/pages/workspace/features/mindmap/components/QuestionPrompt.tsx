"use client";

import { useId, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { apiErrorMessage } from "@/api";
import type { NodeMeta } from "@/api/types";
import { Button, Frame, Icon, Input, Text } from "@/ui/library";
import { selectExhibits, useTreeStore } from "@/store/treeStore";
import { useChatLayout } from "@/store/chatLayout";
import { answerQuestion } from "../nodeActions";

/* A question card's question, held inside the card on the map: an AI wasn't sure what the user wants and asks, grilling style:
 * its pick is marked Recommended (never pre-selected), and the user's own words are always an option. Clicking a
 * choice only selects it; nothing is sent until Answer. Each answer opens a branch: the next question of the
 * chain, or the card where the research continues. Answering again a different way opens another branch; the ways
 * it was answered before link to theirs. Styles: ../MindMap.css. */

type QuestionPromptProps = { node: NodeMeta };

const said = (a: string | string[]) => (Array.isArray(a) ? a.join(", ") : a);
const same = (a: string | string[], b: string | string[]) => said(a) === said(b);

export function QuestionPrompt({ node }: QuestionPromptProps) {
  const q = node.question!;
  const exhibits = useTreeStore(useShallow((s) => selectExhibits(s)));
  const [picked, setPicked] = useState<string[]>([]);
  const [own, setOwn] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const base = useId();

  async function send(answer: string | string[]) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const done = await answerQuestion(node.id, answer);
      if (done?.continuePrompt) useChatLayout.getState().continueIn(done.nodeId, done.continuePrompt);
    } catch (e) {
      setError(apiErrorMessage(e, "Could not send your answer."));
    } finally {
      setBusy(false);
    }
  }

  /** the branch an answer opened before, as a link to it */
  const branchOf = (answer: string | string[]) => {
    const past = q.answers.find((a) => same(a.answer, answer));
    if (!past) return null;
    return (
      <Button
        hierarchy="tertiary"
        size="xs"
        label={`→ ${exhibits[past.node_id] ?? "its branch"}`}
        title={past.by === "gent" ? "Answered by Gent: open that branch" : "Answered before: open that branch"}
        data-author={past.by === "gent" ? "gent" : undefined}
        onClick={() => useTreeStore.getState().setActive(past.node_id)}
        className="question-branch"
      />
    );
  };
  const asker = q.asker.by === "gent" ? "Gent asks" : "This card's model asks";
  const multiChoice = q.type === "multi";
  const others = q.answers.filter((a) => !q.options.some((o) => same(o.label, a.answer)));
  // what Answer sends: the picked choice(s), plus the user's own words if they wrote any
  const words = own.trim();
  const answer: string | string[] = multiChoice ? (words ? [...picked, words] : picked) : (words || picked[0] || "");
  const ready = multiChoice ? answer.length > 0 : Boolean(answer);

  return (
    // its own pointer presses aren't the card's drag (down branches, up deletes: DragAction.tsx)
    <Frame as="section" gap="0" className="question-prompt nodrag nopan" aria-label="A question for you" onPointerDown={(e) => e.stopPropagation()}>
      <Frame gap="3">
        <Frame direction="row" gap="1" align="center">
          <Icon icon="help" size="s" />
          <Text as="span" size="xxs" className="question-kicker" content={`${asker}${q.trail.length ? ` · question ${q.trail.length + 1}` : ""}`} />
        </Frame>
        {q.trail.map((t) => (
          <Text key={t.prompt} size="xs" hierarchy="tertiary" content={`${t.prompt} ${said(t.answer)}`} />
        ))}
        <Text id={base} as="h3" size="m" hierarchy="primary" content={q.prompt} />
        {multiChoice && <Text size="xs" hierarchy="tertiary" content="Pick one or more" />}
        <Frame gap="2" role="group" aria-labelledby={base}>
          {/* the asker's pick goes first, unstyled: only its place and label say it's recommended */}
          {[...q.options].sort((a, b) => Number(b.label === q.recommended) - Number(a.label === q.recommended)).map((o) => {
            const recommended = o.label === q.recommended;
            const label = `${o.label}${recommended ? " (Recommended)" : ""}`;
            return (
              <Frame key={o.label} direction="row" gap="2" align="center" className="question-option">
                {/* a click only picks it (one choice: it replaces the pick and own words; several: it toggles); Answer sends */}
                <button
                  type="button"
                  className="question-choice"
                  aria-pressed={picked.includes(o.label)}
                  disabled={busy}
                  onClick={() =>
                    multiChoice
                      ? setPicked((p) => (p.includes(o.label) ? p.filter((l) => l !== o.label) : [...p, o.label]))
                      : (setPicked([o.label]), setOwn(""))
                  }
                >
                  <Text as="span" size="s" content={label} />
                  {o.description && <Text as="span" size="xs" hierarchy="tertiary" content={o.description} />}
                </button>
                {!multiChoice && branchOf(o.label)}
              </Frame>
            );
          })}
          {others.map((a) => (
            <Frame key={a.node_id} direction="row" gap="2" align="center" className="question-option">
              <Text as="span" size="s" hierarchy="secondary" content={`“${said(a.answer)}”`} />
              {branchOf(a.answer)}
            </Frame>
          ))}
        </Frame>
        <Input
          aria-label={`Your own answer: ${q.prompt}`}
          placeholder="Or in your own words…"
          value={own}
          maxLength={300}
          // a single-choice question takes one answer: own words replace a picked choice
          onChange={(e) => (setOwn(e.target.value), !multiChoice && setPicked([]))}
          onKeyDown={(e) => e.key === "Enter" && ready && (e.preventDefault(), void send(answer))}
          className="question-other"
        />
        <Frame direction="row" gap="2" align="center" justify="end">
          {multiChoice && picked.length > 0 && branchOf(q.options.map((o) => o.label).filter((l) => picked.includes(l)))}
          <Button hierarchy="primary" label={busy ? "Sending…" : "Answer"} disabled={busy || !ready} onClick={() => void send(answer)} />
        </Frame>
        {error && <Text role="alert" size="s" className="question-error" content={error} />}
      </Frame>
    </Frame>
  );
}
