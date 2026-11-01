import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

from autodev.config import load_project
from autodev.db import Database
from autodev.trackers.notion import NotionTracker


def serve(projects: list[str], port: int, dev: bool = False) -> int:
    """Serves the dashboard for the given projects, or for every file in projects/ when none is named.

    With dev, also runs the Vite dev server (hot reload) proxying /api to this backend.
    """
    import uvicorn

    from autodev.engine import Engine
    from autodev.server.app import Ctx, build_app

    names = projects or sorted(p.stem for p in Path("projects").glob("*.yaml"))
    token = os.environ.get("NOTION_TOKEN")
    if names and not token:
        print("NOTION_TOKEN missing in .env")
        return 1
    db = Database()

    def context(name: str) -> Ctx:
        cfg = load_project(f"projects/{name}.yaml")
        tracker = NotionTracker(cfg.tracker, token)
        return Ctx(cfg, name, db, tracker, Engine(cfg, name, db, tracker))

    app = build_app(db, [context(n) for n in names], run_loop=True)
    code = app.state.auth.setup_code
    vite = None
    if dev:
        dashboard = Path(__file__).resolve().parents[2] / "dashboard"
        if not shutil.which("npm"):
            print("--dev needs npm")
            return 1
        if not (dashboard / "node_modules").is_dir():
            subprocess.run(["npm", "ci"], cwd=dashboard, check=True)
        env = {**os.environ, "AUTODEV_API": f"http://127.0.0.1:{port}"}
        vite = subprocess.Popen(["npm", "run", "dev"], cwd=dashboard, env=env)
    print(f"\nautodev dashboard: http://localhost:{5173 if dev else port}")
    if code:
        print(f"First setup: on the page enter the code  {code}  and choose a password.\n")
    try:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    finally:
        if vite:
            vite.terminate()
    return 0


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="autodev", description="Start the local dashboard.")
    parser.add_argument("--project", action="append", default=[], help="repeatable; default: every file in projects/")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--dev", action="store_true", help="also run the Vite dev server with frontend hot reload (http://localhost:5173)")
    args = parser.parse_args()
    sys.exit(serve(args.project, args.port, args.dev))


if __name__ == "__main__":
    main()
