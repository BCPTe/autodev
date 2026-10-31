# Backlog

Ordered by what unblocks the most. Done items live in git history, not here.

## Next
0. **Dashboard** ([DASHBOARD_PLAN.md](DASHBOARD_PLAN.md)): all five phases done. Left over: chat with finished runs (resume session); agent plan checkpoint before edits; browser tests for the dashboard (`e2e/autodev`, on `demo_server.py`); GitHub features (PR list, merge, housekeeping) and `notify-send` untested against the real services; Windows/macOS notifiers need a custom `notify_command`.
1. **Pull requests.** (enabled; first real PR pending) `GITHUB_TOKEN` in `.env`, `pr.create: true`, state `In review` links the PR. Replaces the manual merge into `staging`. Includes updating an already open PR when a ticket is re-run (done in `github.py`, untested against the real API).
2. **`autodev run`.** Polling loop (triage then fix) with a lock, a **daily spend cap** (the per-ticket cap of $6 exists, the daily one does not), quiet hours, and a `systemd --user` service.
3. **Merge conflicts resolved by the agent.** When the base branch moved and merging it into the ticket branch conflicts (as happened on `scia_sue_calabria_fields.json`), hand both versions to the fix agent in the same run instead of stopping.

## Learning loop (phase 1 done: playbook file, injection, retrospective proposals, Learnings page, usage and per-area metrics)
- **Phase 2: selective retrieval.** Today the playbook is filtered by Area and by paths mentioned in the ticket or the triage analysis, then by recency, within `knowledge.max_chars`. Next: rank by the files the triage actually suspects (re-select for the fix prompt from `suspected_files`), by usage and citation counts (already recorded in `playbook_usage`), and bring in similar past tickets (title/area/files) with what was decided on them. Also let the fix agent cite entries so `cited` is measured for fixes too (only triage cites today).
- **Phase 3: pruning and consolidation.** Merge near-duplicate entries, flag entries whose paths vanished from the checkout or that were never used or cited for N runs, decay them, and propose a consolidated rewrite when the playbook nears `max_chars` (still human-reviewed). Compare the per-area metrics before and after an entry was accepted to see which ones help.
- Untested against the real services: the retrospective with the real Claude API, `git diff --stat` on a real merged/deleted branch, and the auto trigger from a real GitHub merge.

## Later
4. **CI on GitHub for the target repo** (pytest, vitest, tsc on every PR) so PRs carry checks that do not depend on the agent.
6. **Notion views.** Inbox (New + Authorized), In review, Needs info, Closed.
7. **Automatic UI check.** With in-place mode the Docker stack already serves the ticket branch, so Playwright (an end-to-end suite in the target repo) can run against `localhost:3000` as part of verification for changes that touch the frontend.
8. **Model column for triage.** Today the "Model" column only drives the fix agent; triage always cascades Haiku -> Sonnet.
9. **Mutation testing as a tool.** Move the AST mutation sampler used for the test audit into this repo and run it on demand per module.
10. **Triage should recognise duplicates** (the old "Duplicato" state was dropped because nothing could set it).
