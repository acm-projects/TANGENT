# DESIGN.md

How our UI is structured, and the rules that keep it modular.

**The deal:** `src/ui/library/` is a self-contained library that knows nothing
about Tangent. Everything else (`src/ui/features/`, `src/ui/pages/`, `src/api/`,
`src/store/`) is app code that consumes it. A component can be redesigned without opening a page,
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
tokens  →  primitives  →  components  →  features  →  pages
(values)   (building       (built from     (reusable    (a screen of
            blocks: Text)   primitives:     behaviour:   the site:
                            Button)         Auth)        login)
```

| Layer      | What it is                                        | Examples                              |
|------------|---------------------------------------------------|---------------------------------------|
| Tokens     | Design decisions as CSS custom properties         | `--color-brand`, `--radius-md`        |
| Primitives | Small, single-purpose components                  | Text, Panel, Icon, Frame              |
| Components | Assembled from primitives and other components    | Button, Select, Dialog, Card          |
| Features   | Self-contained pieces of app behaviour a page uses| `ui/features/auth/`                   |
| Pages      | Whole screens of the site, assembled from features| `ui/pages/login/`                     |

Tokens, primitives and components together are **the library** (`ui/library/`).
"Component" names the layer; "library piece" means anything in the library.

**A layer is defined by what it may import, not by how big it is.** Asking "is this a
primitive or a component?" is not a question about size: if it imports another
library piece it's a component, otherwise it's a primitive. Keep it mechanical.

### Pages vs. features

This is the distinction that matters most:

- A **page** is a screen of the site — landing, login, workspace. It owns layout
  and composition. A page is mostly *arrangement*: it decides which features go
  where, and wires them to each other.
- A **feature** is a piece a page uses — chat, toolbar. It owns its own behaviour,
  state and data calls, and knows nothing about the page it sits in. A feature is
  a unit you could drop into a second page without editing it.

Rule of thumb: if it has a URL, it's a page. If it's a thing *on* a page that
could move to another page, it's a feature. **A page folder is named after its
route:** `/login` is `app/login/page.tsx`, which renders `ui/pages/login/Login.tsx`.

---

## 2. File structure

```
frontend/src/
  app/                         ← Next.js App Router: routes only, no UI
    layout.tsx                 ← root layout: loads fonts, sets the default theme
    page.tsx
    login/page.tsx             ← renders ui/pages/login/Login
    globals.css                ← the one CSS entry point (see below)
  ui/
    library/                   ← the design library: knows nothing about Tangent
      tokens/
        colors.css             ← palette (tier 1) + colour meanings (tier 2) + dark theme
        shape.css              ← spacing scale, radii, elevation (shadow, blur, glass mix)
        text.css               ← typography: font families, size scale, weights, line heights
        motion.css             ← durations, easings, reduced-motion rule
        index.css              ← imports the four above
      types/
        Types.ts               ← shared prop vocabularies (TextSize, Hierarchy, Elevation)
      primitives/
        Text/
        Panel/
        Icon/
        Frame/
      components/
        Button/                ← Panel + Text + Icon
      index.ts                 ← the entry point features and pages import from
    features/                  ← features shared by two or more pages (or planned to be)
      auth/                    ← the sign-in card
    pages/                     ← one folder per route, named after it
      login/
      workspace/
        features/              ← features used only by this page
          chat/
          toolbar/
  api/                         ← the backend seam
    client.ts                  ← transport: auth header, single-flight refresh
    stream.ts                  ← transport: SSE over fetch
    session.ts                 ← the app's one client instance + in-memory token
    types.ts                   ← wire types
    endpoints/                 ← one file per endpoint group (nodes, trees, auth)
    index.ts                   ← the entry point features import from
  store/                       ← persisting cross-page state
    treeStore.ts
