# autodev

Orchestrator that turns tracker tickets (Notion) into verified pull requests using Claude agents. Project-agnostic by design: each target repo is described by a file in `projects/`.

First target: Acme (`projects/demo.yaml`).

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
