# DESIGN.md

How our UI is structured, and the rules that keep it modular.

**The deal:** `src/ui/components/` is a self-contained library that knows nothing
about Tangent. Everything else (`src/ui/pages/`, features, `src/api/`, `src/store/`)
is app code that consumes it. A component can be redesigned without opening a page,
and a page can be rewritten without opening a component.

There is no separate "designer" role on this project — whoever owns a component owns
its look. That means **a component's styling lives in the component's own folder**,
never in a global file reaching in from outside.

### Two principles that outrank every rule below

**1. As little code as possible per unique component.** Every layer of indirection
is something a person types by hand, for every component, forever. A rule earns its
place by preventing a real bug, not by being more general. **When two mechanisms do
the same job, keep one.**

**2. No fallbacks.** Never write `var(--a, var(--b))`, and never give a value a
second place to come from. A fallback converts a mistake into a plausible-looking
result: misspell `--a` and CSS silently uses `--b`, the component renders fine, and
what you actually wrote is ignored. Nothing errors and nothing logs, so you find out
when someone eventually notices the colour is wrong.

Drop the fallback and an undefined custom property makes the declaration invalid, so
the style **visibly breaks** — which is the outcome you want. A loud failure costs a
minute; a silent one costs a day.

The corollary is what removes most of the code: **if a value always has a definition,
the fallback is dead code that can only ever hide a typo.** A component always defines
its own look, so it never needs one.

---

## 1. The layers

Everything is built in layers. Each layer may only use the layers to its left.

```
tokens  →  primitives  →  composites  →  features  →  pages
(values)   (building       (built from     (reusable    (a screen of
            blocks)         primitives)     behaviour)   the site)
```

| Layer      | What it is                                        | Examples                              |
|------------|---------------------------------------------------|---------------------------------------|
| Tokens     | Design decisions as CSS custom properties         | `--color-brand`, `--radius-md`        |
| Primitives | Small, single-purpose components                  | Button, Text, Stack, Icon             |
| Composites | Bigger components assembled from primitives       | Select, Dialog, Card, TextField       |
| Features   | Self-contained pieces of app behaviour a page uses| `workspace/features/chat/`            |
| Pages      | Whole screens of the site, assembled from features| `ui/pages/workspace/`                 |

**A layer is defined by what it may import, not by how big it is.** Asking "is this a
primitive or a composite?" is not a question about size: if it imports another
component it's a composite, otherwise it's a primitive. Keep it mechanical.

### Pages vs. features

This is the distinction that matters most:

- A **page** is a screen of the site — landing, login, workspace. It owns layout
  and composition. A page is mostly *arrangement*: it decides which features go
  where, and wires them to each other.
- A **feature** is a piece a page uses — chat, toolbar. It owns its own behaviour,
  state and data calls, and knows nothing about the page it sits in. A feature is
  a unit you could drop into a second page without editing it.

Rule of thumb: if it has a URL, it's a page. If it's a thing *on* a page that
could move to another page, it's a feature.

---

## 2. File structure

```
frontend/src/
  app/                         ← Next.js App Router: routes only, no UI
    layout.tsx                 ← renders a page component from ui/pages/
    page.tsx
    globals.css                ← the one CSS entry point (see below)
  ui/
    components/                ← the design library
      tokens/
        base.css               ← raw values: palette, spacing scale, font sizes
        semantic.css           ← meaning: --color-surface, --color-danger, --color-text-muted
        motion.css             ← durations, easings, shared keyframes, reduced-motion rule
        index.css              ← imports the three above, in order
      primitives/
        Button/
        Text/
        Stack/
        Icon/
      composites/
        Card/
        Dialog/
        Select/
        TextField/
      index.ts                 ← the entry point pages and features import from
    pages/                     ← one folder per screen of the site
      landing/
      login/
      workspace/
        features/              ← features used only by this page
          chat/
          toolbar/
  features/                    ← features shared by two or more pages
  api/                         ← the backend seam
    client.ts                  ← transport: auth header, single-flight refresh
    stream.ts                  ← transport: SSE over fetch
    session.ts                 ← the app's one client instance + in-memory token
    types.ts                   ← wire types
    endpoints/                 ← one file per endpoint group (nodes, trees, auth)
    index.ts                   ← the entry point features import from
  store/                       ← cross-page state
    treeStore.ts
frontend/AGENTS.md             ← auto-generated by `next dev`; do not hand-edit
docs/ARCHITECTURE.md           ← how the system works, and why
docs/FILE_STRUCTURE.md         ← where a new file goes
docs/DEVELOPMENT.md            ← setup, workflow, testing, troubleshooting
docs/DESIGN.md                 ← this file
```

