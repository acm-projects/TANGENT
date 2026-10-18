"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { Frame } from "../../primitives/Frame/Frame";
import { Panel } from "../../primitives/Panel/Panel";
import { Text } from "../../primitives/Text/Text";
import "./Popup.css";

/* A modal popup: a sheet of paper over a dimmed board. It is a native <dialog>
 * opened with showModal(), so the browser handles focus trapping, Escape to
 * close and the top layer (it escapes any transformed parent, such as a map
 * node). Clicking the dim backdrop closes it too.
 *
 * Controlled: `open` shows it, and onClose reports every way it closed (Escape,
 * backdrop) so the owner can set `open` back to false. Children are the body
 * and actions, under the title. Styles in Popup.css. */

type PopupProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
};

export function Popup({ open, onClose, title, children }: PopupProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (open && !dialog?.open) dialog?.showModal();
    if (!open && dialog?.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      data-ui="popup"
      // React Flow (and other pan/drag surfaces) ignore events from inside these classes.
      className="nopan nodrag nowheel"
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(e) => {
        // The dialog's React parent may be clickable (a map node); a popup click is not a click on it.
        e.stopPropagation();
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <Panel elevation="floating">
        <Frame gap="4">
          <Text as="h2" id={titleId} size="l" hierarchy="primary" content={title} />
          {children}
        </Frame>
      </Panel>
    </dialog>
  );
}
