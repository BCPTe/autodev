# Configuring a project

Everything project-specific lives in `projects/<name>.yaml` plus two secrets in `.env`. The code knows nothing about any particular project. `projects/example.yaml.dist` is a commented template (copy it to `projects/<name>.yaml`; `.dist` files are ignored by autodev); `projects/demo.yaml` is a real one.

To check what you wrote: `uv run autodev check` (Notion reachable? columns present? GitHub token usable?).

## 1. Secrets (`.env`, never committed)

| Variable | Where to get it |
|---|---|
| `NOTION_TOKEN` | notion.so/profile/integrations → **New integration** (internal) → copy the *Internal Integration Secret*. Then open your ticket database in Notion → `···` menu → **Connections** → add the integration, otherwise every call returns 404. The integration needs *read content*, *update content* and *insert comments*. |
| `GITHUB_TOKEN` | github.com → Settings → Developer settings → Personal access tokens → **Fine-grained**. Resource owner: the owner of the repo (an organization may need to approve it). Repository access: only that repo. Permissions: *Pull requests* read and write, *Contents* read and write (push, delete merged branches), *Checks* read and *Commit statuses* read (CI state on the PR page), *Metadata* read. Only needed when `pr.create` is on or you use the PR page. Without *Contents* GitHub answers "422 Unprocessable Entity" when a PR is opened (`autodev check` now tells you). |
| Claude | No key. The agents use the Claude Code login of the user running autodev (`claude` once in a terminal to log in). |

`git push` itself uses your normal git credentials (SSH key or credential helper), not the token.

## 2. Project file, key by key

### Identity
| Key | Meaning and where to find it |
|---|---|
| `name` | Optional display name. Defaults to the file name. |
| `language` | Language the agents write analysis, questions and notes in (`English`, `Italian`...; default `English`). |
| `repo` | Remote URL of the repository: in the checkout, `git remote get-url origin`. |
| `base_branch` | Branch that fixes branch from and PRs target (`staging`, `main`...). `git branch -a` in the checkout, or the repo's default branch on GitHub. |
| `local_path` | Absolute path of the project's checkout on this machine. |
| `branch_prefix` | Prefix of the branches the agents create (default `autodev`, giving `autodev/<ticket>-<id>`). |
| `workspace_mode` | `inplace`: the agent works in `local_path` itself on its own branch (you can test it with your running Docker; the tree must be clean). `clone`: a throwaway clone under `workspaces/` (needs `prepare`/`exclude` below). |

### Tracker (Notion)
| Key | Meaning and where to find it |
|---|---|
| `tracker.type` | `notion` (the only one today). |
| `tracker.database_id` | The 32 hex characters in the database URL: `notion.so/<workspace>/`**`00000000000000000000000000000000`**`?v=...`. Open the database as a full page first (not an inline view). |
| `tracker.data_source_id` | Notion API 2025-09 splits a database into data sources. Get it with `curl -s https://api.notion.com/v1/databases/<database_id> -H "Authorization: Bearer $NOTION_TOKEN" -H "Notion-Version: 2025-09-03"` and read `data_sources[0].id`. |
| `tracker.status_map` | Maps each autodev state (`new`, `needs_info`, `analyzed`, `in_progress`, `review`, `escalated`, `closed`) to the exact text of the options of the Notion **Status** column. Rename the options in Notion or the labels here, but they must match character for character. |
| `tracker.properties` | Optional. Notion column name for each field the code reads or writes. Defaults (English): `title: Title`, `status: Status`, `kind: Type`, `area: Area`, `priority: Priority`, `environment: Environment`, `page_url: Page URL`, `reported_by: Reported by`, `authorized: Authorized`, `attempts: Attempts`, `cost: Cost (USD)`, `model: Model`, `risk: Risk`, `branch: Branch`, `pr: PR`, `agent_note: Agent notes`, `verification: Verification result`, `attachments: Attachments`. Only list the ones you named differently. The README has the column types. |

