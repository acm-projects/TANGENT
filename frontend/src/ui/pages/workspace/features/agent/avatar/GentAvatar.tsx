import type { GentAvatarState } from "./avatarState";

/* Gent himself: a drop of ink in a detective's hat. A still drawing for now, with `state` on it (data-state) for
 * the animated version to act out; when the animation library comes in, it replaces this SVG and reads the same
 * `state` (avatarState.ts lists them). */

type GentAvatarProps = { state: GentAvatarState; size?: number; className?: string };

export function GentAvatar({ state, size = 28, className }: GentAvatarProps) {
  return (
    <svg
      viewBox="0 0 32 32"
      width={size}
      height={size}
      className={["gent-avatar", className].filter(Boolean).join(" ")}
      data-state={state}
      aria-hidden
    >
      {/* the drop */}
      <path d="M16 9.5c5.6 0 9.5 4 9.5 9.2 0 5.3-4.3 9.3-9.5 9.3s-9.5-4-9.5-9.3c0-5.2 3.9-9.2 9.5-9.2Z" fill="var(--avatar-ink, var(--gent-ink))" />
      {/* the hat: crown, band, brim */}
      <path d="M9.6 12.6 11 5.9c.3-1.3 1.3-1.9 2.4-1.5l2.6.9 2.6-.9c1.1-.4 2.1.2 2.4 1.5l1.4 6.7Z" fill="var(--avatar-ink, var(--gent-ink))" />
      <path d="M10.3 10.2h11.4l.4 1.9H9.9Z" fill="var(--avatar-paper, var(--on-gent-ink))" opacity=".9" />
      <ellipse cx="16" cy="12.9" rx="11.6" ry="2.1" fill="var(--avatar-ink, var(--gent-ink))" />
      {/* eyes under the brim */}
      <circle cx="12.9" cy="18.6" r="1.35" fill="var(--avatar-paper, var(--on-gent-ink))" />
      <circle cx="19.1" cy="18.6" r="1.35" fill="var(--avatar-paper, var(--on-gent-ink))" />
    </svg>
  );
}
