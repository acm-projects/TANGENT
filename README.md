<p align="center">
  <img src="https://media.tenor.com/B1KlQs7e3R4AAAAM/see-you-again-paul-walker.gif" alt="See You Again" width="480"/>
</p>

<!-- Drop the Tangent logo at ./assets/tangent-logo.png, then uncomment this block:
<p align="center">
  <img src="./assets/tangent-logo.png" alt="Tangent" width="400"/>
</p>
-->

<h1 align="center">🌳 TANGENT 🌳</h1>

<p align="center">
Most AI chat tools are built like a straight line: you ask, you get an answer, you keep scrolling. But real thinking branches. You chase a side question, then want to come back to where you were without losing your place. Tangent is an AI brainstorming workspace that turns a conversation into a live, visual mind map. Start with one idea, branch into a tangent whenever a thought pulls at you, explore it fully in its own thread, then snap back to the main line, and the whole tree renders as an interactive map you can navigate and export.
</p>

<p align="center">
<b>The differentiator is visual idea lineage.</b> Every prompt, response, and branch becomes part of a map you can revisit and reshape, instead of a wall of chat history you scroll and lose.
</p>

---

## MVP ✅
* **Standard Chat Interface** → Model selection and streamed responses
* **Start a Tangent** → Branch from any message to fork a child thread from that exact point
* **Live Mind Map** → Every node is a branch, rendered alongside the chat, click any node to jump into it
* **Breadcrumb Trail** → Always shows the current path (Main → Tangent 1 → Tangent 1.1)
* **Return to Main** → Jump back at any time without losing context in any branch
* **Tree Storage Model** → Each node stores its own messages plus a parent pointer and a fork index
* **Context Reconstruction** → Walks the ancestor path, assembled in a prompt-caching-friendly order
* **Prompt Coach** → Collapsible "improve this prompt" panel with 2-3 suggestions, generated on demand
* **Battle Mode** → Fork a "for" branch and an "against" branch, develop each across multiple turns, then a Battle button adjudicates between them
* **Usage Tracking** → Tokens, cost, and model recorded per message
* **Session Saving** → User authentication and persistent sessions
* **Export** → Mind map as a PNG or a shareable read-only link

---

## Stretch Goals 💪
* **Real-Time Collaboration** → Multiple people exploring and branching on one shared tree
* **Synthesize** → Select two or more branches and merge their strongest ideas into one new node
* **Best Next Tangent** → The model proposes unexplored branches worth taking
* **Map Intelligence** → Automatic clustering and color-coding of related branches by topic
* **Semantic Search** → Search across every past node using **pgvector**
* **Prompt Scoring** → Track prompt quality over time and generate a personal prompting-style report
* **Multi-Model Comparison** → Run one prompt across models and diff the answers *(deliberately deprioritized: cross-model switching defeats prompt caching)*
* **Platform** → Templates, file uploads, third-party integrations, full analytics dashboard

---

## How It Works 🧠

Tangent is a chat app where the conversation is a tree instead of one long list.

* **Every branch is a row in the database** that remembers which branch it came from.
* **Each branch also records how far along the conversation was when it split off,** and that number never changes afterwards.
* **Rebuilding a branch's history** means following the chain of parents back and taking only the messages that existed when each split happened.
* **Branches stay apart on their own:** two made from the same point never see each other's messages.
* **Running costs stay low** because providers charge far less for history they have already read, and every branch shares most of its history with its parent.

### ⚠️ If this part is wrong, nothing crashes

* **The app keeps working,** which is exactly what makes it dangerous.
* **Answers look completely normal,** except the AI was handed a history that never happened on that branch.
* **Nobody catches it by looking,** so it surfaces weeks later once the mind map and Battle mode are sitting on top of it.
* **So this gets built and tested first,** before any of the visual work starts.

### What gets built on top