### Where to find the code, and what the agent may run
| Key | Meaning and where to find it |
|---|---|
| `area_map` | File (next to the YAML) that tells the triage agent which files belong to each ticket Area. Write one heading per option of the Notion **Area** column, listing the relevant folders/files. Keep it short: it is sent with every triage. |
| `python` | Python interpreter whose environment can run the backend tests, used for `{python}` in commands. Typically `<local_path>/<backend>/.venv/bin/python` (run `which python` inside the venv). Default `python3`. |
| `agents.triage.models` / `agents.fix.models` | Model ids, cheapest first. Triage moves to the next one when confidence is low; fix moves to the next one on each retry. Ids: see the Anthropic model list (`claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5`, ...). |
| `agents.*.max_turns` | Upper bound of agent steps per run (cost control). |
| `agents.fix.allowed_bash` | Bash command prefixes the fix agent may run without asking (`{python} -m pytest`, `git status`...). Anything else needs your approval in the dashboard, or is denied in Auto mode. Run from the repo root: `cd` and compound commands are not allowed. |
| `agents.*.commands` | Free text appended to the fix agent's prompt: the exact test and typecheck commands for your stack. Must match `allowed_bash`. |
| `agents.*.instructions` | Free text appended to the agent's prompt for project rules that are not in the repo's `CLAUDE.md` (which is read automatically). |
| `min_body_chars` | A ticket whose description is shorter is bounced to "needs info" without spending an agent run. |

### Verification (what "fixed" means)
| Key | Meaning and where to find it |
|---|---|
| `checks` | List of `{name, cmd, cwd, when_changed}` run after every fix and from the Repo page. `cwd` is relative to the repo root; `when_changed` (optional) lists path prefixes: the check runs only if the fix touches them. Use the commands you already run before a PR (test suites, `tsc`, lint). |
| `regressions` | List of `{test_globs, cwd, cmd}`. A fix must add a test matching `test_globs` (repo-relative, `*` also crosses folders) that **fails without the fix and passes with it**; `{tests}` in `cmd` becomes the new test files. One entry per test suite (backend, frontend...). Without any, the gate is skipped. |
| `prepare`, `exclude` | Only for `workspace_mode: clone`: shell commands run in the fresh clone (copy untracked data, link `node_modules`) and paths kept out of commits. Placeholders: `{python}`, `{local_path}`. |

### Pull requests, risk, limits
| Key | Meaning and where to find it |
|---|---|
| `pr.create` | `true` to push the branch and open a PR after a verified fix; `false` leaves the branch local. |
| `pr.slug` | `owner/repo` as in `github.com/owner/repo`. Needed for the PR page, merge and housekeeping even when `create` is false. |
| `risk.never_automerge` | Globs of sensitive files (billing, auth, migrations). A change touching them is rated **High**: never approved by Auto and never mergeable from the dashboard. Think of what would hurt in production. |
| `limits.max_attempts` | Fix attempts inside one run (each retry gets the verification output). |
| `limits.max_fix_runs` | How many times a ticket may be started before it escalates; reset with "Azzera tentativi". |
| `limits.max_files` | A fix touching more files than this is escalated as suspicious. |
| `limits.budget_usd_per_ticket` | Total spend allowed on one ticket across triage and fixes. |
| `limits.daily_budget_usd` | Default daily cap per project (editable in the dashboard). Values are dollar equivalents; with a subscription you do not pay them but they use your quota. |
| `model_choices` | Names selectable in the Notion **Model** column → model id. The names must be exactly the options of that column (plus `Auto`, which uses `agents.fix.models`). |

### `autonomy` (how independent it is)
| Key | Meaning |
|---|---|
| `default_mode` | Mode at first start: `manual` (default), `supervised`, `auto`, `paused`. Afterwards the dashboard's choice is remembered. |
| `poll_seconds` | How often Auto/Supervised look at the board (default 60). |
| `retry_cooldown_seconds` | A ticket whose run failed is not retried automatically for this long (default 1800). |
| `auto_approve_risks` | Risk levels Auto may approve by itself (default `[Low, Medium]`). |
| `checkpoints` | Where a run waits for you (never in Auto): `after_agent`, `before_pr` (default). |
| `quiet_hours` | `"22:00-07:00"` local time: nothing starts by itself. |
| `notify_command` | Desktop notifier as an argument list with `{title}` and `{body}`. Default: `notify-send` if installed. |
| `auto_cleanup_branches` | Delete the local branch when its PR is merged. |

### Present in the file but not used by the code
`commands` and `environments` (in `demo.yaml`) are notes for humans today; no part of autodev reads them. You can omit them.
