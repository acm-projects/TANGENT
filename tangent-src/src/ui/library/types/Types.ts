/* Shared prop vocabularies — see DESIGN.md "Shared types".
 *
 * Only types that two or more components use live here. A union only one
 * component uses stays inline in that component. */

/* The one size scale. Every step needs a matching --font-size-* token in
 * tokens/text.css. */
export type TextSize = "xxs" | "xs" | "s" | "base" | "m" | "l" | "xl" | "xxl" | "display";

/* How much visual emphasis something gets. A component hands it down to its
 * parts so they agree on one look. */
export type Hierarchy = "tertiary" | "secondary" | "primary";

/* Whether a surface sits flat on the page or floats above it as frosted
 * glass. Independent of Hierarchy: any hierarchy can float. */
export type Elevation = "flat" | "floating";
