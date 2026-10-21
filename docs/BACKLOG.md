# Backlog

Ordered by what unblocks the most. Done items live in git history, not here.

## Next
0. **Dashboard** ([DASHBOARD_PLAN.md](DASHBOARD_PLAN.md)): all five phases done. Left over: chat with finished runs (resume session); agent plan checkpoint before edits; browser tests for the dashboard (`e2e/autodev`, on `demo_server.py`); GitHub features (PR list, merge, housekeeping) and `notify-send` untested against the real services; Windows/macOS notifiers need a custom `notify_command`.
1. **Pull requests.** (enabled; first real PR pending) `GITHUB_TOKEN` in `.env`, `pr.create: true`, state `Da rivedere` links the PR. Replaces the manual merge into `staging`. Includes updating an already open PR when a ticket is re-run (done in `github.py`, untested against the real API).
2. **`autodev run`.** Polling loop (triage then fix) with a lock, a **daily spend cap** (the per-ticket cap of $6 exists, the daily one does not), quiet hours, and a `systemd --user` service.
3. **Merge conflicts resolved by the agent.** When the base branch moved and merging it into the ticket branch conflicts (as happened on `scia_sue_calabria_fields.json`), hand both versions to the fix agent in the same run instead of stopping.

## Later
4. **CI on GitHub for demo** (pytest, vitest, tsc on every PR) so PRs carry checks that do not depend on the agent.
6. **Notion views.** Inbox (Nuovo + Autorizzato), Da rivedere, Serve info, Chiusi.
7. **Automatic UI check.** With in-place mode the Docker stack already serves the ticket branch, so Playwright (`e2e/demo`) can run against `localhost:3000` as part of verification for changes that touch the frontend.
8. **Model column for triage.** Today the "Model" column only drives the fix agent; triage always cascades Haiku -> Sonnet.
9. **Mutation testing as a tool.** Move the AST mutation sampler used for the test audit into this repo and run it on demand per module.
10. **Triage should recognise duplicates** (the old "Duplicato" state was dropped because nothing could set it).
