# Contributing

Thanks for helping. Small, focused pull requests are easiest to review; for anything big, open an issue first.

## Setup

```
uv sync
cd dashboard && npm install
```

No Notion or GitHub token is needed to work on the code: tests use fakes and fixtures in `tests/fixtures`.

## Checks before a PR

```
uv run pytest
cd dashboard && npx tsc -b && npm run lint && npm run build
```

## Working on the dashboard

`uv run autodev serve --dev` runs the API with the Vite dev server (hot reload). To see the UI with fake data and no credentials:

```
uv run python e2e/autodev/demo_server.py 8799 /tmp/autodev-demo.db
```

## Conventions

- Python 3.12, type hints, and a test for every behaviour change (`tests/`, pytest-asyncio and respx for HTTP).
- Keep autodev project-agnostic: nothing specific to one target repository belongs in `src/`, tests or docs. Use `tests/fixtures/demo.yaml` for examples.
- Dashboard: React, Tailwind and shadcn components in `dashboard/src/components/ui`.
- Never commit `.env`, `projects/<your-project>.*`, `data/` or `workspaces/`.
- If you change configuration or behaviour, update `README.md` or `docs/CONFIG.md` in the same PR.

## License and contributions

autodev is released under the [FSL-1.1-ALv2](LICENSE). The copyright holders keep the right to license future versions differently, so **for now we only accept pull requests from contributors who agree to a Contributor License Agreement** that grants this right. When you open a pull request, the CLA bot comments with the [agreement](docs/CLA.md); sign it once by replying `I have read the CLA Document and I hereby sign the CLA`, and the check turns green for this and all your future PRs. Bug reports and ideas are always welcome without one.