frontend/AGENTS.md             ← auto-generated by `next dev`; do not hand-edit
docs/ARCHITECTURE.md           ← how the system works, and why
docs/FILE_STRUCTURE.md         ← where a new file goes
docs/DEVELOPMENT.md            ← setup, workflow, testing, troubleshooting
docs/DESIGN.md                 ← this file
```

Imports use the `@/*` alias from `tsconfig.json`: `@/ui/library`,
`@/ui/features/...`, `@/api`.

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

@import "../ui/library/tokens/index.css";

@layer reset {
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: var(--font-content);
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
`ui/library/index.ts`, and it imports the file directly:

```ts
// ui/library/index.ts
export { Button } from "./components/Button/Button";
```

A component should be viewable in isolation — if it needs a page, a route, or a
logged-in session to look at, it isn't a component yet. A component explorer
(Storybook or similar) is **[planned]**, not installed; when it lands, each folder
also gets a `Button.stories.tsx` covering every prop value and state.

### Feature anatomy

```
chat/
  Chat.tsx             ← the feature's UI, built from ui/library
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
The moment a *second* page needs it, move it to `ui/features/<name>/` and update
the imports. Don't pre-promote features on a guess that they'll be reused.

**The one exception:** when a second user is already *planned* — not hoped for —
put it straight into `ui/features/`. Auth is the example: the login page uses it
now, and a re-auth dialog in the workspace will use it next. Write that second user
in a comment at the top of the feature, so the reason is visible.

---

## 3. Modularity rules

### Rule 1: Two token tiers, and a component uses the second one directly

Token files are split by **kind of value** — `colors.css`, `shape.css`, `text.css`,
`motion.css` — not by tier. Where a kind has both tiers (colours, elevation), the
file holds both, raw values first, and each tier-2 token references only its own
file's tier-1 values, so the files can be imported in any order.

```css
/* colors.css, tier 1: raw values. Never referenced by a component. */
--purple-500: #7c3aed;

/* colors.css, tier 2: meaning. The only tier a component may name. */
--color-brand: var(--purple-500);

