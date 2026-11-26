# 2 · Button, DangerButton, Loading, InkText

**Files you own:** `frontend/src/ui/library/components/{Button,DangerButton,Loading,InkText}/*`.

DS spec and fixes:
- **Button:** primary = solid ink (one per view, the main action); secondary = paper with an outline;
  tertiary = no surface. Sizes follow the Text scale. Icon-only buttons are square, lift 3px on hover,
  keep their label as `aria-label`. Pressed squashes under the finger and springs back. A toggle whose
  panel is open carries `aria-pressed` and an emphasis border. Disabled: half opacity, not-allowed.
  **Fix:** the shared hover paints `--color-surface-raised` (paper) behind tertiary buttons everywhere,
  which reads wrong on cork and on Gent's ink (a light paper wash on a dark board at Night). A tertiary
  hover should tint from the current text colour instead
  (`background: color-mix(in srgb, currentColor 10%, transparent)`), so it reads in every scope.
  Keep secondary's paper hover. Keep all leather rules exactly as they are.
- **DangerButton:** hold to confirm; oxblood (`--color-danger`) outline, label and fill bar; never the
  string red. Check its disabled state reads disabled, its focus ring, and the fill bar's contrast in
  both themes.
- **Loading:** a red pin that breathes beside a short muted label (`role="status"`); the only loop
  besides Gent's ink; stops under reduced motion. Give the pin its real shadow (`--shadow-pin` at this
  size, or a scaled version through `color-mix` of the same token colour) instead of none.
- **InkText:** text that dries like wet ink while streaming. Probably correct; check it inherits
  colour in every scope and that `::selection` inside it is themed.
