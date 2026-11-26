"use client";

import { useEffect } from "react";
import { Button, Frame, Panel, Text } from "@/ui/library";
import { readShowNudges, useGentStore, writeShowNudges } from "@/store/gentStore";
import "./Settings.css";

/* Settings > Show Gent's nudges: whether Gent's work log shows the moments the server steered him (a reminder to
 * update his Field Notes, how deep the research has gone, a finish sent back). Kept in this browser. */
export function ShowNudges() {
  const on = useGentStore((s) => s.showNudges);
  useEffect(() => useGentStore.setState({ showNudges: readShowNudges() }), []);
  return (
    <Frame direction="row" justify="between" align="center" gap="4" className="account-row">
      <Frame gap="0">
        <Text id="show-gent-nudges" size="s" hierarchy="primary" content="Show Gent's nudges" />
        <Text size="xs" hierarchy="tertiary" content="In Gent's work log, show when he was reminded to keep his notes, told how deep he'd gone, or sent back to finish properly." />
      </Frame>
      {/* the same leather switch plate as Lighting, Off and On, so the page has one kind of switch */}
      <Panel material="leather" stitch="none" role="group" aria-labelledby="show-gent-nudges" className="settings-lighting settings-switch">
        {[false, true].map((value) => (
          <Button
            key={String(value)}
            material="leather"
            size="xs"
            label={value ? "On" : "Off"}
            pressed={on === value}
            onClick={() => writeShowNudges(value)}
            className="settings-lighting-option"
          />
        ))}
      </Panel>
    </Frame>
  );
}