Imports use the `@/*` alias from `tsconfig.json`: `@/ui/components`,
`@/features/...`, `@/api`.

**File extensions:** `.tsx` for any file containing JSX, `.ts` for files with none.
So `Button.tsx`, `Chat.tsx`, but `useChat.ts`, `api.ts`, `index.ts`. `tsconfig.json`
sets `strict: true` and `"jsx": "react-jsx"`, so a `.ts` file with JSX in it fails
typecheck — the split enforces itself.

**Plain `.css`, not CSS Modules.** Modules hash class names, which breaks the
`data-ui` styling contract in §4 and makes component CSS untargetable from a
consumer. We rely on global, unhashed selectors on purpose.

### Wiring the CSS

`src/app/globals.css` is the only CSS entry point (`layout.tsx` imports it):

```css
@layer reset, ui;                     /* pin the order first: reset < ui < unlayered */

@import "../ui/components/tokens/index.css";

@layer reset {
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: system-ui, sans-serif;
    background: var(--color-surface);
    color: var(--color-text);
  }
}
```

The priority order, lowest to highest:

```
@layer reset   →   @layer ui   →   unlayered
(the * reset)      (components)    (pages, features)
```

Component CSS lives inside `@layer ui`. Page and feature CSS stays **unlayered**,
because unlayered CSS always beats layered CSS — that's what lets a page override a
component without specificity fights. See §4.

**The reset must be inside a layer, and it must come first.** This is the one piece
of the layer model that bites. Cascade layers outrank specificity, and *unlayered
declarations outrank every layer* — so an unlayered `* { padding: 0 }` silently beats
`@layer ui { [data-ui="button"] { padding: ... } }` even though the component selector
is far more specific. Every component would lose its padding and margin, and the
cascade would give you no warning. Putting the reset in `@layer reset` restores the
order you actually want.

### Component anatomy

```
Button/
  Button.tsx           ← structure + UI behaviour (no app logic)
  Button.css           ← look and motion, built only from tokens
```

**Two files, not three.** There is no per-component `index.ts`. A one-line
re-export file per component is pure overhead: the only barrel is
`ui/components/index.ts`, and it imports the file directly:

```ts
// ui/components/index.ts
export { Button } from "./primitives/Button/Button";
```

A component should be viewable in isolation — if it needs a page, a route, or a
logged-in session to look at, it isn't a component yet. A component explorer
(Storybook or similar) is **[planned]**, not installed; when it lands, each folder
also gets a `Button.stories.tsx` covering every variant and state.

### Feature anatomy

```
chat/
  Chat.tsx             ← the feature's UI, built from ui/components
  Chat.css             ← layout + any one-off styling it needs (unlayered)
  useChat.ts           ← its state and behaviour
  api.ts               ← its calls, wrapping @/api (optional)
  components/          ← pieces only this feature uses (optional)
```

### Page anatomy

```
workspace/
  Workspace.tsx        ← layout: arranges features, wires them together
  Workspace.css        ← page-level layout only (grid/areas), unlayered
  features/            ← features used only by this page
```

Features and pages have no `index.ts` either — import the file:
`import { Chat } from "./features/chat/Chat"`.

A component, feature, or page folder is self-contained: deleting or replacing it
must not break anything except the things that import it.

