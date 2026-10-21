# Dashboard plan

Goal: one place to see everything autodev does, decide how much it does alone, step in at any
moment, and talk to the agents it spawns. Local-first: it runs on the same machine as the repo,
Docker and the Claude Code login, so it is a local web app, not a hosted service.

## Principles
- **Notion stays the ticket source of truth.** The dashboard reads and writes it; it does not
  replace it. Everything the dashboard stores itself (runs, events, chat, costs) is in local SQLite.
- **Every automatic action can become a manual one.** Autonomy is a setting, not a code path.
- **One writer per checkout.** In-place mode means one agent at a time may touch `demo/`; the
  dashboard shows who holds it, and lets you take it ("my turn") so automation waits.
- **Nothing the agents read is trusted.** Ticket text and comments are rendered as plain text.

## Autonomy levels
Set globally, per stage (triage / fix / PR), and overridable per ticket.

| Level | Behaviour |
|---|---|
| **Auto** | Picks tickets up by itself, runs, opens the PR. You are notified of the result. |
| **Supervised** | Runs by itself but stops at checkpoints and waits for your approval (below). |
| **Manual** | Nothing starts until you press Start. |
| **Paused** | Nothing starts, running jobs finish. A **Stop all** button kills running agents. |

Checkpoints (each can be switched on or off): after triage (go / no go, today the move to
"In lavorazione"), agent's plan before it edits, before the commit, before the PR is opened,
and every time the agent asks for a permission it does not already have.

## Screens
```
┌──────────────────────────────────────────────────────────────────────────────┐
│ autodev   mode: [Auto|Supervised|Manual|Paused]   today $4.2/$20   ● 1 agent   │
├───────────┬──────────────────────────────────────────────────────────────────┤
│ Inbox  3  │  Ticket board (Notion states as columns, drag to change state)    │
│ Tickets   │  Nuovo | Serve info | Analizzato | In lavorazione | Da rivedere   │
│ Live      │                                                                    │
│ Repo      │  ── ticket detail ──────────────────────────────────────────────  │
│ PRs       │  description · comments · triage analysis · runs · cost · PR       │
│ Costs     │  [Authorize] [Model: Auto▾] [Triage] [Fix] [Retry] [Reset attempts]│
│ Settings  │  [Comment to Notion] [Close]                                       │
└───────────┴──────────────────────────────────────────────────────────────────┘
```
1. **Inbox**: only what needs you: approvals, "Serve info" answers, "Da rivedere", escalations,
   budget alerts. Desktop notification when something lands here.
2. **Tickets**: board and detail as above. Every Notion column editable (Autorizzato, Modello,
   Stato, Tentativi). Comment box writes to the ticket.
3. **Live**: the running agent: action stream (files read, searches, edits, test runs), the diff
   growing, test output, cost ticking, elapsed time. Buttons: **Pause**, **Stop**, **Take over**.
4. **Chat with an agent**: send a message to a running agent ("also handle X", "stop, that file is
   wrong") or to a finished one (resume its session with context). Approve or deny its permission
   requests inline.
5. **Repo**: checkout state (branch, dirty files), who holds the lock, branches `autodev/*`,
   diff viewer, buttons to run pytest / vitest / tsc, safe "back to staging", delete merged branches.
6. **PRs**: PRs opened by autodev with status and the verification evidence; open on GitHub, later merge.
7. **Costs**: per ticket, model, day; the per-ticket and daily caps editable here.
8. **Settings**: project YAML (models, limits, allowed commands, risk paths, area map), schedule and
   quiet hours, notification rules.

## Talking to the agents (the part that changes the architecture)
Today agents run as one-shot `query()` calls: they cannot be spoken to once started. The SDK has
`ClaudeSDKClient` (multi-turn session, `interrupt()`) and a `can_use_tool` callback (permission
prompt), which is what the dashboard needs. So a run becomes a **controllable session**:
- a message queue per run: your chat messages are injected as the next user turn;
- `interrupt()` for Pause/Stop, session id stored so a stopped run can be resumed with its context;
- `can_use_tool` routed to the Inbox in Supervised mode, auto-answered from the allowlist in Auto mode;
- checkpoints are just "wait for approval event" between pipeline steps.

## Architecture
- **`autodev serve`**: one Python process: FastAPI + the orchestrator loop (this replaces the
  planned `autodev run`). Bound to `127.0.0.1` only, with a local token, because it can run
  commands and spend quota.
- **State**: SQLite (`runs`, `events`, `messages`, `approvals`, `settings`). Events are append-only
  and drive both the live view and the audit trail ("who decided this: you or Auto").
- **Live updates**: Server-Sent Events from the event stream; commands over REST.
- **Frontend**: React + Tailwind + shadcn (same family as Acme), built to static files and served
  by the same FastAPI process: one port, one command, no Node at runtime.
- **Existing pieces kept**: tracker, pipeline, gate, workspace. The CLI keeps working on top of the
  same job layer.

## Phases
| Phase | Delivers | Why this order |
|---|---|---|
| **0 Foundation** | Job layer with states (queued, running, waiting, done, failed), event log in SQLite, cancel/pause, spend caps (per ticket and daily) | Everything else sits on it |
| **1 Read-only dashboard** | Tickets, runs, live stream, costs, repo state | Useful immediately, no risk |
| **2 Controls** | Autonomy levels, Start/Stop/Retry/approve, Notion field editing, comment box, "my turn" lock | You stop using Notion and the terminal for routine operations |
| **3 Interactive agents** | ClaudeSDKClient sessions, chat, interrupt, permission prompts, checkpoints | The part you asked for most |
| **4 Repo and PRs** | Diff viewer, run checks, branch cleanup, PR list, merge | Closes the loop |
| **5 Automation polish** | Schedule and quiet hours, notifications, auto-close on merge, multi-project switcher | Generalisation |

## Risks to handle
- A dashboard that can run agents is a remote-control surface: localhost only, token, no CORS to the world.
- Two writers on `demo/`: the lock and the clean-tree check stay the source of safety.
- Live sessions are memory-resident: if the process restarts, running sessions are resumed from the
  stored session id, never silently lost.
- Cost: Supervised and chat sessions can run long; the caps apply per ticket and per day regardless of mode.

## Open decisions
1. Frontend stack (React/Vite recommended) vs server-rendered pages (less code, less interactive).
2. Local only, or reachable from the phone (needs a tunnel and real authentication).
3. Which phase first. Recommended: 0 then 1, so you can watch it before you steer it.
