# autodev

Orchestrator that turns tracker tickets (Notion) into verified pull requests using Claude agents. Project-agnostic by design: each target repo is described by a file in `projects/`.

First target: Acme (`projects/demo.yaml`).

## Setup

1. `cp .env.example .env` and fill in `NOTION_TOKEN` (an internal integration shared with the ticket database) and, for pull requests, `GITHUB_TOKEN`.
2. Create the ticket database in Notion with **exactly** the columns below (names are case-sensitive; rename any of them with `tracker.properties` in the project YAML, see [docs/CONFIG.md](docs/CONFIG.md)). Share the database with the integration.

| Column | Type | Filled by |
|---|---|---|
| Title | Title | you |
| Status | Status (options in `tracker.status_map`) | you / autodev |
| Type | Select | you |
| Area | Select (values match the project's `area_map`) | you |
| Priority | Select | you |
| Environment | Select | you |
| Page URL | URL | you |
| Reported by | Text | you |
| Attachments | Files | you |
| Authorized | Checkbox: autodev ignores tickets until it is ticked | you |
| Model | Select: `Auto` or a key of `model_choices` | you |
| Attempts | Number | autodev |
| Cost (USD) | Number | autodev |
| Risk | Select: `Low`, `Medium`, `High` | autodev |
| Branch | Text | autodev |
| PR | URL | autodev |
| Agent notes | Text | autodev |
| Verification result | Select | autodev |

   The ticket description is the page body; people answer questions as page comments.
3. Put the Notion `database_id` / `data_source_id` and the status labels in `projects/<name>.yaml`.
4. `uv run autodev check` verifies the connection and the columns.

## Dashboard and autonomy

`cd dashboard && npm install && npm run build`, then `uv run autodev serve` (127.0.0.1:8765, password set on first visit). From the top bar you choose how much autodev does alone:

| Mode | Behaviour |
|---|---|
| Auto | Triages authorized tickets, approves analysed ones whose risk is in `autonomy.auto_approve_risks`, then fixes them |
| Supervised | Triages and fixes by itself, but you approve the move to "In progress" |
| Manual | Nothing starts until you press Start on a ticket (default, `autonomy.default_mode`) |
| Paused | Nothing starts; "Stop all" interrupts running agents |

"My turn" holds the checkout: no agent starts while you work in it. One agent runs at a time. Tickets can be authorized, approved, retried, closed, given a model and commented on from the dashboard; every decision is logged as made by you or by the automatic mode. A ticket whose run failed is not retried automatically for `autonomy.retry_cooldown_seconds`.

### Talking to the agents

Runs started from the dashboard are interactive (runs started with `autodev triage|fix` in a terminal are not):
- **Message:** writing to a running agent interrupts what it is doing and gives it your text as the next turn, keeping its whole context. **Pause** interrupts and waits for your next message.
- **Permissions:** when an agent tries something outside its allowed commands, the run waits and the request shows up under "Da te" (allow once, allow for this run, or deny with a reason the agent reads). In Auto mode nobody is asked and the request is denied.
- **Checkpoints** (`autonomy.checkpoints`, not applied in Auto): `after_agent` waits after the agent says it is done and before the verification gate; `before_pr` waits after verification and before the push and the pull request. Rejecting escalates the ticket.
- Finished runs cannot be resumed with a chat yet.

### Repo and pull requests

- **Repo:** the checkout's state, the agent branches with a file-by-file diff, "Try" (switch to a branch to test it with Docker), "Back to <base>", and **Run the checks** (the project's `checks` as a tracked run). Switching branches and deleting are refused while an agent works or when the tree is dirty.
- **Pull request:** autodev's PRs with GitHub check status, the ticket's risk and verification, and the PR description with the evidence. **Merge** (squash) needs a second click and is refused for drafts, failing or pending checks, conflicts and Alto risk; a merge closes the ticket and deletes the remote branch.
- Branches whose PR was merged (even squashed) count as merged. `uv run autodev cleanup [--dry-run] [--remote] [--workspaces]` deletes them from the terminal; unmerged branches are never removed.

### Running unattended

- **Quiet hours** (`autonomy.quiet_hours: "22:00-07:00"`, editable in Settings): nothing starts by itself in that window; a manual Start still works.
- **Notifications:** a desktop notification (via `notify-send`, or `autonomy.notify_command` with `{title}` and `{body}`) when a request or checkpoint waits for you, a run finishes or fails, the daily cap is reached or a PR is merged. The browser tab title shows the number of pending requests, and optional browser notifications work while the tab is open in the background.
- **Housekeeping:** every polling round a merged PR closes its ticket and a PR closed unmerged escalates it (`autonomy.auto_cleanup_branches: true` also deletes the merged local branch).
- **Several projects:** `uv run autodev serve` serves every file in `projects/` (or the ones named with `--project`, repeatable). A project switcher appears in the sidebar; mode, daily cap, quiet hours, runs and costs are per project, and each project's agent works on its own checkout.

## Layout

```
src/autodev/   orchestrator (trackers, agents, sandbox, pipeline, github, report)
e2e/           black-box Playwright suites, one folder per project
projects/      per-project configuration
docs/          design notes, Notion schema
```

## Roadmap

1. Notion integration + triage agent (read-only on code, comments on the ticket)
2. Fix agent in an isolated git worktree, opens PR against the base branch
3. Playwright verification on local/staging, review agent
4. Auto-merge for low-risk classes

See [docs/NOTION_SCHEMA.md](docs/NOTION_SCHEMA.md) for the ticket database and state machine.