/* Button.css — the component just uses it. No third name, no fallback. */
background: var(--color-brand);
```

- Components reference **semantic** tokens only — never a palette token, never a
  raw value. Scales (`--space-*`, `--radius-*`, `--font-size-*`, `--motion-*`) are
  used directly: their names already say what they're for.
- The test for tier 2: **can you name it without saying a colour?** `--color-danger`
  passes; `--color-red` is tier 1 in disguise.
- A rebrand = edit the tier-2 block of `colors.css`. One component's look = edit that component's CSS.

**What may be a raw value.** Tokens are for *design decisions*; structural
constants may be written raw.

| Must be a token | May be raw |
|-----------------|------------|
| colours, spacing, radii | hairline widths: `1px` borders, `2px` focus outlines |
| font sizes, weights, families | `0`, `1`, `100%`, `auto` |
| durations, easings | `line-height: 1` on icons |
| shadows, blurs, glass mix | `opacity: 0.5` for disabled — until a second component needs it, then `--opacity-disabled` |
| anything a theme or rebrand would change | |

A page's or feature's **own layout values** (`max-width: 24rem` on a card, the
`16px` dot grid on the login background) may be raw too, because they're one-offs
that belong to that page (Rule 6). The moment a second page or feature needs the
same value, it becomes a token.

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

### Rule 1a: Typography and theme

Typography tokens live in their own file, `tokens/text.css`.

- **Fonts are loaded by `next/font`** in `app/layout.tsx`, which puts
  `--font-bungee`, `--font-roboto` and `--font-material-symbols` on `<html>`.
  `text.css` maps those to the three roles a component may use:
  - `--font-heading` (Bungee): headings and display text.
  - `--font-content` (Roboto): everything else. `body` uses it, so it is the default.
  - `--font-icon` (Material Symbols Rounded, filled): only `Icon` uses it.
    `next/font/google` doesn't carry it, so `layout.tsx` loads the file from the
    `@material-symbols/font-400` package with `next/font/local` and
    `display: "block"` (otherwise ligature names like "home" flash as text before
    the glyphs load). Fill is `font-variation-settings: "FILL" 1` in `Icon.css`.
- **Sizes come from one scale**, named the same as the `TextSize` type (see
  "Shared types" below): `xxs, xs, s, base, m, l, xl, xxl, display`. Every step
  in the type needs a matching `--font-size-*` token, and each component maps its
  `size` prop onto those tokens. A size in the type with no token is a bug.
- **Dark is the default theme.** `layout.tsx` sets `data-theme="dark"` on `<html>`.
  Check a new component in light as well (remove the attribute in devtools).

### Shared types

Prop vocabularies that more than one component uses live in
`ui/library/types/Types.ts`, not inline in each component:

```ts
export type TextSize  = "xxs" | "xs" | "s" | "base" | "m" | "l" | "xl" | "xxl" | "display";
export type Hierarchy = "tertiary" | "secondary" | "primary";
export type Elevation = "flat" | "floating";
```

- **`TextSize`** is the one size scale. Text, Icon, Button and anything else with a
  `size` prop use it, so `size="l"` means the same thing everywhere.
- **`Hierarchy`** is how much visual emphasis something gets, and nothing else. A
  component passes it down to its parts (Button hands it to Panel, Icon and Text) so
  they agree on one look. **Panel owns colour; Text and Icon inherit it.** Panel's
  hierarchy picks the surface colour (`primary` = brand fill, `secondary` =
  bordered surface, `tertiary` = transparent) and sets `color` to match. Text and
  Icon use `color: inherit`, so they read correctly on any surface. On Text and
  Icon, hierarchy only changes emphasis: `primary` is heavier, `tertiary` is muted.
- **`Elevation`** is whether a surface sits flat or floats as frosted glass. Only
  surfaces take it: Panel, and Button (which hands it to its Panel). It's separate
  from `Hierarchy` because it's a different property. Every combination works:
  floating mixes the hierarchy's own colour into the glass (brand for `primary`,
  surface for `secondary`; `tertiary` stays transparent and only gains blur and
  shadow). A floating Button stays glass on hover, with more colour showing
  (`--glass-mix` → `--glass-mix-hover`).
- **A shared type must mean something to every component that takes it.** If a
  value would do nothing on one of them, it belongs in a separate prop.
- Add a type here only once a **second** component needs it, the same rule as for
  features. A union only one component uses stays inline in that component.
- `Types.ts` holds only types. If it grows a runtime value (for example a
  `TEXT_SIZES` array to loop over), it is still a `.ts` file, since it has no JSX.

### Rule 2: Every element comes from the library

**A page or feature never renders a raw HTML tag.** No `<div>`, no `<p>`, no
`<span>`, no `<button>` — not even for layout. If it is on screen, it is a component
from `ui/library/`; if that piece doesn't exist yet, you build it before you
build the screen.

Text is included, and is the usual temptation: every string on screen goes through
`<Text>`, never a bare `<p>` or `<h2>`. So is layout: a wrapper is `<Frame>` or
`<Panel>`, not a `<div className="row">`.

Native tags live in exactly one place — inside a primitive, whose whole job is to
wrap one. Components build from primitives and other components: Select uses our
Button, Dialog uses our Button and Text. Never style the same thing twice. Fragments (`<>`) are fine — they
render nothing.

**Primitives choose their tag with `as`.** A primitive that could be several
elements takes an `as` prop limited to the tags that make sense for it, so pages
keep their semantics without raw tags: `<Frame as="main">`, `<Panel as="section">`,
`<Text as="h1">`. A component uses the same mechanism: Button's root is
`<Panel as="button">`, so Button itself renders no raw tag either.

**Why.** A raw tag is unstyled, untokenized, and invisible to every rule in this
document. It inherits whatever the reset left it, sits next to real components
looking approximately right, and drifts from them with no error — the silent-failure
shape Principle 2 exists to kill. It also guarantees the next screen needing the same
thing re-invents it slightly differently instead of importing one file.

The cost is deliberate: having to build `<Text>` before you can write a heading is
the pressure that keeps the library complete. Pay it once, then never again.

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

**The exception is a leaf with fixed anatomy.** When a component's insides are always
the same few pieces in the same order and nothing else may go in, the content is
props rather than children: `<Text content="…" />`, and
`<Button label="Save" icon="save" showIcon />`. That keeps every Button laid out
identically, and it means a consumer can't put a raw tag inside one. Containers
(Card, Dialog, Panel, Frame) still take children.

### Rule 4: Imports flow one way

```
app/  →  ui/pages/  →  ui/features/  →  ui/library/
```

- `app/` holds routes only. A route file renders a page component and nothing else.
- A **page** may import `ui/library`, `ui/features/`, and its own `features/`.
- A **feature** may import `ui/library`, `@/api`, and `@/store`. It must
  **never** import a page, or another page's features.
- `ui/library/` must **never** import from `ui/features/`, `ui/pages/`, `api/`, or
  `store/`. The library knows nothing about chat, workspaces or the API.
- Inside the library: a **component** may import primitives and other components,
  as long as there's **no cycle** (Dialog → Select → Dialog). A **primitive** imports
  no other library piece — that's what makes it a primitive.

**Barrel discipline:** consumers import from `@/ui/library`. Files *inside*
`ui/library/` always import the file directly
(`../../primitives/Text/Text`), never through the barrel — importing your own
barrel creates circular dependencies and makes every edit invalidate everything.

> Not yet enforced by tooling **[planned]**. Lint zones (`import/no-restricted-paths`)
> or `dependency-cruiser` can encode this graph in CI. Worth doing while there are
> zero violations to fix.

### Rule 5: Look and logic stay separate

- Library pieces in `ui/library/` contain **UI behaviour** only: open/close, hover,
  focus, keyboard.
- **App logic** (fetching, saving, business rules) lives in features, usually as
  hooks like `useChat()`, and is passed into components via props.

```tsx
// ui/pages/workspace/features/chat/Chat.tsx
<Button hierarchy="primary" label="Send" disabled={!chat.canSend} onClick={chat.send} />
```

### Rule 6: Where a style change goes

Four destinations, and picking the right one is most of what keeps this modular:

| Need                                | Goes in                                      |
|-------------------------------------|----------------------------------------------|
| Recurring, nameable intent          | a **named prop** — `hierarchy="primary"`     |
| A true one-off, with no good name   | the **consumer's own CSS**, scoped to it     |
| Different *behaviour* or semantics  | a **new component**                          |
| Whole-app art direction             | **the token files** (tier 2)                 |

- **Named props are data attributes, not new components.** `<Button hierarchy="primary">`
  renders `data-hierarchy="primary"`, styled in the component's own CSS. Never create
  `DangerButton`, `BigButton`, `GlowButton` — that way you get a combinatorial
  explosion where one token change has to be applied in nine places.
- **One-offs belong to their consumer.** Don't widen a prop's union for
  a single call site (`hierarchy="checkout-cta"` is not a hierarchy). The feature owns a
  class, in its own CSS file, next to the code that needs it:

```tsx
<Button hierarchy="primary" label="Send" className="chat-send" />
```
```css
/* Chat.css — one-off styling lives with the thing that needs it.
   Unlayered, so it beats Button.css without a fight. */
