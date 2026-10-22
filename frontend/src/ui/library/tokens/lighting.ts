/* The board's lighting: the OS's light or dark by default (colors.css), or a
 * reader's own pick from Settings. Every colour is light-dark(), so pinning
 * the scheme on <html> is all it takes -- by attribute (colors.css), since the
 * build polyfills light-dark() and an inline color-scheme wouldn't reach it. Kept per browser (localStorage):
 * a convenience, so a blocked or empty store just falls back to the OS. */

export type Lighting = "system" | "light" | "dark";

const KEY = "tangent-lighting";

export function readLighting(): Lighting {
  try {
    const saved = localStorage.getItem(KEY);
    return saved === "light" || saved === "dark" ? saved : "system";
  } catch {
    return "system";
  }
}

/** Switches the lighting. With a pointer origin, the new lighting spreads out
 * from it like a lamp coming on (globals.css ::view-transition-new). */
export function setLighting(lighting: Lighting, from?: { x: number; y: number }) {
  try {
    if (lighting === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, lighting);
  } catch {}
  const apply = () => {
    if (lighting === "system") delete document.documentElement.dataset.lighting;
    else document.documentElement.dataset.lighting = lighting;
  };
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!document.startViewTransition || reduced || !from) return apply();
  document.documentElement.style.setProperty("--lamp-x", `${from.x}px`);
  document.documentElement.style.setProperty("--lamp-y", `${from.y}px`);
  document.startViewTransition(apply);
}

/** Runs before first paint (app/layout.tsx), so a picked lighting never flashes the OS one first. */
export const lightingScript = `try{var l=localStorage.getItem("${KEY}");if(l==="light"||l==="dark")document.documentElement.dataset.lighting=l}catch(e){}`;
