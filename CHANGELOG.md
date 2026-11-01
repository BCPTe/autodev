# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-11-01

First public release (source-available, FSL-1.1-ALv2).

### Added
- Orchestrator that turns Notion tickets into verified pull requests with Claude agents: triage, fix, checks and PR.
- Dashboard: Now, Tickets, Pull requests, Learnings, Costs and Settings, with Auto / Supervised / Manual / Paused modes, a daily cost cap and quiet hours.
- Per-project configuration in `projects/*.yaml`, with `example` and `sandbox` templates and a "Reset to project file" button in Settings.
- Demo server (`e2e/autodev/demo_server.py`) with fake data for UI work and screenshots.
- CI (backend tests, dashboard checks, gitleaks), CLA Assistant, Dependabot, `SECURITY.md` and `CONTRIBUTING.md`.
