# Where the money goes

Measured on the 8 agent runs recorded for one real project on 2026-10-22 (database `runs` and `events`, plus the Claude Code session transcripts, which carry the API usage of every turn). Dollar values are list-price equivalents, as everywhere in autodev.

## The short answer

**About two thirds of what was spent bought nothing the agent used**: every session carried ~127,000 tokens of tool definitions for the 76 MCP tools of the claude.ai connectors of the account autodev runs under (Notion, Google, Booking, ...), and each turn re-read them. The sessions never called one of those tools. Telling the CLI to ignore them (`strict_mcp_config`, now the default) removes them. The same fixture ticket went from **$0.155 to $0.001 on Haiku and $0.566 to $0.015 on Sonnet** with the same outcome (verification gate passed, regression test fails before and passes after).

## Ranked by dollars

Booked cost of the 8 runs: **$10.50** (plus ~$1.1 that was never booked, see 6). Split by what the tokens were, using the sessions' token counts with the standard relative rates (cache read 0.1x, cache write 1.25x, output 5x of input) and scaling each run to its booked cost:

| # | Cause | $ | Share | Evidence |
|---|---|---|---|---|
| 1 | Tool definitions of the account's MCP connectors (`deferred_tools_delta`, 76 tools) | 7.0 | 67% | Context is 8.7k tokens on turn 1 and 137k on turn 2 in every session, triage and fix alike. The attachment is 345 KB. Written to the cache once, then read on every later turn |
| 2 | Conversation growth: tool results re-read on every later turn | 2.1 | 20% | 30-70k chars of tool output per session; large single results: 29k chars (a grep in `data/knowledge_base`), 15k (`cat` of a scratch file), 11k (greps) |
| 3 | Fixed prompt re-read each turn (system prompt, tool schemas, CLAUDE.md, area map, playbook) | 0.8 | 8% | 8.7k tokens for triage, 15k for fix. CLAUDE.md of the measured project is 11.6 KB of it |
| 4 | Output tokens (reasoning, edits, final JSON) | 0.6 | 6% | 2-12k output tokens per session |

On top of the token split, the process added cost:

5. **Retries are 47% of the booked dollars.** Runs 12 and 13 (Sonnet then Opus attempts after the first fix) cost $4.92 of $10.50; each one started a fresh session and spent its first 5-6 tool calls on `git show`, `git diff`, `cat <the test it had written>` to find out where it was.
6. **Failed sessions were not booked.** Run 10's Haiku triage ended on `error_max_turns` (15 turns, 23 tool calls, no answer) and Sonnet started over: ~$0.46 never reached the run, the ticket or the daily cap. Run 6 (`failed`) shows $0.00 for a session worth ~$0.7. The cap was weaker than it looked.
7. **The cascade paid twice on 2 of 3 triages.** Run 2: Haiku answered `needs_info` with low confidence ($0.25), then Sonnet ($0.71) re-explored from zero. Run 10: Haiku hit the turn cap, then Sonnet. Run 3: Haiku was enough.
8. **Why the dollars were so high per token.** Prompts above roughly 100k tokens are billed at a much higher rate per token. Measured with a haiku prompt with no tools: 50k tokens $0.16 per million token-equivalents, 93k $0.16, **127k $0.80 (5x)**. The connectors pushed every turn of every session to 130-185k, so item 1 also moved everything else into the expensive range. This is why the fix is worth 100x on small sessions rather than 3x.
9. The retrospective cost $0.14 for 2 turns because it carried the same 127k tokens; it ran on a ticket that already had a person's comments, so it is only skipped now when nothing happened.

### What does not matter (measured, left alone)

- **Cap tool output / read large JSON smarter.** The 29k-char grep was re-read ~7 times: ~$0.03 once the context is small. Not worth a custom reading tool or output caps.
- **Trimming the project's CLAUDE.md** (11.6 KB, ~3k tokens): 3k tokens x 20 turns x 0.1 is about $0.01 per fix on Sonnet.
- **Lower `max_turns` for fix**: no fix needed more than 21 turns, but the cap does not save money unless a run loops. Set to 30 as a safety net. **Triage went up to 25**: it is the cap that made Haiku fail in run 10 and pay twice.
- **Sonnet-first triage instead of Haiku-first**: Haiku was enough in 3 of 5 sessions. With the connectors gone a Haiku triage is a few cents; the cascade is cheap again. Not changed.
- **Turns lost to permission prompts**: run 4 had 11 asks, run 11 had 3 (python heredocs, `sed`, `cat > /tmp/x.py`). They cost wall time (run 11 took 991 s for 17 turns) and a human click, not tokens.

## What changed

