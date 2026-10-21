# Notion database schema (proposal)

One database, "Ticket". Humans fill the **Intake** properties, the orchestrator owns the **Pipeline** and **Output** properties.

## Intake (filled by users / you)

| Property | Type | Notes |
|---|---|---|
| Titolo | Title | Short description of the problem |
| Tipo | Select | `Bug`, `Modifica`, `Feature`, `Domanda` |
| Area | Select | `Wizard`, `Autofill`, `Export PDF`, `Documenti secondari`, `Admin`, `Rubrica`, `Billing`, `Auth`, `Altro` (helps triage find the right files) |
| Descrizione | Page body | What happened, steps to reproduce, expected vs actual |
| Segnalato da | Person / Text | Who reported it |
| Allegati | Files | Screenshots, example PDFs |
| URL pagina | URL | Where in the app it happened |
| Ambiente | Select | `Produzione`, `Staging`, `Locale` |
| Priorità | Select | `Bassa`, `Media`, `Alta`, `Bloccante` |
| Autorizzato | Checkbox | The agent only picks up tickets with this ticked (gate against prompt injection and noise) |

## Pipeline (owned by the orchestrator)

| Property | Type | Notes |
|---|---|---|
| Stato | Status | See state machine below |
| Rischio | Select | `Basso`, `Medio`, `Alto` (set by triage, drives merge gate) |
| Modello | Select | `Auto`, `Haiku`, `Sonnet`, `Opus`, `Fable`. Model used by the fix agent. Auto = Sonnet first, Opus on retry after failed verification |
| Agent run ID | Text | Idempotency key, one run per ticket |
| Tentativi | Number | Capped by `limits.max_attempts` |
| Costo (USD) | Number | Accumulated token cost |

## Output (written by the orchestrator)

| Property | Type | Notes |
|---|---|---|
| Analisi | Page section / comment | Diagnosis, suspected files |
| PR | URL | Pull request link |
| Branch | Text | e.g. `fix/ticket-123` |
| Esito verifica | Select | `Non eseguita`, `Passata`, `Fallita` |
| Note agente | Text | What was tried, why it escalated |
| Risolto il | Date | |

## State machine (`Stato`)

| Stato | Who sets it | Meaning |
|---|---|---|
| Nuovo | you | Waiting for triage (needs "Autorizzato") |
| Serve info | autodev | Ticket too vague; answer, then set back to Nuovo |
| Analizzato | autodev | Triage says "ready"; waiting for your go-ahead |
| In lavorazione | you | Your approval; `autodev fix` picks it up |
| Da rivedere | autodev | Fix verified; a PR (or local branch) awaits your review |
| Escalation umana | autodev | Something failed; needs you |
| Chiuso | you (or autodev) | Done, not reproducible or duplicate; reason in "Note agente" |

```
Nuovo ─► Serve info ─► (you answer) ─► Nuovo
  │
  ├─► Chiuso (not reproducible)
  ▼
Analizzato ─(you)─► In lavorazione ─► Da rivedere ─(you merge)─► Chiuso
                         └────────► Escalation umana
```
