# Screenshots

Images used by the README. Capture them from the demo server (fake data, no Notion, no agents):

```
uv run python e2e/autodev/demo_server.py 8799 /tmp/autodev-demo.db
```

Open http://127.0.0.1:8799, 1440x900 window, light theme unless noted. Save PNGs here with these names:

| File | Page | What it must show |
|---|---|---|
| `now.png` | Now | Mode switch, "Needs you" cards, a run in progress |
| `ticket.png` | Ticket page | Decisions on one side, live run console on the other |
| `pull-requests.png` | Pull requests | Checks, risk and the merge button |
| `learnings.png` | Learnings | Playbook entries and a pending proposal |
| `settings.png` | Settings | The "differs from project file" banner with Reset |
| `costs.png` | Costs | Breakdown by stage, model and area |
| `now-dark.png` | Now | Same as `now.png`, dark theme |

Keep each file under 300 KB (e.g. `oxipng -o4` or `pngquant`) and make sure no real names, tokens or paths are visible.
