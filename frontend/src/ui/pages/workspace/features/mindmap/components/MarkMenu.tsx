import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, type MouseEvent } from "react";
import { createPortal } from "react-dom";
import { Button, Frame } from "@/ui/library";
import { spring } from "@/ui/library/tokens/motion";

export type MarkOption = { icon: string; label: string; onClick: (e?: MouseEvent) => void };

/* The "Mark as" menu a drag to the right drops where the pointer let go: one button per way the branch can end,
 * springing out of the cursor one after another. A pick, Escape or a press anywhere else closes it. Portalled to
 * <body> in screen coordinates, like the drag's string (DragAction.tsx). Styles in ../MindMap.css. */
export function MarkMenu({ at, options, onClose }: {
  at: { x: number; y: number } | null;
  options: MarkOption[];
  onClose(): void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!at) return;
    // Escape closes; the arrows, Home and End move between the items, as in any menu
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") return onClose();
      const items = [...(ref.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])];
      const at = items.indexOf(document.activeElement as HTMLElement);
      const to = { ArrowDown: at + 1, ArrowUp: at - 1, Home: 0, End: items.length - 1 }[e.key];
      if (to === undefined || !items.length) return;
      e.preventDefault();
      items[(to + items.length) % items.length]?.focus();
    };
    const onDown = (e: PointerEvent) => !ref.current?.contains(e.target as Node) && onClose();
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onDown, true);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onDown, true);
    };
  }, [at, onClose]);

  return createPortal(
    <AnimatePresence>
      {at && (
        <Frame
          ref={ref}
          gap="2"
          className="mark-menu"
          role="menu"
          aria-label="Mark as"
          style={{ left: at.x, top: at.y }}
        >
          {options.map((option, i) => (
            <motion.div
              key={option.icon}
              initial={{ opacity: 0, x: -12, y: -8 * (i + 1), scale: 0.7 }}
              animate={{ opacity: 1, x: 0, y: 0, scale: 1, transition: { ...spring.pin, delay: i * 0.05 } }}
              exit={{ opacity: 0, scale: 0.7, transition: { ...spring.lift, delay: (options.length - 1 - i) * 0.03 } }}
            >
              <Button
                size="l"
                role="menuitem"
                elevation="floating"
                showIcon
                icon={option.icon}
                label={option.label}
                autoFocus={i === 0}
                onClick={(e) => {
                  e.stopPropagation();
                  onClose();
                  option.onClick(e);
                }}
              />
            </motion.div>
          ))}
        </Frame>
      )}
    </AnimatePresence>,
    document.body,
  );
}