.chat-send { border-radius: var(--radius-full); }
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

- Durations and easings are tokens in `motion.css` (`--motion-fast`, `--ease-out`).
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
  internals (`data-part`) — use a named prop, or override at the component's root from
  the page's own unlayered CSS.
- A page holds no data fetching of its own. If a screen needs data, that belongs
  to one of its features.

### Rule 9: Keep `"use client"` as deep as possible

Every component is a **Server Component by default**. `"use client"` is required for
`useState`, `useEffect`, event handlers, or store access — and it is **contagious
downward**: everything a client component imports ships to the browser too.

- **Never put `"use client"` in `ui/library/index.ts`.** That ships the whole
  library to the client and silently disables server rendering everywhere. It
  produces no error, just a worse app.
- Mark the individual interactive component. Keep static primitives (`Text`, `Frame`,
  `Icon`, `Panel`) directive-free so they render on the server.
- Features are usually the client boundary; pages stay server components where they
  can. This matches Rule 8 — pages arrange (server), features behave (client).
- Never pass a function as a prop from a server component into a client one.

---

## 4. The component contract

### Props

```tsx
// ui/library/primitives/Panel/Panel.tsx (trimmed: the real one also takes elevation)
import type { ComponentProps, ElementType } from "react";
import type { Hierarchy } from "../../types/Types";
import "./Panel.css";

type PanelTag = "div" | "main" | "section" | "header" | "footer" | "button";

type PanelProps<T extends PanelTag> = ComponentProps<T> & {
  as?: T;
  hierarchy?: Hierarchy;
};

export function Panel<T extends PanelTag = "div">({ as, hierarchy = "secondary", ...rest }: PanelProps<T>) {
  const Tag = (as ?? "div") as ElementType;
  return <Tag {...rest} data-ui="panel" data-hierarchy={hierarchy} />;
}
```

