# Pointing autodev at another project

Everything project-specific lives in `projects/<name>.yaml`; the code has no knowledge of Acme.
With a single file in `projects/`, `--project` can be omitted.

| Key | What it controls |
|---|---|
| `name`, `language` | Display name; language the agents write analysis and notes in |
| `repo`, `base_branch`, `local_path`, `branch_prefix` | The checkout, the branch PRs target, the prefix of agent branches |
| `workspace_mode` | `inplace` (the checkout itself) or `clone` |
| `tracker.status_map` | Notion status label for each autodev state |
| `tracker.properties` | Notion column name for each field (title, status, kind, area, priority, environment, page_url, reported_by, authorized, attempts, cost, model, risk, branch, pr, agent_note, verification, attachments); omitted keys use the defaults in `config.py` |
| `agents.triage` / `agents.fix` | `models` (cheapest first), `max_turns`, `allowed_bash`, `commands`, `instructions` (extra prompt text) |
| `area_map` | Markdown file mapping ticket areas to code |
| `checks`, `regressions`, `prepare`, `python` | How to verify a fix in that stack |
| `limits`, `risk`, `model_choices`, `pr` | Budgets, risky paths, model names, pull requests |

Dashboard: `cd dashboard && npm install && npm run build`, then `uv run autodev serve`.