### Where does a new feature go?

Start it inside the page that needs it (`ui/pages/<page>/features/<name>/`).
The moment a *second* page needs it, move it to `src/features/<name>/` and update
the two imports. Don't pre-promote features on a guess that they'll be reused.

---

## 3. Modularity rules

### Rule 1: Two token tiers, and a component uses the second one directly

```css
/* base.css — tier 1: raw values. Never referenced by a component. */
--purple-500: #7c3aed;

/* semantic.css — tier 2: meaning. The only tier a component may name. */
--color-brand: var(--purple-500);

/* Button.css — the component just uses it. No third name, no fallback. */
background: var(--color-brand);
```

- Components reference **semantic** tokens only — never base tokens, never a raw
  value.
- The test for tier 2: **can you name it without saying a colour?** `--color-danger`
  passes; `--color-red` is tier 1 in disguise.
- A rebrand = edit `semantic.css`. One component's look = edit that component's CSS.

**There is no third tier.** A component does not publish `--button-bg` alongside the
semantic token it already reads. That pattern costs three names per visual property
(`--_bg` private, `--button-bg` public, `--color-brand` semantic) joined by a
fallback, and the fallback is exactly the silent failure Principle 2 is about: a
consumer who writes `--buton-bg` gets no error, no warning, and no effect. Overrides
have a simpler mechanism — see Rule 6 and §4.

The payoff is still theming. Because no component ever names a colour, a whole theme
is a few lines, and **no component file changes**:

```css
:root                   { --color-surface: var(--gray-50);  --color-text: var(--gray-900); }
:root[data-theme="dark"]{ --color-surface: var(--gray-900); --color-text: var(--gray-50);  }
```

### Rule 2: Composites reuse primitives

Select uses our Button. Dialog uses our Button and Text. Never style the same
thing twice. If a composite needs a button, it uses `<Button>`, not a raw `<button>`.

### Rule 3: Composition over configuration

Prefer small pieces that snap together:

```tsx
<Card>
  <Card.Header>Plan</Card.Header>
  <Card.Body>...</Card.Body>
  <Card.Footer>...</Card.Footer>
</Card>
```

over one component with a pile of props (`<Card title subtitle footer showDivider headerIcon ...>`).

### Rule 4: Imports flow one way

```
app/  →  ui/pages/  →  features  →  ui/components/  →  tokens
```

- `app/` holds routes only. A route file renders a page component and nothing else.
- A **page** may import `ui/components`, `src/features/`, and its own `features/`.
- A **feature** may import `ui/components`, `@/api`, and `@/store`. It must
  **never** import a page, or another page's features.
- `ui/components/` must **never** import from `pages/`, `features/`, `api/`, or
  `store/`. The library knows nothing about chat, workspaces or the API.
- Composites may import primitives; primitives must not import composites.

**Barrel discipline:** consumers import from `@/ui/components`. Files *inside*
`ui/components/` always import the file directly
(`../primitives/Button/Button`), never through the barrel — importing your own
barrel creates circular dependencies and makes every edit invalidate everything.

> Not yet enforced by tooling **[planned]**. Lint zones (`import/no-restricted-paths`)
> or `dependency-cruiser` can encode this graph in CI. Worth doing while there are
> zero violations to fix.

### Rule 5: Look and logic stay separate

- Components in `ui/components/` contain **UI behaviour** only: open/close, hover,
  focus, keyboard.
- **App logic** (fetching, saving, business rules) lives in features, usually as
  hooks like `useChat()`, and is passed into components via props.

```tsx
// ui/pages/workspace/features/chat/Chat.tsx
<Button variant="primary" disabled={!chat.canSend} onClick={chat.send}>
  Send
</Button>
```

### Rule 6: Where a style change goes

Four destinations, and picking the right one is most of what keeps this modular:

| Need                                | Goes in                                      |
|-------------------------------------|----------------------------------------------|
| Recurring, nameable intent          | a **variant prop** — `variant="danger"`      |
| A true one-off, with no good name   | the **consumer's own CSS**, scoped to it     |
| Different *behaviour* or semantics  | a **new component**                          |
| Whole-app art direction             | **`semantic.css`**                           |

