"use client";

import { useId, useState } from "react";
import { apiErrorMessage } from "@/api";
import type { AgentQuestion } from "@/api/types";
import { Button, Frame, Input, Panel, Text } from "@/ui/library";

/* The agent turns to the user: every open question on one card, answered once. `single` is a radio choice,
 * `multi` checkboxes, `text` a free-text line, and `allow_other` adds the user's own words. Answers go back as
 * the option's label text, never its position. The server needs every question answered. `confirm` is the
 * runtime asking before the agent may delete something. */

type RunQuestionsProps = {
  questions: AgentQuestion[];
  confirm: boolean;
  onAnswer(answers: Record<string, string | string[]>): Promise<void>;
};

export function RunQuestions({ questions, confirm, onAnswer }: RunQuestionsProps) {
  const [picked, setPicked] = useState<Record<string, string[]>>({});
  const [typed, setTyped] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const base = useId();

  const answerFor = (q: AgentQuestion): string | string[] | null => {
    const own = typed[q.id]?.trim();
    const chosen = picked[q.id] ?? [];
    if (q.type === "text") return own || null;
    if (q.type === "multi") return own || chosen.length ? [...chosen, ...(own ? [own] : [])] : null;
    return own || chosen[0] || null;
  };
  const answers = Object.fromEntries(questions.map((q) => [q.id, answerFor(q)]));
  const complete = Object.values(answers).every((a) => a !== null);

  async function send() {
    if (busy || !complete) return;
    setBusy(true);
    setError(null);
    try {
      await onAnswer(answers as Record<string, string | string[]>);
    } catch (e) {
      setError(apiErrorMessage(e, "Could not send your answer."));
      setBusy(false);
    }
  }

  const toggle = (q: AgentQuestion, label: string, on: boolean) =>
    setPicked((p) => {
      const cur = p[q.id] ?? [];
      return { ...p, [q.id]: q.type === "single" ? [label] : on ? [...cur, label] : cur.filter((l) => l !== label) };
    });

  const title = confirm ? "Confirm before the agent deletes" : "The agent asks you";
  return (
    <Panel as="section" elevation="floating" className="agent-question" aria-label={title}>
      <Frame gap="3">
        <Text as="span" size="xxs" className="agent-kicker" content={title} />
        {questions.map((q, i) => (
          <Frame key={q.id} gap="2" role="group" aria-labelledby={`${base}-${i}`}>
            <Text id={`${base}-${i}`} size="s" hierarchy="primary" content={q.prompt} />
            {q.options.map((o, j) => {
              const id = `${base}-${i}-${j}`;
              return (
                <Frame key={o.label} direction="row" gap="2" align="start" className="agent-option">
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
            {(q.allow_other || q.type === "text") && (
              <Panel className="agent-other">
                <Input
                  aria-label={q.type === "text" ? q.prompt : `Your own answer: ${q.prompt}`}
                  placeholder={q.type === "text" ? "Your answer…" : "Or in your own words…"}
                  value={typed[q.id] ?? ""}
                  onChange={(e) => setTyped((t) => ({ ...t, [q.id]: e.target.value }))}
                />
              </Panel>
            )}
          </Frame>
        ))}
        {error && <Text role="alert" size="s" className="agent-error" content={error} />}
        <Frame direction="row" justify="end">
          <Button hierarchy="primary" label={busy ? "Sending…" : "Answer"} disabled={busy || !complete} onClick={() => void send()} />
        </Frame>
      </Frame>
    </Panel>
  );
}
