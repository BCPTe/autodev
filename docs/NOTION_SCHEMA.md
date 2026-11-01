# Notion database schema

One database, "Ticket". Humans fill the **Intake** properties, the orchestrator owns the **Pipeline** and **Output** properties.

## Intake (filled by users / you)

| Property | Type | Notes |
|---|---|---|
| Title | Title | Short description of the problem |
| Type | Select | `Bug`, `Change`, `Feature`, `Question` |
| Area | Select | `Wizard`, `Autofill`, `Export PDF`, `Documenti secondari`, `Admin`, `Rubrica`, `Billing`, `Auth`, `Altro` (helps triage find the right files) |
| Descrizione | Page body | What happened, steps to reproduce, expected vs actual |
| Reported by | Person / Text | Who reported it |
| Attachments | Files | Screenshots, example PDFs |
| Page URL | URL | Where in the app it happened |
| Environment | Select | `Production`, `Staging`, `Local` |
| Priority | Select | `Low`, `Medium`, `High`, `Blocking` |
| Authorized | Checkbox | The agent only picks up tickets with this ticked (gate against prompt injection and noise) |

## Pipeline (owned by the orchestrator)

| Property | Type | Notes |
|---|---|---|
| Status | Status | See state machine below |
| Risk | Select | `Low`, `Medium`, `High` (set by triage, drives merge gate) |
| Model | Select | `Auto`, `Haiku`, `Sonnet`, `Opus`, `Fable`. Model used by the fix agent. Auto = Sonnet first, Opus on retry after failed verification |
| Agent run ID | Text | Idempotency key, one run per ticket |
| Attempts | Number | Capped by `limits.max_attempts` |
| Cost (USD) | Number | Accumulated token cost |

## Output (written by the orchestrator)

| Property | Type | Notes |
|---|---|---|
| Analisi | Page section / comment | Diagnosis, suspected files |
| PR | URL | Pull request link |
| Branch | Text | e.g. `fix/ticket-123` |
| Verification result | Select | `Not run`, `Passed`, `Failed` |
| Agent notes | Text | What was tried, why it escalated |
| Risolto il | Date | |

## State machine (`Status`)

| Status | Who sets it | Meaning |
|---|---|---|
| New | you | Waiting for triage (needs "Authorized") |
| Needs info | autodev | Ticket too vague; answer, then set back to New |
| Analysed | autodev | Triage says "ready"; waiting for your go-ahead |
| In progress | you | Your approval; the engine picks it up |
| In review | autodev | Fix verified; a PR (or local branch) awaits your review |
| Needs a human | autodev | Something failed; needs you |
| Closed | you (or autodev) | Done, not reproducible or duplicate; reason in "Agent notes" |

```
New ─► Needs info ─► (you answer) ─► New
  │
  ├─► Closed (not reproducible)
  ▼
Analysed ─(you)─► In progress ─► In review ─(you merge)─► Closed
                         └────────► Needs a human
```
