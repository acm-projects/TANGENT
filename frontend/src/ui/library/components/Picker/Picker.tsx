"use client";

import { AnimatePresence, MotionConfig, motion, type Variants } from "motion/react";
import { useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { Icon } from "../../primitives/Icon/Icon";
import { Text } from "../../primitives/Text/Text";
import { spring } from "../../tokens/motion";
import "./Picker.css";

/* A select with our own list: a quiet trigger (the chosen option's icon and label) that opens a sheet of options,
 * each with an icon and a line of description, springing out of the trigger one after another. Use it where the
 * options deserve more than a word (models); a plain choice stays the native Select.
 *
 * The listbox pattern: the trigger opens it with a click, Enter, Space or the arrows; the arrows, Home and End move;
 * Enter or Space picks; Escape, Tab or a press outside closes, and focus goes back to the trigger. The list is
 * portalled to <body> at the trigger's place, below it or above when there's no room, so a clipping or transformed
 * parent (the dock, a card) can't cut it off; scrolling or resizing closes it. Styles in Picker.css. */

export type PickerOption = { value: string; label: string; icon?: string; description?: string };

type PickerProps = {
  options: PickerOption[];
  value: string;
  onChange(value: string): void;
  "aria-label": string;
  disabled?: boolean;
  /** shown on the trigger when no option matches `value` (loading, nothing available) */
  placeholder?: string;
  className?: string;
  /** a class for the list too (it's portalled to <body>, out of reach of the consumer's own styles) */
  listClassName?: string;
  /** which edge of the trigger the list lines up with: "end" for a trigger at the right of its bar */
  align?: "start" | "end";
};

// the sheet grows out of the trigger (from the side it opens on) and its options follow one after another; closing
// tucks them away in reverse, then the sheet, as the board's More menu does. `custom` is true when it opens upward.
const sheet: Variants = {
  closed: (up: boolean) => ({ opacity: 0, scale: 0.7, y: up ? 8 : -8, transition: { ...spring.lift, when: "afterChildren", staggerChildren: 0.03, staggerDirection: -1 } }),
  open: { opacity: 1, scale: 1, y: 0, transition: { ...spring.pin, delayChildren: 0.03, staggerChildren: 0.05 } },
};
const row: Variants = {
  closed: (up: boolean) => ({ opacity: 0, y: up ? 6 : -6, transition: spring.lift }),
  open: { opacity: 1, y: 0, transition: spring.pin },
};

type Place = { left: number; width: number; maxHeight: number; top?: number; bottom?: number };

export function Picker({ options, value, onChange, disabled, placeholder = "Choose…", className, listClassName, align = "start", ...rest }: PickerProps) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [place, setPlace] = useState<Place | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const id = useId();
  const chosen = options.find((o) => o.value === value);

  const close = (refocus = true) => {
    setOpen(false);
    if (refocus) trigger.current?.focus();
  };
  const show = (at = Math.max(0, options.findIndex((o) => o.value === value))) => {
    if (disabled || !options.length) return;
    setActive(at);
    setOpen(true);
  };
  const pick = (i: number) => {
    const o = options[i];
    if (o && o.value !== value) onChange(o.value);
    close();
  };

  // where the list goes: under the trigger, or over it when the space below is short
  useLayoutEffect(() => {
    if (!open || !trigger.current) return;
    const r = trigger.current.getBoundingClientRect();
    const need = Math.min(options.length * 64 + 16, 360);
    const below = window.innerHeight - r.bottom;
    const width = Math.max(r.width, 240);
    const left = Math.max(8, Math.min(r.left, window.innerWidth - width - 8));
    // the list never runs past the side it opens on (--picker-room, with Picker.css's caps)
    setPlace(below >= need || below >= r.top
      ? { left, width, maxHeight: below - 14, top: r.bottom + 6 }
      : { left, width, maxHeight: r.top - 14, bottom: window.innerHeight - r.top + 6 });
  }, [open, options.length]);

  // a list wider than the trigger (long descriptions) slides back in from the right edge, once it's measured
  useLayoutEffect(() => {
    const el = list.current;
    if (!el || !place) return;
    const r = trigger.current?.getBoundingClientRect();
    const want = align === "end" && r ? r.right - el.offsetWidth : place.left;
    const left = Math.max(8, Math.min(want, window.innerWidth - 8 - el.offsetWidth));
    if (Math.abs(left - place.left) > 0.5) setPlace({ ...place, left });
  }, [place, align]);

  useEffect(() => {
    if (!open) return;
    list.current?.querySelectorAll<HTMLElement>('[role="option"]')[active]?.focus();
  }, [open, active, place]);

  useEffect(() => {
    if (!open) return;
    const outside = (e: PointerEvent) => {
      const t = e.target as Node;
      if (!list.current?.contains(t) && !trigger.current?.contains(t)) close(false);
    };
    const away = () => close(false);
    // the page scrolling moves the trigger out from under the list; the list scrolling its own options doesn't
    const scrolled = (e: Event) => {
      if (!list.current?.contains(e.target as Node)) close(false);
    };
    window.addEventListener("pointerdown", outside, true);
    window.addEventListener("resize", away);
    window.addEventListener("scroll", scrolled, true);
    return () => {
      window.removeEventListener("pointerdown", outside, true);
      window.removeEventListener("resize", away);
      window.removeEventListener("scroll", scrolled, true);
    };
  }, [open]);

  const onTriggerKey = (e: KeyboardEvent) => {
    if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) {
      e.preventDefault();
      show();
    }
  };
  const onListKey = (e: KeyboardEvent) => {
    const last = options.length - 1;
    const to = { ArrowDown: Math.min(active + 1, last), ArrowUp: Math.max(active - 1, 0), Home: 0, End: last }[e.key];
    if (to !== undefined) {
      e.preventDefault();
      setActive(to);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      pick(active);
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation(); // the picker closes, not the dock or popup it sits in
      close();
    } else if (e.key === "Tab") {
      close(false);
    }
  };

  const up = place?.bottom !== undefined;
  return (
    <>
      <button
        // Firefox otherwise restores the disabled state on reload, before hydration, and the HTML no longer matches
        // (as Panel does for buttons; React's button types omit it, browsers don't)
        {...{ autoComplete: "off" }}
        ref={trigger}
        type="button"
        data-ui="picker"
        className={className}
        // the name carries the choice too: an aria-label hides the button's own text from screen readers
        aria-label={`${rest["aria-label"]}: ${chosen?.label ?? placeholder}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        title={chosen?.description}
        disabled={disabled}
        onClick={() => (open ? close() : show())}
        onKeyDown={onTriggerKey}
      >
        {chosen?.icon && <Icon icon={chosen.icon} size="s" className="picker-icon" />}
        <span className="picker-value">{chosen?.label ?? placeholder}</span>
        <Icon icon="expand_more" size="s" className="picker-chevron" data-open={open || undefined} />
      </button>
      {typeof document !== "undefined" &&
        createPortal(
          // portalled out of whatever MotionConfig the trigger sits in, so it honours reduced motion itself
          <MotionConfig reducedMotion="user">
            <AnimatePresence>
              {open && place && (
                <motion.ul
                  ref={list}
                  id={id}
                  role="listbox"
                  aria-label={rest["aria-label"]}
                  className={["picker-list", listClassName].filter(Boolean).join(" ")}
                  style={{ left: place.left, minWidth: place.width, "--picker-room": `${place.maxHeight}px`, top: place.top, bottom: place.bottom, transformOrigin: up ? "bottom left" : "top left" } as CSSProperties}
                  variants={sheet}
                  custom={up}
                  initial="closed"
                  animate="open"
                  exit="closed"
                  onKeyDown={onListKey}
                >
                  {options.map((o, i) => (
                    <motion.li
                      key={o.value}
                      role="option"
                      tabIndex={-1}
                      aria-selected={o.value === value}
                      // named by the label, the description read after it, not one run-on name
                      aria-labelledby={`${id}-${i}`}
                      aria-describedby={o.description ? `${id}-${i}-d` : undefined}
                      className="picker-option"
                      variants={row}
                      custom={up}
                      onPointerEnter={() => setActive(i)}
                      onClick={() => pick(i)}
                    >
                      {o.icon && <Icon icon={o.icon} size="m" className="picker-icon" />}
                      <span className="picker-text">
                        <Text as="span" size="s" id={`${id}-${i}`} content={o.label} />
                        {o.description && <Text as="span" size="xs" hierarchy="tertiary" id={`${id}-${i}-d`} content={o.description} />}
                      </span>
                      {o.value === value && <span aria-hidden="true" className="picker-pin" />}
                    </motion.li>
                  ))}
                </motion.ul>
              )}
            </AnimatePresence>
          </MotionConfig>,
          document.body,
        )}
    </>
  );
}
