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
| Risk | Select: `Basso`, `Medio`, `Alto` | autodev |
| Branch | Text | autodev |
| PR | URL | autodev |
| Agent notes | Text | autodev |
| Verification result | Select | autodev |

   The ticket description is the page body; people answer questions as page comments.
3. Put the Notion `database_id` / `data_source_id` and the status labels in `projects/<name>.yaml`.
4. `uv run autodev check` verifies the connection and the columns.

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
