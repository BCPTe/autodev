from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from autodev.models import Status


DEFAULT_PROPERTIES = {
    "title": "Title", "status": "Status", "kind": "Type", "area": "Area", "priority": "Priority",
    "environment": "Environment", "page_url": "Page URL", "reported_by": "Reported by",
    "authorized": "Authorized", "attempts": "Attempts", "cost": "Cost (USD)", "model": "Model",
    "risk": "Risk", "branch": "Branch", "pr": "PR", "agent_note": "Agent notes",
    "verification": "Verification result", "attachments": "Attachments",
}


class TrackerConfig(BaseModel):
    type: str
    database_id: str
    data_source_id: str
    status_map: dict[Status, str]
    properties: dict[str, str] = {}

    def prop(self, key: str) -> str:
        """Name of the tracker column that holds `key`; override any of them under `tracker.properties`."""
        return self.properties.get(key) or DEFAULT_PROPERTIES[key]


class Limits(BaseModel):
    max_attempts: int = 3
    max_fix_runs: int = 3
    max_files: int = 10
    budget_usd_per_ticket: float = 5.0
    daily_budget_usd: float = 20.0


class RiskConfig(BaseModel):
    never_automerge: list[str] = []


class Environment(BaseModel):
    url: str
    auth: str | None = None


class AgentConfig(BaseModel):
    models: list[str]
    max_turns: int = 15
    allowed_bash: list[str] = []
    commands: str = ""
    instructions: str = ""


class Check(BaseModel):
    name: str
    cmd: str
    cwd: str = "."
    when_changed: list[str] = []


class Regression(BaseModel):
    """Tests added by the fix must fail on the base commit and pass on the fixed one."""

    test_globs: list[str]
    cmd: str
    cwd: str = "."


class PRConfig(BaseModel):
    create: bool = False
    slug: str | None = None


class ProjectConfig(BaseModel):
    name: str = ""
    language: str = "Italian"
    branch_prefix: str = "autodev"
    repo: str
    base_branch: str
    local_path: str
    tracker: TrackerConfig
    commands: dict[str, str] = {}
    environments: dict[str, Environment] = {}
    risk: RiskConfig = RiskConfig()
    limits: Limits = Limits()
    agents: dict[str, AgentConfig] = {}
    model_choices: dict[str, str] = {}
    area_map: str | None = None
    area_map_text: str = ""
    min_body_chars: int = 40
    workspace_mode: Literal["clone", "inplace"] = "clone"
    python: str | None = None
    prepare: list[str] = []
    exclude: list[str] = []
    checks: list[Check] = []
    regressions: list[Regression] = []
    pr: PRConfig = PRConfig()


def load_project(path: str | Path) -> ProjectConfig:
    path = Path(path)
    cfg = ProjectConfig.model_validate(yaml.safe_load(path.read_text()))
    if cfg.area_map:
        cfg.area_map_text = (path.parent / cfg.area_map).read_text()
    return cfg
