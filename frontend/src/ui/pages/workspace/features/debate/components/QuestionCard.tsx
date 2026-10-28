"use client";

import { useId, useState } from "react";
import { apiErrorMessage } from "@/api";
import type { DebateQuestion } from "@/api/types";
import { Button, Frame, Input, Panel, Text } from "@/ui/library";
import { answerQuestions } from "../debateActions";

/* The court turns to the user: every open question on one card, answered once. `single` is a radio choice,
 * `multi` checkboxes, and `allow_other` adds the user's own words. Answers are sent as the option's label
 * text, never its position. Skip lets the debate decide. */

type QuestionCardProps = { debateId: string; questions: DebateQuestion[] };

export function QuestionCard({ debateId, questions }: QuestionCardProps) {
  const [picked, setPicked] = useState<Record<string, string[]>>({});
  const [other, setOther] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const base = useId();

  const answerFor = (q: DebateQuestion): string | string[] | null => {
    const own = other[q.id]?.trim();
    const chosen = picked[q.id] ?? [];
    if (q.type === "multi") return own || chosen.length ? [...chosen, ...(own ? [own] : [])] : null;
    return own || chosen[0] || null;
  };

  async function send(skip: boolean) {
    if (busy) return;
    const answers: Record<string, string | string[]> = {};
    if (!skip) for (const q of questions) {
      const a = answerFor(q);
      if (a !== null) answers[q.id] = a;
    }
    setBusy(true);
    setError(null);
    try {
      // a question left blank is skipped (the server lets the debate decide it)
      await answerQuestions(debateId, answers, skip || Object.keys(answers).length === 0);
    } catch (e) {
      setError(apiErrorMessage(e, "Could not send your answer."));
      setBusy(false);
    }
  }

  const toggle = (q: DebateQuestion, label: string, on: boolean) =>
    setPicked((p) => {
      const cur = p[q.id] ?? [];
      return { ...p, [q.id]: q.type === "single" ? [label] : on ? [...cur, label] : cur.filter((l) => l !== label) };
    });

  return (
    <Panel as="section" elevation="floating" className="debate-question" aria-label="The court asks you">
      <Frame gap="3">
        <Text as="span" size="xxs" className="debate-kicker" content="The court asks you" />
        {questions.map((q, i) => (
          <Frame key={q.id} gap="2" role="group" aria-labelledby={`${base}-${i}`}>
            <Text id={`${base}-${i}`} size="s" hierarchy="primary" content={q.prompt} />
            {q.options.map((o, j) => {
              const id = `${base}-${i}-${j}`;
              return (
                <Frame key={o.label} direction="row" gap="2" align="start" className="debate-option">
                  <Input
                    id={id}
                    type={q.type === "multi" ? "checkbox" : "radio"}
                    name={`${base}-${i}`}
                    checked={(picked[q.id] ?? []).includes(o.label)}
                    onChange={(e) => toggle(q, o.label, e.target.checked)}
                  />
                  <Frame gap="0">
                    <Text as="label" htmlFor={id} size="s" content={o.label} />
                    {o.description && <Text size="xs" hierarchy="tertiary" content={o.description} />}
                  </Frame>
                </Frame>
              );
            })}
            {q.allow_other && (
              <Panel className="debate-other">
                <Input
                  aria-label={`Your own answer: ${q.prompt}`}
                  placeholder="Or in your own words…"
                  value={other[q.id] ?? ""}
                  onChange={(e) => setOther((o) => ({ ...o, [q.id]: e.target.value }))}
                />
              </Panel>
            )}
          </Frame>
        ))}
        {error && <Text role="alert" size="s" className="debate-error" content={error} />}
        <Frame direction="row" gap="2" justify="end">
          <Button label="Leave it to counsel" disabled={busy} onClick={() => void send(true)} />
          <Button hierarchy="primary" label={busy ? "Sending…" : "Answer"} disabled={busy} onClick={() => void send(false)} />
        </Frame>
      </Frame>
    </Panel>
  );
}
