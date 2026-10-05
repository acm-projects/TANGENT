import type { ComponentProps } from "react";
import "./Button.css";

/* No "use client": Button holds no state (DESIGN.md Rule 9). It renders on the
 * server, and when a client component imports it, it joins that client bundle
 * automatically — so onClick works without making the whole library client-side. */

type ButtonProps = ComponentProps<"button"> & {
  variant?: "primary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
};

export function Button({
  variant = "primary",
  size = "md",
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      data-ui="button"
      data-variant={variant}
      data-size={size}
      {...rest}
    />
  );
}
