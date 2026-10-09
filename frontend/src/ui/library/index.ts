/* The entry point pages and features import from (DESIGN.md Rule 4).
 *
 * This is the ONLY barrel in the library — components are two files each, with
 * no per-component index.ts, so exports here name the file directly (§2).
 *
 * Files INSIDE ui/library/ must not import this barrel — they import by
 * direct relative path, or you get circular dependencies.
 *
 * Never put "use client" in this file: it would ship the whole library to the
 * browser and silently disable server rendering everywhere (Rule 9). */

export { Text } from "./primitives/Text/Text";
export { Icon } from "./primitives/Icon/Icon";
export { Panel } from "./primitives/Panel/Panel";
export { Frame } from "./primitives/Frame/Frame";
export { Link } from "./primitives/Link/Link";
export { Image } from "./primitives/Image/Image";
export { Input } from "./primitives/Input/Input";
export { TextArea } from "./primitives/TextArea/TextArea";
export { Divider } from "./primitives/Divider/Divider";
export { ProgressiveBlur } from "./primitives/ProgressiveBlur/ProgressiveBlur";
export { Button } from "./components/Button/Button";

export type { TextSize, Hierarchy, Elevation } from "./types/Types";
