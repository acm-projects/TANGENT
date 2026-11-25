"use client";

import { useState } from "react";
import { Button, Panel } from "@/ui/library";
import { readLighting, setLighting, type Lighting } from "@/ui/library/tokens/lighting";
import "./Settings.css";

/* The lighting switch: three leather switches on a leather plate, the lit one pressed in.
 * The new lighting spreads out from the switch that was pressed (lighting.ts). */

const LIGHTING: { value: Lighting; icon: string; label: string }[] = [
  { value: "system", icon: "brightness_auto", label: "System" },
  { value: "light", icon: "light_mode", label: "Day" },
  { value: "dark", icon: "dark_mode", label: "Night" },
];

export function LightingPicker({ labelledBy }: { labelledBy: string }) {
  const [lighting, setPicked] = useState(readLighting);
  return (
    <Panel material="leather" stitch="none" role="group" aria-labelledby={labelledBy} className="settings-lighting">
      {LIGHTING.map((option) => (
        <Button
          key={option.value}
          material="leather"
          size="xs"
          icon={option.icon}
          label={option.label}
          showIcon
          pressed={lighting === option.value}
          onClick={(e) => {
            setPicked(option.value);
            setLighting(option.value, { x: e.clientX, y: e.clientY });
          }}
          className="settings-lighting-option"
        />
      ))}
    </Panel>
  );
}
