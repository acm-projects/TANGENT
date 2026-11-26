"use client";

import { useState } from "react";
import { Button, Frame, Picker, Popup, Text } from "@/ui/library";

/* The gallery's stateful specimens (Popup, Picker): the page itself stays a server component, so the open state lives here. */

export function PopupSpecimen() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button label="Open popup" onClick={() => setOpen(true)} />
      <Popup open={open} onClose={() => setOpen(false)} title="Rename case">
        <Text content="Drought records will keep their nodes under the new name." />
        <Frame direction="row" gap="2" justify="end">
          <Button label="Cancel" hierarchy="tertiary" onClick={() => setOpen(false)} />
          <Button label="Rename" data-primary onClick={() => setOpen(false)} />
        </Frame>
      </Popup>
    </>
  );
}

const MODELS = [
  { value: "fast", label: "Fast", icon: "bolt", description: "Quick answers for routine questions" },
  { value: "balanced", label: "Balanced", icon: "tune", description: "Good judgement at a steady pace" },
  { value: "deep", label: "Deep", icon: "psychology", description: "Slow, careful reading of the sources" },
];

export function PickerSpecimen() {
  const [value, setValue] = useState("balanced");
  return <Picker aria-label="Model" options={MODELS} value={value} onChange={setValue} />;
}