- **Variants are data attributes, not new components.** `<Button variant="danger">`
  renders `data-variant="danger"`, styled in `Button.css`. Never create
  `DangerButton`, `BigButton`, `GlowButton` — that way you get a combinatorial
  explosion where one token change has to be applied in nine places.
- **One-offs belong to their consumer.** Don't widen a component's variant union for
  a single call site (`variant="checkout-cta"` is not a variant). The feature owns a
  class, in its own CSS file, next to the code that needs it:

```tsx
<Button variant="primary" className="chat-send">Send</Button>
```
```css
/* Chat.css — one-off styling lives with the thing that needs it.
   Unlayered, so it beats Button.css without a fight. */
.chat-send { background: var(--color-accent); }
```

Delete the feature and the styling goes with it.

The consumer sets **the real property**, not a custom property the component had to
publish first. That works because `Chat.css` is unlayered and `Button.css` is in
`@layer ui`, and unlayered CSS always wins (§4) — so there is nothing to opt into and
nothing to spell correctly. If the selector is wrong you see no change and go look at
it; if a hook name were wrong you'd see no change and have no idea why.

**Still off-limits:** reaching into a component's internals (`.chat-send [data-part]`).
Override what the component renders at its root, not how it is built inside.

### Rule 7: Motion is its own module

- Durations and easings are tokens in `motion.css` (`--motion-fast`, `--ease-bouncy`).
  Components use those tokens, never a hard-coded `200ms ease`.
- **Features decide *when*, components decide *how*.** When an animation is triggered
  by app state, the feature flips a prop and the component owns the keyframes:

```tsx
<Message data-streaming={isStreaming} />          {/* feature: when */}
```
```css
/* Message.css — component: how */
[data-ui="message"][data-streaming] {
  animation: shimmer var(--motion-slow) var(--ease-out) infinite;
}
```

- Enter/exit animation is native now: `@starting-style` plus
  `transition-behavior: allow-discrete`. Reach for that before any JS.
- **Reduced motion** works by zeroing the duration tokens under
  `prefers-reduced-motion` in `motion.css`. This only covers animations that *use* the
  tokens — a hand-written `animation: glow 2s` is not caught, and neither is anything
  animated in JS. If you hand-write keyframes, honour the preference yourself
  (`matchMedia("(prefers-reduced-motion: reduce)")` for the JS case).

### Rule 8: Pages lay out, features behave

- A page's CSS may set grid, areas, and spacing. It may not reach into a component's
  internals (`data-part`) — use a variant, or override at the component's root from
  the page's own unlayered CSS.
- A page holds no data fetching of its own. If a screen needs data, that belongs
  to one of its features.

### Rule 9: Keep `"use client"` as deep as possible

Every component is a **Server Component by default**. `"use client"` is required for
`useState`, `useEffect`, event handlers, or store access — and it is **contagious
downward**: everything a client component imports ships to the browser too.

- **Never put `"use client"` in `ui/components/index.ts`.** That ships the whole
  library to the client and silently disables server rendering everywhere. It
  produces no error, just a worse app.
- Mark the individual interactive component. Keep static primitives (`Text`, `Stack`,
  `Icon`, `Card`) directive-free so they render on the server.
- Features are usually the client boundary; pages stay server components where they
  can. This matches Rule 8 — pages arrange (server), features behave (client).
- Never pass a function as a prop from a server component into a client one.

---

## 4. The component contract

### Props

```tsx
// ui/components/primitives/Button/Button.tsx
import type { ComponentProps } from "react";
import "./Button.css";

type ButtonProps = ComponentProps<"button"> & {
  variant?: "primary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
};

export function Button({ variant = "primary", size = "md", ...rest }: ButtonProps) {
  return <button data-ui="button" data-variant={variant} data-size={size} {...rest} />;
}
```

