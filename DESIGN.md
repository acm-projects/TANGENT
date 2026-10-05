# DESIGN.md

How our UI is structured, and the rules that keep it modular.

**The deal:** `src/ui/components/` is a self-contained library that knows nothing
about Tangent. Everything else (`src/ui/pages/`, features, `src/api/`, `src/store/`)
is app code that consumes it. A component can be redesigned without opening a page,
and a page can be rewritten without opening a component.

There is no separate "designer" role on this project — whoever owns a component owns
its look. That means **a component's styling lives in the component's own folder**,
never in a global file reaching in from outside.

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
  api/                         ← client, typed endpoints, streaming
    client.ts
    services.ts
    stream.ts
    types.ts
  store/                       ← cross-page state
    treeStore.ts
frontend/AGENTS.md             ← rules for AI agents building features
docs/DEVELOPMENT.md            ← repo setup, workflow, backend design, testing
DESIGN.md                      ← this file
```

Imports use the `@/*` alias from `tsconfig.json`: `@/ui/components`,
`@/features/...`, `@/api/services`.

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
@layer reset, ui;                                /* pin the layer order first */
@import "../ui/components/tokens/index.css";

@layer reset {
  *, *::before, *::after { box-sizing: border-box; }
  * { margin: 0; padding: 0; }
}
```

Cascade order, weakest to strongest:

| Tier | Holds | Why it's there |
|------|-------|----------------|
| `@layer reset` | the `*` reset | must lose to components |
| `@layer ui` | `ui/components/**` CSS | beats the reset, loses to app code |
| unlayered | page and feature CSS | beats components without specificity fights |

**The reset must be inside a layer.** Unlayered CSS beats *every* layer regardless of
specificity, so an unlayered `* { padding: 0 }` silently outranks a component's own
`padding` — including a zero-specificity `:where()` rule. No specificity change fixes
that; only layer order does. This is the one ordering mistake that makes components
look broken for no visible reason.

### Component anatomy

```
Button/
  Button.tsx           ← structure + UI behaviour (no app logic)
  Button.css           ← look and motion, built only from tokens
  index.ts             ← export { Button } from "./Button";
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
  index.ts             ← export { Chat } from "./Chat";
```

### Page anatomy

```
workspace/
  Workspace.tsx        ← layout: arranges features, wires them together
  Workspace.css        ← page-level layout only (grid/areas), unlayered
  features/            ← features used only by this page
  index.ts             ← export { Workspace } from "./Workspace";
```

A component, feature, or page folder is self-contained: deleting or replacing it
must not break anything except the things that import it.

### Where does a new feature go?

Start it inside the page that needs it (`ui/pages/<page>/features/<name>/`).
The moment a *second* page needs it, move it to `src/features/<name>/` and update
the two imports. Don't pre-promote features on a guess that they'll be reused.

---

## 3. Modularity rules

### Rule 1: Three token tiers

```css
/* base.css: raw values, never used directly by components */
--purple-500: #7c3aed;

/* semantic.css: meaning */
--color-brand: var(--purple-500);

/* Button.css: component-level hook, falls back to semantic */
background: var(--button-bg, var(--color-brand));
```

- Components only reference **semantic** tokens, never base tokens or raw values.
- The test for tier 2: **can you name it without saying a colour?** `--color-danger`
  passes; `--color-red` is tier 1 in disguise.
- A rebrand = edit `semantic.css`. A one-component tweak = set `--button-bg`.

The payoff is theming. Because no component ever names a colour, a whole theme is a
few lines, and **no component file changes**:

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
`ui/components/` always import by direct relative path (`../primitives/Button`),
never through the barrel — importing your own barrel creates circular dependencies
and makes every edit invalidate everything.

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
/* Chat.css — one-off styling lives with the thing that needs it */
.chat-send { --button-bg: var(--color-accent); }
```

Delete the feature and the styling goes with it. Note it goes through a **published
custom-property hook**, not a selector reaching into Button's internals — so Button
keeps control of what is themeable.

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
:where([data-ui="message"][data-streaming]) {
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

- A page's CSS may set grid, areas, and spacing. It may not restyle a component's
  internals — use a variant, or a published custom-property hook.
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
  Passing `children` is fine — an element tree is serialisable.
- **Mark hook files too, not just components.** A module calling `useState`/`useEffect`
  needs its own `"use client"` if a feature barrel re-exports it: a server component
  importing *anything* from that barrel pulls every re-exported module into the
  server graph, and the build fails on the hook. This is the barrel hazard in Rule 4
  showing up as an RSC error rather than a circular import.

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
public API and the DOM can't be refactored. Expose a custom property instead.

### Themeable hooks

Each component publishes the custom properties it honours, as deliberately as it
publishes props:

```css
/* Button.css */
@layer ui {
  :where([data-ui="button"]) {
    background: var(--button-bg, var(--color-brand));
    padding: var(--button-padding, var(--space-2) var(--space-4));
  }
}
```

Two mechanisms make consumer overrides safe and `!important`-free:

- **`@layer ui`** — unlayered CSS (pages, features) always beats layered CSS,
  regardless of specificity.
- **`:where(...)`** — contributes zero specificity, so even a single class in a
  feature's CSS wins.

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
2. Create the folder with the anatomy from §2.
3. Use the correct native element; add `"use client"` only if it holds state (Rule 9).
4. Extend `ComponentProps<...>` and spread `...rest`; map variants to `data-*`.
5. Style only with semantic tokens, inside `@layer ui` and `:where()`.
6. Use motion tokens for any transition or animation.
7. Add a `:focus-visible` style if it's interactive.
8. Check it in both themes (flip `data-theme="dark"` on `:root` in devtools) — if
   it doesn't re-theme, it hardcoded a colour.
9. Export it from `ui/components/index.ts`.

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
- [ ] Button can be fully redesigned without opening any file in `pages/` or `features/`.
- [ ] No file in `ui/components/` imports from `pages/`, `features/`, `api/` or `store/`.
- [ ] No CSS outside a component targets that component's `data-part` internals.
- [ ] No feature imports a page, or another page's features.
- [ ] A feature can be moved from one page's `features/` folder to `src/features/`
      by changing imports only.
- [ ] `"use client"` appears on individual components, never on a barrel.
- [ ] Every file in `src/app/` is a thin route wrapper, not a screen.
