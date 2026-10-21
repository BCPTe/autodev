# Notion database schema

One database, "Ticket". Humans fill the **Intake** properties, the orchestrator owns the **Pipeline** and **Output** properties.

## Intake (filled by users / you)

| Property | Type | Notes |
|---|---|---|
| Title | Title | Short description of the problem |
| Type | Select | `Bug`, `Modifica`, `Feature`, `Domanda` |
| Area | Select | `Wizard`, `Autofill`, `Export PDF`, `Documenti secondari`, `Admin`, `Rubrica`, `Billing`, `Auth`, `Altro` (helps triage find the right files) |
| Descrizione | Page body | What happened, steps to reproduce, expected vs actual |
| Reported by | Person / Text | Who reported it |
| Attachments | Files | Screenshots, example PDFs |
| Page URL | URL | Where in the app it happened |
| Environment | Select | `Produzione`, `Staging`, `Locale` |
| Priority | Select | `Bassa`, `Media`, `Alta`, `Bloccante` |
| Authorized | Checkbox | The agent only picks up tickets with this ticked (gate against prompt injection and noise) |

## Pipeline (owned by the orchestrator)

| Property | Type | Notes |
|---|---|---|
| Status | Status | See state machine below |
| Risk | Select | `Basso`, `Medio`, `Alto` (set by triage, drives merge gate) |
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
| Verification result | Select | `Non eseguita`, `Passata`, `Fallita` |
| Agent notes | Text | What was tried, why it escalated |
| Risolto il | Date | |

## State machine (`Status`)

| Status | Who sets it | Meaning |
|---|---|---|
| Nuovo | you | Waiting for triage (needs "Authorized") |
| Serve info | autodev | Ticket too vague; answer, then set back to Nuovo |
| Analizzato | autodev | Triage says "ready"; waiting for your go-ahead |
| In lavorazione | you | Your approval; `autodev fix` picks it up |
| Da rivedere | autodev | Fix verified; a PR (or local branch) awaits your review |
| Escalation umana | autodev | Something failed; needs you |
| Chiuso | you (or autodev) | Done, not reproducible or duplicate; reason in "Agent notes" |

```
Nuovo ─► Serve info ─► (you answer) ─► Nuovo
  │
  ├─► Chiuso (not reproducible)
  ▼
Analizzato ─(you)─► In lavorazione ─► Da rivedere ─(you merge)─► Chiuso
                         └────────► Escalation umana
```
