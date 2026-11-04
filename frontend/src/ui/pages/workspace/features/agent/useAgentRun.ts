import { useEffect, useState } from "react";
import { api, apiErrorMessage } from "@/api";
import type { AvailableModel } from "@/api/types";
import { useAgentRunStore } from "@/store/agentRunStore";
import { useTreeStore } from "@/store/treeStore";
import { answerRun, cancelRun, dismissRun, resumeRun, startRun } from "./agentRunActions";

/** The agent run window's behaviour, with no UI in it (DESIGN.md Rule 5): the run itself comes from the store,
 * which its event stream keeps up to date; this adds the model choice and the buttons' busy and error state. */
export function useAgentRun() {
  const view = useAgentRunStore((s) => s.view);
  const projectId = useTreeStore((s) => s.project?.id) ?? null;
  const [models, setModels] = useState<AvailableModel[]>([]);
  const [model, setModel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.chats
      .models()
      .then((available) => {
        if (cancelled) return;
        setModels(available);
        setModel(available[0]?.id ?? "");
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(apiErrorMessage(e, "Could not load models."));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // pick up the run last started in this project (it goes on without the window)
  useEffect(() => {
    if (projectId) void resumeRun(projectId).catch((e: unknown) => setError(apiErrorMessage(e, "Could not load the agent run.")));
  }, [projectId]);

  async function act(fallback: string, fn: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e: unknown) {
      setError(apiErrorMessage(e, fallback));
    } finally {
      setBusy(false);
    }
  }

  return {
    view,
    models,
    model,
    setModel,
    busy,
    error,
    start: (goal: string) =>
      act("Could not start the agent.", async () => {
        if (projectId && goal.trim() && model) await startRun(projectId, goal.trim(), model, useTreeStore.getState().activeNodeId);
      }),
    cancel: () => act("Could not cancel the run.", async () => void (projectId && view && (await cancelRun(projectId, view.id)))),
    /** Throws on failure: the question card shows the message. */
    answer: async (answers: Record<string, string | string[]>) => {
      if (projectId && view) await answerRun(projectId, view.id, answers);
    },
    dismiss: () => projectId && dismissRun(projectId),
  };
}
