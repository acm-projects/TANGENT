/* The entry point pages and features import from (DESIGN.md Rule 4).
 *
 * Files INSIDE ui/components/ must not import this barrel — they import by
 * direct relative path, or you get circular dependencies.
 *
 * Never put "use client" in this file: it would ship the whole library to the
 * browser and silently disable server rendering everywhere (Rule 9). */

export { Button } from "./primitives/Button";
