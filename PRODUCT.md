# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
A solo developer who owns the target repos and runs autodev on their own machine. They keep the dashboard open next to their editor, glance at it while working, approve tickets and pull requests, and check what the agents are spending.

## Product Purpose
autodev turns tracker tickets (Notion) into verified pull requests using Claude agents. The dashboard is the control room: it shows what is running, what needs the user's decision, what it cost, and what the agents learned. Success is the user trusting the agents with progressively more work while never being surprised by a push, a PR or a bill.

## Positioning
- Notion tickets in, verified pull request out: the tracker is the interface and work is verified before a PR opens.
- Graduated autonomy (Auto, Supervised, Manual, Paused, plus risk-based approval) so trust is extended step by step.
- Cost and quota awareness: daily and per-ticket caps, with token and cost breakdowns by stage and model.
- A learnings loop: agents propose knowledge entries the user reviews, so later runs improve.

## Operating Context
Localhost only (127.0.0.1:8765, password set on first visit); never exposed beyond the machine. One agent runs at a time and "My turn" holds the checkout while the user works in it. Project behaviour lives in `projects/<name>.yaml`; the dashboard changes only autonomy mode, quiet hours, daily cap and similar overrides. Dev and screenshots use `e2e/autodev/demo_server.py` with fake data.

## Capabilities and Constraints
Tickets can be authorized, approved, retried, closed, given a model and commented on; running agents can be messaged, paused and asked for permissions. Pages: Now, Tickets, Runs, Pull requests, Repo, Costs, Learnings, Settings. Figures are dollar-equivalents: on a subscription the user is not billed, but they count against quota. Stack is React + Vite + Tailwind + TanStack Query, served by a Python API.

## Brand Commitments
None recorded. Copy is plain, short and jargon-free, as in the current Settings and Costs labels.

## Evidence on Hand
Real screenshots in `docs/screenshots`; fake-data demo server in `e2e/autodev/demo_server.py`. No testimonials, customers or benchmarks exist: do not invent any.

## Product Principles
- The user's decision points are the product: anything needing approval is findable in seconds.
- Money and risk are always visible, never buried; caps and over-limit states are unmistakable.
- Show what the agents did and why, in plain language, before offering controls.
- Dense but calm: a tool glanced at all day should not demand attention it has not earned.
- Safe defaults: nothing starts, pushes or spends without the user having chosen that level of autonomy.
