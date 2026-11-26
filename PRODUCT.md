# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Students and researchers digging into a research question over a long session: reading papers and
sources, asking follow-ups, and chasing side questions without losing the main thread. They come back to
the same case across sessions.

## Product Purpose

Tangent is an AI research workspace that turns a conversation into a case board. Every question is a case;
every follow-up is a lead pinned under the one it came from, so a person can branch into any tangent,
explore it fully in its own thread, and find their way back. Success is a researcher who follows every lead
they care about and can still see, and return to, the whole line of thought.

## Positioning

The map and the assistant, equally. Visual idea lineage: every prompt, answer and branch is kept as a board
you can navigate and reshape, instead of a chat history you scroll and lose. Gent, the built-in assistant,
does the legwork that fills the board in: he opens leads, asks the cards, and reads sources while the user
steers the case.

## Operating Context

- A desktop browser, for hours at a time: the case board in the middle, the case notes sheet on the right,
  the rail on the left, Gent's dock at the bottom.
- Workflows: start a case, branch from any reply, jump between cards, attach and read PDF sources, let Gent
  run a task, take a question to debate mode (the courtroom) for a verdict, share a case by invite.
- Workspaces hold cases; a case is a tree of cards with their own threads.

## Capabilities and Constraints

- Streaming chat per card with model choice; branching from any reply; split, join, compact, resolve and tag
  cards; context assembled from the card's ancestor path.
- Gent: an agent with near user-level tools over the board, guarded by limits.
- Debate mode: two sides argue a proposition, a judge rules, and the ruling proposes next branches.
- Sources: uploaded PDFs and Semantic Scholar papers the research tools can read.
- Sharing by email invitation; a sharee's first write forks their own copy.
- Google sign-in only.
- Terminology: case, lead, card, exhibit number (1, 1.2, 1.2.1), Field Notes (Gent's list), courtroom words in
  debate mode.
- Undecided: real case numbers for the case badge (the backend has none yet).

## Brand Commitments

- The name is Tangent: one word, capital T.
- The look and voice are set by the Tangent design system (docs/VISUAL_LANGUAGE.md, docs/DESIGN.md): a
  detective's case board; red means the user's path, blue means Gent; detective words for the board and Gent,
  courtroom words for debate mode; plain sentences, no exclamation marks.
- Gent is a drop of ink in a detective's hat and has no other mascot form.

## Evidence on Hand

An ACM student project, demoed but not publicly launched. There are no users, testimonials, metrics, press or
pricing to cite: future work must not invent any.

## Product Principles

- Never lose the thread: every branch stays on the board and every path leads back.
- The user steers; Gent does the legwork, visibly and in his own ink.
- Long reading wins: texture and character live around the words, never in them.
- Say what the product does today, plainly; claim nothing it can't show.