The tree and the history rebuilding are the foundation. Agentic features are layered on top of it, where the model works the tree itself rather than one message at a time, proposing tangents worth taking and developing several branches in parallel. The same structure suits research, where separate angles stay in separate branches until Battle mode settles the ones that genuinely conflict.

---

## Tech Stack & Resources
#### React + TypeScript • Tailwind • React Flow • Zustand • FastAPI • PostgreSQL • Gemini API

<details>
<summary>Frontend</summary>

* [React + TypeScript Docs](https://react.dev/learn/typescript)
* [Vite Getting Started](https://vitejs.dev/guide/)
* [Tailwind CSS Installation](https://tailwindcss.com/docs/installation/using-vite)
* [Zustand Docs](https://zustand.docs.pmnd.rs/) · [Zustand GitHub](https://github.com/pmndrs/zustand)
* [TipTap - React Install](https://tiptap.dev/docs/editor/getting-started/install/react) *(optional, a plain textarea is a fine fallback)*
* [assistant-ui](https://github.com/assistant-ui/assistant-ui) *(prebuilt chat components, evaluate in Week 1)*
* [VIDEO: TypeScript in React - Complete Crash Course](https://www.youtube.com/watch?v=TPACABQTHvM)
* [VIDEO: Tailwind CSS Full Course - Master Tailwind in One Hour](https://www.youtube.com/watch?v=6biMWgD6_JY)
* [VIDEO: Zustand Beginner Tutorial - React State Management](https://www.youtube.com/watch?v=-Y8brhQKvtA)
* [VIDEO: Tiptap Editor for React - Advanced Quick Start](https://www.youtube.com/watch?v=s1lpwpeSGW4)

</details>

<details>
<summary>Mind Map (React Flow)</summary>

* [React Flow Quick Start](https://reactflow.dev/learn)
* [Building a Flow - Core Concepts](https://reactflow.dev/learn/concepts/building-a-flow)
* [VIDEO: React Flow Crash Course - Build Your First Flow Editor](https://www.youtube.com/watch?v=f6kj_GLM_9A)

> Derive node layout from the tree structure rather than storing an x/y position on every node. Storing positions creates a second source of truth that drifts out of sync with the real tree. Keep custom node components memoized; React Flow already virtualizes rendering.

</details>

<details>
<summary>Backend</summary>

* [FastAPI Full Tutorial](https://fastapi.tiangolo.com/tutorial/)
* [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)
* [Pydantic Docs](https://docs.pydantic.dev/latest/)
* [SQLAlchemy ORM Quickstart](https://docs.sqlalchemy.org/en/20/orm/quickstart.html)
* [Alembic Migrations Tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
* [pytest Docs](https://docs.pytest.org/en/stable/)
* [VIDEO: FastAPI Crash Course - Modern Python API Development](https://www.youtube.com/watch?v=8TMQcRcBnW8)
* [VIDEO: How WebSockets Work - Build a Chat with FastAPI](https://www.youtube.com/watch?v=jQMl8E9hUp8)
* [VIDEO: FastAPI & Alembic - Database Migrations](https://www.youtube.com/watch?v=zTSmvUVbk8M)

</details>

<details>
<summary>Database</summary>

* [PostgreSQL Getting Started](https://www.postgresqltutorial.com/postgresql-getting-started/)
* [Recursive CTE Queries](https://www.postgresqltutorial.com/postgresql-tutorial/postgresql-recursive-query/) ← **the query that walks the tree**
* [JSONB in Postgres](https://www.postgresql.org/docs/current/datatype-json.html)
* [pgvector](https://github.com/pgvector/pgvector) *(stretch goal only)*
* [VIDEO: PostgreSQL Tutorial for Beginners](https://www.youtube.com/watch?v=SpfIwlAYaKk)
* [VIDEO: Recursive SQL Queries Tutorial](https://www.youtube.com/watch?v=7hZYh9qXxe4)

> **Do not use a graph database for this.** At club scale the adjacency-list model in Postgres is simpler, faster to build, and entirely sufficient. Neo4j only becomes worth discussing at scales this project will not reach.

</details>

<details>
<summary>AI / Model Layer</summary>

* [Gemini API Quickstart](https://ai.google.dev/gemini-api/docs/quickstart) ← **primary recommendation for v1**
* [Gemini Free Tier Rate Limits](https://ai.google.dev/gemini-api/docs/rate-limits)
* [Gemini Context Caching](https://ai.google.dev/gemini-api/docs/caching) *(implicit caching is on by default for 2.5+ models, zero code required)*
* [Anthropic API Getting Started](https://docs.anthropic.com/en/api/getting-started)
* [Anthropic Prompt Caching](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching) *(explicit, via a `cache_control` marker)*
* [Ollama - run models locally](https://github.com/ollama/ollama) *(for development, so debugging the tree walk costs nothing)*
* [VIDEO: How to Use the Gemini API in Python](https://www.youtube.com/watch?v=3CW_mr00xYM)
* [VIDEO: Gemini API with Python - Getting Started](https://www.youtube.com/watch?v=qfWpPEgea2A)
* [VIDEO: Learn Ollama in 15 Minutes - Run Models Locally for Free](https://www.youtube.com/watch?v=UtSSMs6ObqY)

**Rules the whole team needs to know:**
1. Call one provider's SDK directly. No router (LiteLLM, OpenRouter) in v1, it is a moving part we do not need yet.
2. Tie model choice to the **branch**, not the message. Switching models mid-branch forces a cold, full-price re-read of the entire ancestor path.
3. Log the cache-hit rate from day one. Gemini reports it in `usage_metadata`, Anthropic in the `usage` object. If it drops, something is poisoning the prefix, find it immediately.
4. Run the Prompt Coach on the cheap model, send it only the user's prompt (never the conversation), cap output around 200 tokens of structured JSON, and fire it only when the panel is expanded.
5. Keep the provider base URL and model name as a single config value from day one, so swapping between Ollama and the real API is free.

</details>

<details>
<summary>Auth</summary>

* [Better Auth Docs](https://www.better-auth.com/docs/introduction)
* [Supabase Auth](https://supabase.com/docs/guides/getting-started)
* [VIDEO: FastAPI JWT Tutorial - How to Add User Authentication](https://www.youtube.com/watch?v=0A_GCXBCNUQ)

</details>

<details>
<summary>Deployment</summary>

All of these have free or hobby tiers appropriate for a club project, and none require managing servers.

* [Vercel - frontend hosting](https://vercel.com/docs/getting-started-with-vercel)
* [Render - deploying FastAPI](https://render.com/docs/deploy-fastapi)
* [Railway - backend alternative](https://docs.railway.com/quick-start)
* [Neon - serverless Postgres](https://neon.com/docs/get-started-with-neon/signing-up)
* [Supabase - Postgres alternative](https://supabase.com/docs/guides/getting-started)
* [VIDEO: Deploy a FastAPI App on Render for Free](https://www.youtube.com/watch?v=stDadw38H0I)
* [VIDEO: How to Create a PostgreSQL Database on Neon](https://www.youtube.com/watch?v=doIFdMp7D2E)

</details>

<details>
<summary>Keeping It Free</summary>

The goal is to build and demo this at or near zero cost. That is achievable, but only on purpose.

* **Develop against Ollama, demo against Gemini.** Hundreds of calls go into debugging the tree walk, where output quality barely matters. Save the real API for the parts that get judged.
* **Test Battle mode on the real model early.** Small local models (7-8B) often produce mushy, near-identical output for both sides, which would undercut the headline feature. Find that out in Week 8, not Week 10.
* **Do not run a local model live during the presentation.** Thermal throttling in front of the room is a real risk. Demo on the hosted API.
* **Gemini's free tier covers development comfortably.** Check the rate limits link above before assuming a load test will fit.
* **Set a spend cap on the account before the first week of heavy testing**, and use separate keys for development and the demo.
* **Prompt caching is the main cost lever**, and it is free to implement. It is also silent when it breaks, which is why the cache-hit rate gets logged from day one.
* **Route by task.** The Prompt Coach and any summarization run on the cheapest model available. Reserve the expensive model for answers the user actually wants to be heavyweight.

</details>

<details>
<summary>Design</summary>

* [Figma](https://www.figma.com/)
* [VIDEO: Figma Tutorial for Beginners](https://www.youtube.com/watch?v=ezldKx-jPag)

</details>

<details>
<summary>Dev Tools</summary>

* **Node.js (LTS) + pnpm** — frontend runtime
Download: [Node.js LTS](https://nodejs.org/en/download)
Tutorial: [VIDEO: How to Download and Install Node.js](https://www.youtube.com/watch?v=4FAtFwKVhn0)

* **Python 3.11+ with virtualenv** — backend runtime
Download: [Python](https://www.python.org/downloads/)
Tutorial: [VIDEO: Python Virtual Environments - Full Tutorial](https://www.youtube.com/watch?v=Y21OR1OPC9A)

* **PostgreSQL 16** — locally, or a free Neon branch
Download: [PostgreSQL](https://www.postgresql.org/download/)
Tutorial: [VIDEO: PostgreSQL Tutorial for Beginners](https://www.youtube.com/watch?v=SpfIwlAYaKk)

* **Docker Desktop** — run Postgres locally without polluting your machine
Download: [Docker](https://docs.docker.com/get-started/get-docker/)
Tutorial: [VIDEO: Docker Crash Course for Absolute Beginners](https://www.youtube.com/watch?v=pg19Z8LL06w)

* **Git + GitHub**
Download: [Git](https://git-scm.com/downloads)
Tutorial: [VIDEO: Git and GitHub for Beginners - Crash Course](https://www.youtube.com/watch?v=RGOj5yH7evk)

* **VS Code** — editor
Download: [Visual Studio Code](https://code.visualstudio.com/download)

* **Postman** — API testing
Download: [Postman](https://www.postman.com/downloads/)

* **DBeaver** — look at the database with your own eyes
Download: [DBeaver](https://dbeaver.io/download/)

* **API keys** — [Google AI Studio](https://aistudio.google.com/) (Gemini) or [Anthropic Console](https://console.anthropic.com/)
API access and billing are separate from any consumer chat subscription. A Pro plan does **not** grant API credits. Store keys in a gitignored `.env` file, never in source control.

</details>

<details>
<summary>Week 1 Learning Path (watch in this order)</summary>

1. [Git and GitHub for Beginners](https://www.youtube.com/watch?v=RGOj5yH7evk)
2. [TypeScript in React - Crash Course](https://www.youtube.com/watch?v=TPACABQTHvM)
3. [React Flow Crash Course](https://www.youtube.com/watch?v=f6kj_GLM_9A)
4. [Zustand Beginner Tutorial](https://www.youtube.com/watch?v=-Y8brhQKvtA)
5. [FastAPI Crash Course](https://www.youtube.com/watch?v=8TMQcRcBnW8)
6. [FastAPI WebSockets](https://www.youtube.com/watch?v=jQMl8E9hUp8)
7. [Postgres Recursive Queries](https://www.postgresqltutorial.com/postgresql-tutorial/postgresql-recursive-query/)

</details>

---

## Roadmap 📅

<table>
  <tr>
    <th>Week</th>
    <th>Frontend</th>
    <th>Backend</th>
  </tr>
  <tr>
    <td align="center"><b>1</b></td>
    <td colspan="2">Everyone: plan the project, walk through how it works, get the tools installed on every machine, and work through the tutorials. Agree on paper how a conversation tree will be stored before anyone writes code. The goal this week is a written plan and an empty project, not features.</td>
  </tr>
  <tr>
    <td align="center"><b>2</b></td>
    <td>Set up the React project. Build the chat screen: a list of messages and a box to type in. No real answers yet.</td>
    <td>Set up the server and the database. Create tables for users, sessions, and branches. Build a basic chat endpoint that can talk to the AI.</td>
  </tr>
  <tr>
    <td align="center"><b>3</b></td>
    <td>Connect the chat screen to the server so answers appear word by word as they arrive. Add a list of saved conversations.</td>
    <td>Send the AI's answers to the browser as they come in. Save every message to the database as it is written, not just at the end.</td>
  </tr>
  <tr>
    <td align="center"><b>4</b></td>
    <td>Add a "Start a Tangent" button to each message, and a trail across the top showing where you currently are in the tree.</td>
    <td>Build the branching. When a branch is made, record which branch it came from and how far along the conversation was. Then build the part that rebuilds a branch's history, and test it properly. <b>This is the riskiest work in the whole project.</b></td>
  </tr>
  <tr>
    <td align="center"><b>5</b></td>
    <td>Draw the mind map next to the chat. Colour the branches, and make clicking a node jump you into that branch.</td>
    <td>Make sure the conversation history is sent to the AI the same way every time, so the cost stays low. Record how many tokens each message used.</td>
  </tr>
  <tr>
    <td align="center"><b>6</b></td>
    <td>Polish the map: highlight the branch you are on, add zoom and drag, and keep the map and the chat in step with each other. Show token usage on screen.</td>
    <td>Check the cost savings are actually happening by logging them, before anything else gets built on top.</td>
  </tr>
  <tr>
    <td align="center"><b>7</b></td>
    <td>Build the Prompt Coach panel. Closed by default, and when opened it shows two or three ways to improve the question.</td>
    <td>Build the Coach behind it. Use the cheapest model, send it only the user's question rather than the whole conversation, and keep the reply short.</td>
  </tr>
  <tr>
    <td align="center"><b>8</b></td>
    <td>Build Battle mode: the two-sided split, the two cases shown side by side, the Battle button, and the verdict screen.</td>
    <td>Collect each side's argument, send both to the AI to judge between them, and save the verdict as a new branch.</td>
  </tr>
  <tr>
    <td align="center"><b>9</b></td>
    <td>Export the map as an image and a shareable link. Handle the empty, loading, and error screens. Make it work in smaller windows.</td>
    <td>Build the share links and view-only access. Add limits so nobody can accidentally run up a bill.</td>
  </tr>
  <tr>
    <td align="center"><b>10</b></td>
    <td colspan="2" align="center">✨ Everyone: stop adding features. Practise the demo, fix only what breaks the demo, and prepare the presentation. ✨</td>
  </tr>
</table>

---

## GitHub Cheat Sheet 💬

| Command | Description |
| ------ | ------ |
| **cd "directory"** | Change directories over to our repository |
| **git branch** | Lists branches for you |
| **git branch "branch name"** | Makes new branch |
| **git checkout "branch name"** | Switch to branch |
| **git checkout -b "branch name"** | Same as 2 previous commands together |
| **git add .** | Finds all changed files |
| **git commit -m "Testing123"** | Commit with message |
| **git push origin "branch"** | Push to branch |
| **git pull origin "branch"** | Pull updates from a specific branch |
| get commit hash (find on github or in terminal run **git log --oneline**) then **git revert 2f5451f --no-edit** | Undo a commit that has been pushed |
| **git reset --soft HEAD~** | Undo commit (not pushed) but *keep* the changes |
| get commit hash then **git reset --hard 2f5451f** | Undo commit (not pushed) and *remove* changes |

---

## The Team 🎉

<div align="center">
<h2>🎊 Developers 🎊</h2>
<h3>Prakrit Chauhan</h3>
<h3>Ryan Strobel</h3>
<h3>Tejas Katira</h3>
<h3>Yafi Rahman</h3>
<h2>🎊 Project Manager 🎊</h2>
<h3>Akilan Chithra Sathish</h3>
<h2>🎊 Industry Mentor 🎊</h2>
<h3>Sam Stegall</h3>
</div>
