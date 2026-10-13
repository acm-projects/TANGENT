import type { ComponentProps } from "react";
import type { Hierarchy, TextSize } from "../../types/Types";
import "./Icon.css";

/* A Material Symbols ligature: the icon name is drawn in the symbol font, so
 * `icon="home"` renders a house. Names: fonts.google.com/icons. The font is
 * loaded in app/layout.tsx.
 *
 * Icon renders its own <span> rather than <Text>: Text applies the content
 * font, and overriding that from here would mean restyling another
 * component's internals. Size and hierarchy mean the same as on Text. */

type IconProps = Omit<ComponentProps<"span">, "children"> & {
  icon: string;
  size?: TextSize;
  hierarchy?: Hierarchy;
};

export function Icon({ icon, size = "base", hierarchy = "secondary", ...rest }: IconProps) {
  return (
    <span aria-hidden="true" {...rest} data-ui="icon" data-size={size} data-hierarchy={hierarchy}>
      {icon}
    </span>
  );
}
