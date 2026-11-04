"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import type { AgentOutcome, AgentRunStatus, AgentTask, AgentTaskStatus } from "@/api/types";
import { isRunOver, type AgentActivity, type AgentRunView } from "@/store/agentRunStore";
import { Button, Frame, Icon, Loading, Select, Text, TextArea } from "@/ui/library";
import { RunQuestions } from "./RunQuestions";
import { useAgentRun } from "./useAgentRun";
import "./AgentWindow.css";

/* The agent window: give the agent a research goal and watch it work. It plans, runs tasks against the project's
 * tree and sources, may stop to ask a question, and ends with an assessment of the goal. Everything shown is the
 * run's real state, rebuilt from its event log (store/agentRunStore.ts), not the model's narration.
 * Styles: AgentWindow.css. */

const STATUS: Record<AgentRunStatus, string> = {
  queued: "Starting…",
  running: "Working…",
  waiting_input: "Waiting for your answer",
  completed: "Finished",
  failed: "Failed",
  cancelled: "Cancelled",
};

const OUTCOME: Record<AgentOutcome, string> = {
  satisfied: "Goal satisfied",
  partially_satisfied: "Partly satisfied",
  inconclusive: "Inconclusive",
  blocked: "Blocked",
};

const TASK_ICON: Record<AgentTaskStatus, string> = {
  pending: "radio_button_unchecked",
  in_progress: "play_circle",
  completed: "check_circle",
  skipped: "do_not_disturb_on",
  failed: "error",
  blocked: "lock",
  unfinished: "pause_circle",
};

const SHOWN_ACTIVITY = 6;
const NOTE_CHARS = 280;
const clip = (s: string) => (s.length <= NOTE_CHARS ? s : `${s.slice(0, NOTE_CHARS)}…`);

type AgentWindowProps = { onClose(): void };

export function AgentWindow({ onClose }: AgentWindowProps) {
  const agent = useAgentRun();
  const [goal, setGoal] = useState("");
  const bodyRef = useRef<HTMLDivElement>(null);
  const view = agent.view;
  const live = view !== null && !isRunOver(view.status);

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight });
  }, [view?.tasks.length, view?.activity.length, view?.status, view?.questions]);

  function submit() {
    if (!goal.trim() || agent.busy || !agent.model) return;
    void agent.start(goal);
    setGoal("");
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  }

  // portalled: a fixed window must not sit inside the chat panel's transforms and filters
  return createPortal(
    <section className="agent-window" aria-label="Agent">
      <Frame as="header" direction="row" justify="between" align="center" className="agent-header">
        <Text as="h2" size="m" content="Agent" />
        <Button hierarchy="tertiary" label="Close agent" icon="close" showIcon showLabel={false} onClick={onClose} />
      </Frame>

      <div ref={bodyRef} className="agent-body" aria-live="polite" aria-label="Agent run">
        {view ? <RunView view={view} onAnswer={agent.answer} /> : <Text size="s" className="agent-hint" content="Give the agent a research goal, such as “Find out whether X holds, using the project's sources.” It plans the work, researches, writes findings into the tree, and asks you when it needs a decision." />}
      </div>

      {agent.error && <Text role="alert" size="s" className="agent-error" content={agent.error} />}

      <Frame as="footer" gap="2" className="agent-field">
        {view ? (
          <Frame direction="row" justify="end">
            {live ? (
              <Button label={agent.busy ? "Cancelling…" : "Cancel run"} icon="stop_circle" showIcon disabled={agent.busy} onClick={() => void agent.cancel()} />
            ) : (
              <Button hierarchy="primary" label="New run" icon="add" showIcon onClick={agent.dismiss} />
            )}
          </Frame>
        ) : (
          <>
            <TextArea
              aria-label="Research goal"
              placeholder="What should the agent find out?"
              value={goal}
              disabled={agent.busy}
              onChange={(e) => setGoal(e.target.value)}
              onKeyDown={onKeyDown}
            />
            <Frame direction="row" justify="between" align="center">
              <Select
                aria-label="Agent model"
                className="agent-model"
                value={agent.model}
                onChange={(e) => agent.setModel(e.target.value)}
                disabled={agent.busy || agent.models.length === 0}
                options={agent.models.length === 0 ? [{ value: "", label: "Loading models…" }] : agent.models.map((m) => ({ value: m.id, label: m.name }))}
              />
              <Button
                hierarchy="primary"
                label="Start research"
                icon="arrow_upward"
                showIcon
                showLabel={false}
                disabled={agent.busy || !goal.trim() || !agent.model}
                onClick={submit}
                className="agent-send"
              />
            </Frame>
          </>
        )}
      </Frame>
    </section>,
    document.body,
  );
}

