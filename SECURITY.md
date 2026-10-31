# Security policy

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's **Report a vulnerability** button in the Security tab of this repository (private vulnerability reporting). Include the version or commit, what you did and what you expected. You will get a first answer within a week.

## What to keep in mind when running autodev

autodev runs AI agents that execute commands, tests and `git` on a checkout of your repository, and can push branches and open pull requests with your tokens.

- **Tokens:** `NOTION_TOKEN` and `GITHUB_TOKEN` live in `.env`, which is git-ignored. Use a fine-grained GitHub token limited to the target repository, and a Notion integration shared only with the ticket database.
- **Dashboard:** it listens on `127.0.0.1` and is protected by a password set on first visit. Do not expose it to the internet or a shared network; put it behind a VPN or an authenticated reverse proxy with HTTPS if you need remote access.
- **Agent permissions:** keep `autonomy.permission_policy: ask` until you trust the setup. Destructive commands (`rm -rf`, `git push`, `sudo`, reading `.env` or `~/.ssh`, writes outside the project) always wait for you and are refused in Auto mode.
- **Ticket content is untrusted input:** anyone who can write a ticket can influence an agent. Keep the **Authorized** checkbox for people you trust, and prefer Manual or Supervised mode on repositories with sensitive code.
- **Project files:** `projects/*.yaml` and the playbook can contain internal paths and identifiers; they are git-ignored by default.

## Supported versions

Only the latest commit on `main`.
