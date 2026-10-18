"use client";

import { useState, type ComponentProps, type CSSProperties } from "react";
import { Button } from "../Button/Button";
import "./HoldButton.css";

/* A Button for a destructive action that must be held, not clicked. Press and
 * hold it (pointer, or Space/Enter) for `duration` ms: a danger-red bar fills
 * it left to right, and onHold fires when it is full. Let go early and nothing
 * happens. The fill is a CSS animation and its end is what fires onHold, so
 * the bar and the action can't drift apart. Styles in HoldButton.css. */

type HoldButtonProps = Omit<ComponentProps<typeof Button>, "onClick"> & {
  onHold: () => void;
  duration?: number;
};

export function HoldButton({ onHold, duration = 2000, style, ...rest }: HoldButtonProps) {
  const [holding, setHolding] = useState(false);
  const stop = () => setHolding(false);
  return (
    <Button
      {...rest}
      data-hold={holding ? "holding" : "idle"}
      style={{ ...style, "--hold-duration": `${duration}ms` } as CSSProperties}
      onPointerDown={(e) => e.button === 0 && setHolding(true)}
      onPointerUp={stop}
      onPointerLeave={stop}
      onPointerCancel={stop}
      onKeyDown={(e) => (e.key === " " || e.key === "Enter") && !e.repeat && setHolding(true)}
      onKeyUp={stop}
      onBlur={stop}
      onAnimationEnd={() => {
        stop();
        onHold();
      }}
    />
  );
}
