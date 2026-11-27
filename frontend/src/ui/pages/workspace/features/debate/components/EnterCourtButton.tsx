"use client";

import { useState } from "react";
import { apiErrorMessage } from "@/api";
import { selectInCourt, useDebateStore } from "@/store/debateStore";
import { Button, Frame, Text } from "@/ui/library";
import { openDebateNode } from "../debateActions";

/** Back into a debate's courtroom from its card: the transcript and the judgment, as the court left them. */
export function EnterCourtButton({ nodeId, className }: { nodeId: string; className?: string }) {
  const [entering, setEntering] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // a debate still in session is already followed: walk straight back in
  const inCourt = useDebateStore(selectInCourt(nodeId));
  return (
    <Frame direction="row" gap="2" align="center" className={className}>
      <Button
        size="s"
        icon="balance"
        showIcon
        label={entering ? "Entering…" : inCourt ? "Return to court" : "Enter the courtroom"}
        disabled={entering}
        onClick={() => {
          if (inCourt) return useDebateStore.getState().setMinimised(false);
          setEntering(true);
          setError(null);
          openDebateNode(nodeId)
            .catch((e: unknown) => setError(apiErrorMessage(e, "Could not open the courtroom.")))
            .finally(() => setEntering(false));
        }}
      />
      {error && <Text role="alert" size="s" className="debate-error" content={error} />}
    </Frame>
  );
}
