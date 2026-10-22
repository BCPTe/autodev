"""Where did an agent session's tokens go? Reads Claude Code transcripts (read only).

autodev runs its agents through Claude Code, which keeps one JSONL transcript per session under
~/.claude/projects/<checkout path with / and . replaced by ->/. Each assistant message carries the
API usage, so a session can be taken apart after the fact: tokens by kind, the conversation size per
turn, the tools called, and anything large that entered the context (the `deferred_tools_delta`
attachment is the list of the account's MCP connectors).

    uv run python scripts/transcript_usage.py /path/to/checkout [--since 2026-10-22T00:00]
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

READ, WRITE, OUT = 0.1, 1.25, 5.0  # relative prices of a cached read, a cache write and an output token, input = 1


def project_dir(checkout: str) -> Path:
    return Path.home() / ".claude" / "projects" / re.sub(r"[/_.]", "-", str(Path(checkout).resolve()))


def load(path: Path) -> dict:
    calls: dict[str, dict] = {}
    tools: Counter = Counter()
    blobs: list[tuple[str, int]] = []
    first_ts, first_prompt = None, ""
    for line in path.read_text().splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        kind = d.get("type")
        if kind == "user" and first_ts is None:
            content = d["message"]["content"]
            first_ts, first_prompt = d.get("timestamp"), (content if isinstance(content, str) else "")[:40].replace("\n", " ")
        elif kind == "assistant":
            m = d["message"]
            calls[m["id"]] = m
            for b in m["content"]:
                if b.get("type") == "tool_use":
                    tools[b["name"]] += 1
        elif kind == "attachment":
            a = d["attachment"]
            size = len(json.dumps(a))
            if size > 20_000:
                blobs.append((a.get("type", "?"), size))
    usage = [m["usage"] for m in calls.values()]
    ctx = [u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0) for u in usage]
    total = {k: sum(u.get(k, 0) for u in usage) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}
    units = total["input_tokens"] + OUT * total["output_tokens"] + READ * total["cache_read_input_tokens"] + WRITE * total["cache_creation_input_tokens"]
    return {
        "file": path.stem[:8], "start": first_ts, "prompt": first_prompt, "model": next(iter(calls.values()))["model"] if calls else "?",
        "turns": len(calls), "ctx": ctx, "tools": dict(tools), "blobs": blobs, **total, "units": units,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("checkout")
    ap.add_argument("--since", default="")
    ap.add_argument("--match", default="^(Triage|Fix) this ticket|^Review this ticket", help="regex on the first prompt: which sessions are autodev's")
    args = ap.parse_args()
    rows = [load(p) for p in project_dir(args.checkout).glob("*.jsonl")]
    rows = [r for r in rows if r["start"] and r["start"] >= args.since and re.search(args.match, r["prompt"])]
    for r in sorted(rows, key=lambda r: r["start"]):
        first, second = (r["ctx"] + [0, 0])[:2]
        print(f"{r['start'][:19]} {r['file']} {r['model'].replace('claude-', ''):<12} turns={r['turns']:>2} out={r['output_tokens']:>6} read={r['cache_read_input_tokens']:>8} write={r['cache_creation_input_tokens']:>7} "
              f"ctx first={first:>6} second={second:>6} last={r['ctx'][-1] if r['ctx'] else 0:>6} tools={r['tools']}")
        for name, size in r["blobs"]:
            print(f"    large attachment: {name} ({size // 4:,} tokens approx.)")


if __name__ == "__main__":
    main()