- **Extend the native element** with `ComponentProps<T>` and spread `...rest`.
  You get `disabled`, `type`, `aria-*`, and every event handler for free, forever.
  Hand-listing props turns the component into a bottleneck needing a PR per attribute.
- **Props are camelCase**, like the native props they sit beside: `showIcon`,
  `iconAlign`, `defaultOpen` — never `show_icon`. (Values aren't props: an icon
  name like `icon="chevron_right"` is spelled however Material Symbols spells it.)
- **Use a shared union when one exists.** A `size` prop is `TextSize`, not a fresh
  `"sm" | "md" | "lg"`. Two components with different scales for the same idea is
  the drift this library exists to prevent.
- **`as` is generic over the allowed tags**, so `<Panel as="button">` accepts
  `type` and `disabled` while `<Panel as="section">` doesn't. Cast the resolved tag
  to `ElementType` (`(as ?? "div") as ElementType`); without the cast TypeScript
  narrows it and rejects the spread.
- **Spread `...rest` first, then the `data-*` attributes.** That way a stray prop
  can't overwrite a component's identity or its prop-driven attributes.
- **Name each prop after what it controls** — `hierarchy`, `elevation`,
  `direction` — never a generic `variant`. A `variant` bag ends up mixing unrelated
  properties (emphasis + surface + layout), and then combinations can't be
  expressed. Named props combine freely, one `data-*` attribute each.
- **Union types, not boolean flags.** `hierarchy?: "primary" | "secondary"`, never
  `primary?: boolean; secondary?: boolean` — the latter permits `<Button primary secondary />`.
- **No `forwardRef`.** On React 19 `ref` is an ordinary prop for function components.
- **Controlled/uncontrolled naming:** bare prop for controlled, `default*` for
  uncontrolled (`value`/`defaultValue`, `open`/`defaultOpen`), as the platform does.

### Styling attributes

| Attribute | Set by | Purpose |
|-----------|--------|---------|
| `data-ui` | every library piece | Identifies it: `panel`, `text`, `icon`, `frame` |
| `data-hierarchy`, `data-elevation`, `data-size` | props | Styled from the piece's own CSS |
| `data-direction`, `data-gap`, `data-align` | Frame's props | Layout |
| `data-icon-only` | Button | Derived state: icon shown, label hidden |
| `data-component` | a component | Marks the primitive root it owns (`data-component="button"`) |
| `data-part` | a component | Names an internal piece — **convention for later**, unused today |

