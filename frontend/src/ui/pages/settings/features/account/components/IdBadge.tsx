"use client";

import { motion } from "motion/react";
import type { Account } from "@/api/types";
import { Frame, Image, Panel, Text } from "@/ui/library";
import { spring } from "@/ui/library/tokens/motion";

/* The investigator's ID: a badge hung from a clip, with their photo (from
 * Google) or their initial, name and email. It swings on its clip when the
 * pointer brushes it, and settles back crooked. A new name reissues it: the
 * badge turns over and comes back round with the name on it. */

export function IdBadge({ account }: { account: Account }) {
  return (
    <motion.div
      className="id-badge-hang"
      initial={{ rotate: -14, y: -40, opacity: 0 }}
      animate={{ rotate: -2, y: 0, opacity: 1, transition: spring.pin }}
      whileHover={{ rotate: [-2, 4, -3, 1.5, -2], transition: { duration: 1.1, ease: "easeOut" } }}
    >
      <motion.div
        key={account.name}
        initial={{ rotateY: -180 }}
        animate={{ rotateY: 0, transition: spring.fly }}
        style={{ transformPerspective: 900 }}
      >
        <Panel elevation="floating" className="id-badge">
          <Frame gap="3" align="center">
            <Text as="span" size="xxs" className="id-badge-kicker" content="Tangent · Investigator" />
            {account.avatar_url ? (
              <Image src={account.avatar_url} alt="" referrerPolicy="no-referrer" className="id-badge-photo" />
            ) : (
              <Text as="span" size="display" className="id-badge-photo id-badge-initial" content={account.name.charAt(0).toUpperCase()} aria-hidden="true" />
            )}
            <Frame gap="0" align="center" className="id-badge-caption">
              <Text as="span" size="l" hierarchy="primary" className="id-badge-name" content={account.name} />
              <Text as="span" size="xs" hierarchy="tertiary" className="id-badge-email" content={account.email} />
            </Frame>
            <Text as="span" size="xxs" className="id-badge-stamp" content={`Cleared via ${account.auth_provider === "google" ? "Google" : account.auth_provider}`} />
          </Frame>
        </Panel>
      </motion.div>
    </motion.div>
  );
}