| Change | Effect | Config |
|---|---|---|
| Agents run with `strict_mcp_config` and without the user's Claude memory (`CLAUDE_CODE_DISABLE_AUTO_MEMORY`) | removes cause 1 and 8, plus ~3k tokens of personal memory per session | `agents.<name>.user_mcp` (default `false`) |
| Every session records its usage: model, tokens in/out/cache read/cache write, cost, turns, tools called, size of tool results, peak context, permission denials, whether it resumed | `runs.usage` (JSON), shown per run and on the Costs page | always on |
| A session that fails (turn cap, budget cap) is booked: its cost is on the run, on the ticket and in the daily cap, and is shown in the triage comment (`haiku (15 turns, $0.40, failed)`) | closes item 6 | always on |
| A failed or cancelled run books what its sessions cost | closes item 6 for runs that raise | always on |
| The automatic retrospective is skipped when nothing happened (no person comment, retry, checkpoint note or denied request); on-demand "Learn" always runs | saves the retrospective run on smooth tickets | `knowledge.skip_uneventful` (default `true`) |
| A retry inside a run can continue the previous fix session with only the feedback as the message | untested for savings, so off | `agents.fix.resume_retries` (default `false`) |
| Example project: triage `max_turns` 15 to 25, fix 40 to 30 | avoids the failed-cheap-model cascade | the project YAML |
| Costs page: tokens and cost by stage and model (with peak context, red when over 100k), average cost per area, cost per outcome, run detail with its sessions | the numbers above, live | |

The verification gate is untouched.

## Before and after

On the throwaway fixture project (`tests/fixture_repo.py`, the ticket of `tests/test_fix_agent.py`), same prompt, same checks, `user_mcp: true` (old behaviour) against `false`:

| Model | | Cost | Turns | Cache read | Cache write | Time | Result |
|---|---|---|---|---|---|---|
| Haiku 5.5 | before | $0.1551 | 8 | 417k | 132k | 14.9 s | verified |
| | after | $0.0011 | 7 | 26k | 1.8k | 8.5 s | verified |
| Sonnet 5.5 | before | $0.5661 | 8 | 280k | 132k | 19.1 s | verified |
| | after | $0.0146 | 7 | 19k | 1.3k | 7.3 s | verified |

On the 8 real runs (estimate: the real sessions' tokens minus the 127k-token connector blob, priced at the small-context rates measured on the fixture; Opus is assumed at 1.7x Sonnet because it was not measured):

| Run | Booked | Estimated now |
|---|---|---|
| 2 triage Haiku then Sonnet | $0.97 | $0.12 |
| 3 triage Haiku | $0.39 | $0.04 |
| 4 fix Sonnet | $1.18 | $0.41 |
| 10 triage Haiku (failed) then Sonnet | $1.40 | $0.53 |
| 11 fix Sonnet | $1.50 | $0.57 |
| 12 fix Sonnet then Opus x2 | $2.17 | $0.36 |
| 13 fix Sonnet then Opus | $2.75 | $0.64 |
| 14 retrospective | $0.14 | $0.00 |
| **Total** | **$10.50** | **~$2.7 (-75%)** |

Sonnet shows no long-context premium in these measurements, so its sessions only lose the connector tokens (-60%); Haiku sessions lose the premium too (-90%).

Spent on the measurements above: about $1.25 (haiku and sonnet sessions on the fixture only; nothing ran on the real checkout, Notion or GitHub).

## How to re-measure

- Costs page, "Tokens and cost by stage and model": a red peak context means a session went over 100k tokens. Runs from before the instrumentation show "tokens not recorded".
- `uv run python scripts/transcript_usage.py /path/to/checkout --since 2026-10-22T00:00` takes the Claude Code transcripts of a checkout apart (read only): tokens by kind, context per turn, tools, and any large attachment. Run it on any session that looks expensive.

## Not verified against real services

- No agent ran on the real checkout, so the "now" column of the real runs is an estimate. The first real runs after this change should land at roughly $0.05-0.15 per triage and $0.3-0.7 per fix; if they do not, the Costs page shows which session and why.
- `resume_retries` was checked against the real SDK only for the plumbing (a session id resumes with its context; a wrong id raises and falls back to a fresh session). Whether it saves money was not measured.
- The Opus price ratio is an assumption.
- Permission prompts in the interactive (dashboard) mode were not exercised with real agents.

## Decisions for you

1. **Per-ticket cap.** `budget_usd_per_ticket: 6` and daily `20` were sized for the old costs. A typical ticket should now be under $1; a cap of $2-3 would stop a runaway loop sooner.
2. **Opus on retry.** Both Opus retries (runs 12, 13) found the same orientation work to do; one escalated, one reached review. With cheap sessions, retrying once more on Sonnet before Opus is worth trying (`agents.fix.models` advances one entry per attempt, so `[claude-sonnet-5-5, claude-sonnet-5-5, claude-opus-5-5]` does it).
3. **`resume_retries`.** Turn it on for your project and compare the retries' cost on the Costs page.
4. **Python one-liners for the fix agent.** It reaches for `python3 - <<EOF` to inspect the knowledge-base JSON and is asked for permission each time. Allowing `{python} -I -c` removes the asks but lets the agent run arbitrary code in your checkout; I did not widen it.
5. **CLAUDE.md size.** 11.6 KB injected into every fix turn; about $0.01 per fix, so only worth trimming if you want the agent to read less.