Interaction state uses the native pseudo-classes (`:hover`, `:focus-visible`,
`:disabled`), not attributes. Add a `data-open` / `data-pressed` style attribute
only for state CSS can't see on its own.

`data-ui` and the prop attributes (`data-hierarchy`, …) are also the right selectors
in tests — stable, and independent of class names.

`data-part` is an **internal** naming convention. Consumers must not target it: the
moment outside CSS depends on a component's internal structure, that structure is
public API and the DOM can't be refactored. If an internal piece genuinely needs to be
stylable from outside, that is a signal it should be a slot the consumer passes in, or
its own component — not a custom property threaded through.

### Components built on a primitive root

When a component's root element *is* a primitive (Button's root is a Panel), the
root keeps the primitive's `data-ui`, so it still gets the primitive's styling. The
component marks it with `data-component="<name>"` and styles it from its own CSS,
qualified with both: `[data-ui="panel"][data-component="button"]`.

That selector is `(0,2,0)`, which beats the primitive's base rule. It ties with
the primitive's own prop rules (`[data-ui="panel"][data-hierarchy="primary"]`),
so **a component must not set a property the primitive's prop rules set.** Button
leaves background, border, colour and glass to Panel and adds only layout, padding,
cursor and interaction states. Its hover rules carry `:hover:not(:disabled)`, so they
outrank Panel's hierarchy rules by specificity, not source order.

### Writing the CSS

A component's CSS sets **real properties from semantic tokens**. No private
`--_vars`, no published hooks, no `var(a, b)`. Prop rules set the same
properties again:

```css
/* Panel.css */
@layer ui {
  [data-ui="panel"] {
    padding: var(--space-4);
    border: 1px solid transparent;
    border-radius: var(--radius-md);
    background: var(--color-surface);
    color: var(--color-text);
  }

  [data-ui="panel"][data-hierarchy="primary"] {
    background: var(--color-brand);
    color: var(--color-text-on-brand);
  }

  [data-ui="panel"][data-hierarchy="secondary"] {
    border-color: var(--color-border);
  }
}

/* Button.css — hover differs by hierarchy, so primary gets its own rule */
@layer ui {
  [data-ui="panel"][data-component="button"]:hover:not(:disabled) {
    background: var(--color-surface-raised);
  }

  /* Required. Without it, a hovered primary button loses its brand fill,
     because the shared :hover rule above is more specific than Panel's
     hierarchy rule. */
  [data-ui="panel"][data-component="button"][data-hierarchy="primary"]:hover:not(:disabled) {
    background: var(--color-brand-hover);
  }
}
```

**Two things make this work, and both are mechanical:**

1. **Always qualify with `data-ui`.** Write `[data-ui="panel"][data-hierarchy="primary"]`,
   never a bare `[data-hierarchy="primary"]`. Qualified, the prop rule is specificity
   `(0,2,0)` and beats the base rule's `(0,1,0)` outright. Bare, it ties with the base
   rule and the winner depends on source order — which breaks the moment someone
   reorders the file.
2. **Every prop value that differs on hover (or focus, or `:disabled`) needs its
   own state rule.** A shared `:hover:not(:disabled)` rule outranks any plain prop
   rule. This is the one real cost of dropping custom properties: a few
   extra rules instead of an indirection layer you maintain in every component. Forget
   one and the component visibly flashes the wrong colour on hover — a bug you see
   immediately rather than one that hides.

**When two props set the same property, write one rule per combination.**
Panel's `hierarchy` and `elevation` both affect `background`, so a floating primary
would otherwise depend on which rule comes later in the file. Instead each pair gets
an explicit rule qualified with both attributes, `(0,3,0)`, which beats either alone:

```css
[data-ui="panel"][data-hierarchy="primary"][data-elevation="floating"] {
  background: color-mix(in srgb, var(--color-brand) var(--glass-mix), transparent);
}
```

