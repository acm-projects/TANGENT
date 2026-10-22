"use client";

import { motion } from "motion/react";
import { Frame, Link, Panel, Text } from "@/ui/library";
import { spring } from "@/ui/library/tokens/motion";

/* The file's contents, on a ruled index card: each section with a dotted
 * leader out to its number. A paperclip marks the section being read and
 * springs to the next one as the page scrolls (Account.tsx tracks which). */

type ContentsProps = {
  sections: readonly { id: string; label: string }[];
  active: string;
  onPick(id: string): void;
};

export function Contents({ sections, active, onPick }: ContentsProps) {
  return (
    <Panel as="aside" elevation="floating" className="contents" aria-labelledby="contents-heading">
      <Text as="h2" id="contents-heading" size="s" className="contents-heading" content="Contents" />
      <Frame as="ol" gap="0">
        {sections.map((section, i) => (
          <Frame as="li" key={section.id} gap="0" className="contents-item">
            {section.id === active && (
              <motion.span layoutId="contents-clip" className="contents-clip" aria-hidden="true" transition={spring.pin} />
            )}
            <Link
              href={`#${section.id}`}
              className="contents-link"
              aria-current={section.id === active ? "location" : undefined}
              onClick={() => onPick(section.id)}
            >
              <Text as="span" size="s" className="contents-label" content={section.label} />
              <Text as="span" size="s" className="contents-leader" content="" aria-hidden="true" />
              <Text as="span" size="s" className="contents-number" content={`§${i + 1}`} />
            </Link>
          </Frame>
        ))}
      </Frame>
    </Panel>
  );
}
