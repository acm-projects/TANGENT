"use client";

import { useEffect, type PointerEvent } from "react";
import { animate, motion, useMotionValue, useReducedMotion } from "motion/react";
import type { Account } from "@/api/types";
import { Frame, Image, Panel, Text } from "@/ui/library";
import { spring } from "@/ui/library/tokens/motion";

/* The investigator's ID: a leather badge hung from a clip, with their photo (from
 * Google) or their initial, name and email. When the pointer brushes it, it
 * swings away from the brush, as hard as the pointer was moving, and settles
 * back crooked on spring.swing (it carries the knock, so it may bounce). A new
 * name reissues it: the badge turns over and comes back round with the name on it. */

const REST = -2;
/** deg/s of swing per px of pointer movement, and the most a knock can give */
const KNOCK = 6;
const MAX_KNOCK = 110;
const MIN_KNOCK = 45;

export function IdBadge({ account }: { account: Account }) {
  const rotate = useMotionValue(-14);
  const still = useReducedMotion();

  useEffect(() => {
    // with reduced motion it just hangs there, no swing in
    if (still) return void rotate.set(REST);
    const hang = animate(rotate, REST, spring.pin);
    return () => hang.stop();
  }, [rotate, still]);

  function knock(e: PointerEvent<HTMLDivElement>) {
    if (still) return;
    const box = e.currentTarget.getBoundingClientRect();
    // from the left it swings right (clockwise), from the right it swings left
    const away = e.clientX < box.left + box.width / 2 ? 1 : -1;
    const speed = Math.min(MAX_KNOCK, Math.max(MIN_KNOCK, Math.abs(e.movementX) * KNOCK));
    // From the live angle, so a second brush mid-swing adds to it instead of jumping. Motion skips a
    // spring whose start is already its target, so a badge at rest is first nudged the way it's knocked.
    const velocity = rotate.getVelocity() + away * speed;
    if (rotate.get() === REST) rotate.jump(REST + away * 0.25);
    animate(rotate, REST, { ...spring.swing, velocity });
  }

  return (
    <motion.div
      className="id-badge-hang"
      style={{ rotate }}
      initial={{ y: -40, opacity: 0 }}
      animate={{ y: 0, opacity: 1, transition: spring.pin }}
      onPointerEnter={knock}
    >
      <motion.div
        key={account.name}
        initial={{ rotateY: -180 }}
        animate={{ rotateY: 0, transition: spring.fly }}
        style={{ transformPerspective: 900 }}
      >
        <Panel material="leather" elevation="floating" className="id-badge">
          <Frame gap="3" align="center">
            <Text as="span" size="xxs" face="stamp" className="id-badge-kicker" content="Tangent · Investigator" />
            {account.avatar_url ? (
              <Image src={account.avatar_url} alt="" referrerPolicy="no-referrer" className="id-badge-photo" />
            ) : (
              <Text as="span" size="display" face="heading" className="id-badge-photo id-badge-initial" content={account.name.charAt(0).toUpperCase()} aria-hidden="true" />
            )}
            <Frame gap="0" align="center" className="id-badge-caption">
              <Text as="span" size="l" face="heading" hierarchy="primary" className="id-badge-name" content={account.name} />
              <Text as="span" size="xs" hierarchy="tertiary" className="id-badge-email" content={account.email} />
            </Frame>
            <Text as="span" size="xxs" face="stamp" className="id-badge-stamp" content={`Cleared via ${account.auth_provider === "google" ? "Google" : account.auth_provider}`} />
          </Frame>
        </Panel>
      </motion.div>
    </motion.div>
  );
}
