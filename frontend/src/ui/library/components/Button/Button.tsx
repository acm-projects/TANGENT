import type { ComponentProps } from "react";
import type { Elevation, Hierarchy, TextSize } from "../../types/Types";
import { Panel } from "../../primitives/Panel/Panel";
import { Text } from "../../primitives/Text/Text";
import { Icon } from "../../primitives/Icon/Icon";
import "./Button.css";

/* Button = Panel (the surface, rendered as the native <button>) + Icon + Text.
 * Hierarchy and size are handed down so all three agree on one look;
 * elevation goes to the Panel, which is the only part with a surface.
 *
 * No "use client": Button holds no state (DESIGN.md Rule 9). It renders on the
 * server, and when a client component imports it, it joins that client bundle
 * automatically — so onClick works without making the whole library client-side. */

type ButtonProps = Omit<ComponentProps<"button">, "children"> & {
  hierarchy?: Hierarchy;
  elevation?: Elevation;
  size?: TextSize;
  label: string;
  icon?: string;
  showIcon?: boolean;
  showLabel?: boolean;
  iconAlign?: "left" | "right";
  /** Toggle buttons only: true while the thing it opens is open. Renders
   * aria-pressed, which is also what Button.css styles (Figma: tile "Open"). */
  pressed?: boolean;
};

export function Button({
  hierarchy = "secondary",
  elevation = "flat",
  size = "base",
  label,
  icon,
  showIcon = false,
  showLabel = true,
  iconAlign = "left",
  pressed,
  type = "button",
  ...rest
}: ButtonProps) {
  const iconOnly = showIcon && !showLabel;
  return (
    <Panel
      as="button"
      type={type}
      hierarchy={hierarchy}
      elevation={elevation}
      /* An icon-only button still needs an accessible name. */
      aria-label={showLabel ? undefined : label}
      aria-pressed={pressed}
      {...rest}
      data-component="button"
      data-size={size}
      data-icon-only={iconOnly || undefined}
    >
      {showIcon && icon && iconAlign === "left" && <Icon icon={icon} size={size} hierarchy={hierarchy} />}
      {showLabel && <Text as="span" content={label} size={size} hierarchy={hierarchy} />}
      {showIcon && icon && iconAlign === "right" && <Icon icon={icon} size={size} hierarchy={hierarchy} />}
    </Panel>
  );
}