A few extra rules, but no private custom property and no source-order dependency.

**No `:where()`.** It contributed zero specificity so that a consumer's single class
could win — but `@layer ui` already guarantees that, since unlayered CSS beats layered
CSS regardless of specificity. Two mechanisms for one job, so we keep the one that
also lets normal specificity do the work above. Component selectors are plain.

### How a consumer overrides

One mechanism: **`@layer ui`.**

- Component CSS is inside `@layer ui`.
- Page and feature CSS is **unlayered**.
- Unlayered beats layered, always, regardless of specificity. So a single class in
  `Chat.css` overrides anything in `Button.css` or `Panel.css`, with no `!important` and nothing the
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
- **Components are where the work is.** `Dialog` needs a focus trap, scroll lock,
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

1. Can it be built from existing primitives or components? If yes, it's a component
   (`ui/library/components/`); otherwise a primitive.
2. Create the folder — two files, `Thing.tsx` and `Thing.css`. No `index.ts`.
3. Use the correct native element; add `"use client"` only if it holds state (Rule 9).
4. Extend `ComponentProps<...>` and spread `...rest`; give each named prop its own
   `data-*` attribute, set after the spread.
5. Style with semantic tokens inside `@layer ui`. Set real properties — **no
   `var(a, b)` fallback, no `--_private` vars, no published hooks** (Rule 1, §4).
   Raw values only for structural constants (Rule 1).
6. Qualify every selector with `data-ui`, and give each prop value its own `:hover` /
   `:focus-visible` / `:disabled` rule where it differs. Two props on one property
   get one rule per combination (§4).
7. Use motion tokens for any transition or animation.
8. Add a `:focus-visible` style if it's interactive.
9. Check it in both themes (flip `data-theme="dark"` on `:root` in devtools) — if
   it doesn't re-theme, it hardcoded a colour.
10. Export it from `ui/library/index.ts`, importing the file directly.

### Adding a page

1. Create `ui/pages/<route>/`, named after its route, with the page anatomy from §2.
2. Add the route in `src/app/` — it renders the page component and nothing else.
3. Break the screen into features. Anything with its own state or data calls is a
   feature, not page code.
4. Put page-only features in `ui/pages/<route>/features/`; reach for
   `ui/features/` only once a second page uses it, or one is already planned.
5. Build the layout from primitives and page-level CSS. **No raw HTML tags** —
   every element is a library component (Rule 2); if one is missing, build it first.
   No hex colours, no inline styles, no restyling component internals.

---

## 7. The modularity test

The structure is working if all of these are true:

- [ ] Changing `--color-brand` recolours the whole app.
- [ ] No library piece hardcodes a colour, spacing, radius or duration — only
      the structural constants Rule 1 allows are raw.
- [ ] `grep -r "var(--[a-z-]*," src/ui` finds nothing — no fallbacks anywhere.
- [ ] No component defines a custom property; it only reads semantic tokens.
- [ ] Every component is two files.
- [ ] Button can be fully redesigned without opening any file in `pages/` or `features/`.
- [ ] No file in `ui/library/` imports from `ui/features/`, `ui/pages/`, `api/` or `store/`.
- [ ] No raw HTML tag outside `ui/library/primitives/` —
      `grep -rnE "<(div|span|p|h[1-6]|button|a|ul|li|input|label|img|main|section|header)[ />]" src/ui/library/components src/ui/features src/ui/pages src/app`
      finds nothing.
- [ ] No CSS outside a component targets that component's `data-part` internals.
- [ ] No feature imports a page, or another page's features.
- [ ] A feature can be moved from one page's `features/` folder to `ui/features/`
      by changing imports only.
- [ ] `"use client"` appears on individual components, never on a barrel.
- [ ] Every file in `src/app/` is a thin route wrapper, not a screen, and each page
      folder is named after its route.
- [ ] No shared type has a value that does nothing on one of the components using it.