- **Extend the native element** with `ComponentProps<"button">` and spread `...rest`.
  You get `disabled`, `type`, `aria-*`, and every event handler for free, forever.
  Hand-listing props turns the component into a bottleneck needing a PR per attribute.
- **Union types, not boolean flags.** `variant?: "primary" | "ghost"`, never
  `primary?: boolean; ghost?: boolean` — the latter permits `<Button primary ghost />`.
- **No `forwardRef`.** On React 19 `ref` is an ordinary prop for function components.
- **Controlled/uncontrolled naming:** bare prop for controlled, `default*` for
  uncontrolled (`value`/`defaultValue`, `open`/`defaultOpen`), as the platform does.

### Styling attributes

| Attribute                                  | Set by     | Purpose                            |
|--------------------------------------------|------------|------------------------------------|
| `data-ui`                                  | component  | Identifies the component           |
| `data-variant`, `data-size`, `data-tone`   | props      | Styled from the component's own CSS|
| `data-part`                                | component  | Names an internal piece            |
| `data-hovered`, `data-pressed`, `data-open`| component  | Interaction state, styled in CSS   |

`data-ui` and `data-variant` are also the right selectors in tests — stable, and
independent of class names.

`data-part` is an **internal** naming convention. Consumers must not target it: the
moment outside CSS depends on a component's internal structure, that structure is
public API and the DOM can't be refactored. If an internal piece genuinely needs to be
stylable from outside, that is a signal it should be a slot the consumer passes in, or
its own component — not a custom property threaded through.

### Writing the CSS

A component's CSS sets **real properties from semantic tokens**. No private
`--_vars`, no published hooks, no `var(a, b)`. Variants and sizes set the same
properties again:

```css
/* Button.css */
@layer ui {
  [data-ui="button"] {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-4);
    border: 1px solid transparent;
    border-radius: var(--radius-md);
    font-size: var(--font-size-md);
    background: var(--color-brand);
    color: var(--color-text-on-brand);
    cursor: pointer;
    transition: background var(--motion-fast) var(--ease-out);
  }

  [data-ui="button"]:hover:not(:disabled) {
    background: var(--color-brand-hover);
  }

  [data-ui="button"][data-variant="ghost"] {
    background: transparent;
    border-color: var(--color-border);
    color: var(--color-text);
  }

  /* Required. Without it, a hovered ghost button turns brand-coloured,
     because the base :hover rule is more specific than the variant rule. */
  [data-ui="button"][data-variant="ghost"]:hover:not(:disabled) {
    background: var(--color-surface-raised);
  }

  [data-ui="button"][data-size="sm"] {
    padding: var(--space-1) var(--space-3);
    font-size: var(--font-size-sm);
  }

  [data-ui="button"]:focus-visible {
    outline: 2px solid var(--color-focus-ring);
    outline-offset: 2px;
  }
}
```

**Two things make this work, and both are mechanical:**

1. **Always qualify with `data-ui`.** Write `[data-ui="button"][data-variant="ghost"]`,
   never a bare `[data-variant="ghost"]`. Qualified, the variant is specificity
   `(0,2,0)` and beats the base rule's `(0,1,0)` outright. Bare, it ties with the base
   rule and the winner depends on source order — which breaks the moment someone
   reorders the file.
2. **Every variant that differs on hover (or focus, or `:disabled`) needs its own
   state rule.** The base `:hover:not(:disabled)` is `(0,3,0)`, so it outranks any
   plain variant rule. This is the one real cost of dropping custom properties: a few
   extra rules instead of an indirection layer you maintain in every component. Forget
   one and the button visibly flashes the wrong colour on hover — a bug you see
   immediately rather than one that hides.

**No `:where()`.** It contributed zero specificity so that a consumer's single class
could win — but `@layer ui` already guarantees that, since unlayered CSS beats layered
CSS regardless of specificity. Two mechanisms for one job, so we keep the one that
also lets normal specificity do the work above. Component selectors are plain.