type RunViewProps = { view: AgentRunView; onAnswer(answers: Record<string, string | string[]>): Promise<void> };

function RunView({ view, onAnswer }: RunViewProps) {
  const working = view.status === "queued" || view.status === "running";
  return (
    <Frame gap="3">
      <Frame gap="1">
        <Text as="span" size="xxs" className="agent-kicker" content="Goal" />
        <Text size="s" hierarchy="primary" content={view.goal} />
      </Frame>

      <Frame direction="row" gap="2" align="center" className="agent-status" data-status={view.status}>
        {working && <Loading />}
        <Text as="span" size="s" content={STATUS[view.status]} />
      </Frame>

      {view.plan && (
        <Frame gap="1">
          <Text as="span" size="xxs" className="agent-kicker" content={`Plan v${view.plan.version}`} />
          <Text size="s" content={view.plan.strategy} />
          {view.plan.reason && <Text size="xs" hierarchy="tertiary" content={`Revised because: ${view.plan.reason}`} />}
          {view.plan.assumptions.length > 0 && (
            <Frame gap="0">
              <Text size="xs" hierarchy="tertiary" content="Assumes" />
              {view.plan.assumptions.map((a, i) => (
                <Text key={i} size="xs" content={`• ${a}`} />
              ))}
            </Frame>
          )}
        </Frame>
      )}

      {view.limit && <Text role="status" size="s" className="agent-limit" content={`Stopped at ${view.limit}. Unfinished tasks keep the work done so far; the summary below covers only what was completed.`} />}

      {view.tasks.length > 0 && (
        <Frame as="ol" gap="2" aria-label="Tasks">
          {view.tasks.map((t) => (
            <TaskRow key={t.key} task={t} />
          ))}
        </Frame>
      )}

      {view.activity.length > 0 && (
        <Frame gap="1">
          <Text as="span" size="xxs" className="agent-kicker" content="Recent activity" />
          <Frame as="ol" gap="0" aria-label="Recent activity">
            {view.activity.slice(-SHOWN_ACTIVITY).map((a, i) => (
              <ActivityRow key={i} item={a} />
            ))}
          </Frame>
        </Frame>
      )}

      {view.questions && <RunQuestions key={view.questions.map((q) => q.id).join()} questions={view.questions} confirm={view.asking === "confirm_delete"} onAnswer={onAnswer} />}

      {view.error && <Text role="alert" size="s" className="agent-error" content={view.error} />}

      {view.final && (
        <Frame gap="2" className="agent-final">
          <Text as="span" size="xxs" className="agent-kicker" content={OUTCOME[view.final.outcome]} />
          <Text size="s" hierarchy="primary" className="agent-summary" content={view.final.summary} />
          <Bullets title="Limitations" items={view.final.limitations} />
          <Bullets title="Still unresolved" items={view.final.unresolved_questions} />
          {view.final.evidence.length > 0 && <Text size="xs" hierarchy="tertiary" content={`Evidence: ${view.final.evidence.join(", ")}`} />}
        </Frame>
      )}
    </Frame>
  );
}

function TaskRow({ task }: { task: AgentTask }) {
  const note = task.status === "completed" ? task.assessment?.findings : task.reason;
  const after = task.depends_on.length > 0 ? ` (after ${task.depends_on.join(", ")})` : "";
  return (
    <Frame as="li" direction="row" gap="2" align="start" className="agent-task" data-status={task.status}>
      <Icon icon={TASK_ICON[task.status]} size="m" />
      <Frame gap="0">
        <Text size="s" hierarchy={task.status === "pending" ? "secondary" : "primary"} content={`${task.key}: ${task.objective}${after}`} />
        {note && <Text size="xs" hierarchy="tertiary" content={clip(note)} />}
      </Frame>
    </Frame>
  );
}

function ActivityRow({ item }: { item: AgentActivity }) {
  return (
    <Frame as="li" direction="row" gap="1" align="center" className="agent-activity" data-failed={item.ok ? undefined : ""}>
      <Icon icon={item.ok ? "check" : "close"} size="xs" />
      <Text size="xs" content={`${item.tool}${item.about ? `: ${item.about}` : ""}${item.error ? ` (${item.error})` : ""}`} />
    </Frame>
  );
}

function Bullets({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <Frame gap="0">
      <Text size="xs" hierarchy="tertiary" content={title} />
      {items.map((x, i) => (
        <Text key={i} size="xs" content={`• ${x}`} />
      ))}
    </Frame>
  );
}