### How a consumer overrides

One mechanism: **`@layer ui`.**

- Component CSS is inside `@layer ui`.
- Page and feature CSS is **unlayered**.
- Unlayered beats layered, always, regardless of specificity. So a single class in
  `Chat.css` overrides anything in `Button.css`, with no `!important` and nothing the
  component had to publish in advance.

That is the whole contract. A consumer needs no permission and no hook name; it just
needs its CSS to be unlayered, which it is by default.

---

## 5. Accessibility

We hand-build components rather than wrapping a headless library, so accessibility
is our responsibility. It is not evenly distributed:

- **Primitives are easy.** Use the correct native element — `<button>`, not
  `<div onClick>` — and focus, keyboard activation, and screen-reader semantics come
  free from the platform. Always render a real `<label>` for form controls.
- **Composites are where the work is.** `Dialog` needs a focus trap, scroll lock,
  `aria-modal`, Escape, and focus restored on close. `Select` needs roving tabindex,
  typeahead, and `aria-activedescendant`. These bugs are invisible to a sighted mouse
  user and will not be noticed until someone uses a keyboard.
- **Prefer the platform:** `<dialog>` with `showModal()` gives focus trapping,
  Escape, and `::backdrop` for free; the Popover API handles light dismiss.
- A headless library for just `Dialog`/`Select`/`Combobox` is a legitimate choice
  later. It would be an implementation detail *inside* that component's folder,
  invisible to every consumer — which is Rule 4 working as intended.

Every interactive component needs a visible `:focus-visible` style. Don't remove
outlines without replacing them.

---

## 6. Checklists

### Adding a component

1. Can it be built by composing existing primitives? If yes, it's a composite.
2. Create the folder — two files, `Thing.tsx` and `Thing.css`. No `index.ts`.
3. Use the correct native element; add `"use client"` only if it holds state (Rule 9).
4. Extend `ComponentProps<...>` and spread `...rest`; map variants to `data-*`.
5. Style with semantic tokens inside `@layer ui`. Set real properties — **no
   `var(a, b)` fallback, no `--_private` vars, no published hooks** (Rule 1, §4).
6. Qualify every selector with `data-ui`, and give each variant its own `:hover` /
   `:focus-visible` / `:disabled` rule where it differs (§4).
7. Use motion tokens for any transition or animation.
8. Add a `:focus-visible` style if it's interactive.
9. Check it in both themes (flip `data-theme="dark"` on `:root` in devtools) — if
   it doesn't re-theme, it hardcoded a colour.
10. Export it from `ui/components/index.ts`, importing the file directly.

### Adding a page

1. Create `ui/pages/<name>/` with the page anatomy from §2.
2. Add the route in `src/app/` — it renders the page component and nothing else.
3. Break the screen into features. Anything with its own state or data calls is a
   feature, not page code.
4. Put page-only features in `ui/pages/<name>/features/`; reach for
   `src/features/` only once a second page uses it.
5. Build the layout from primitives and page-level CSS. No hex colours, no inline
   styles, no restyling component internals.

---

## 7. The modularity test

The structure is working if all of these are true:

- [ ] Changing `--color-brand` recolours the whole app.
- [ ] No component hardcodes a hex colour or a duration.
- [ ] `grep -r "var(--[a-z-]*," src/ui` finds nothing — no fallbacks anywhere.
- [ ] No component defines a custom property; it only reads semantic tokens.
- [ ] Every component is two files.
- [ ] Button can be fully redesigned without opening any file in `pages/` or `features/`.
- [ ] No file in `ui/components/` imports from `pages/`, `features/`, `api/` or `store/`.
- [ ] No CSS outside a component targets that component's `data-part` internals.
- [ ] No feature imports a page, or another page's features.
- [ ] A feature can be moved from one page's `features/` folder to `src/features/`
      by changing imports only.
- [ ] `"use client"` appears on individual components, never on a barrel.
- [ ] Every file in `src/app/` is a thin route wrapper, not a screen.
