"""The ticket database autodev expects, as Notion API payloads: create it, or add what an existing one lacks."""
import httpx

from autodev.config import DEFAULT_PROPERTIES
from autodev.models import Status
from autodev.trackers.notion import API, VERSION

STATUS_LABELS = {
    Status.NEW: ("New", "To-do", "gray"),
    Status.NEEDS_INFO: ("Needs info", "In progress", "yellow"),
    Status.ANALYZED: ("Analysed", "In progress", "blue"),
    Status.IN_PROGRESS: ("In progress", "In progress", "purple"),
    Status.REVIEW: ("In review", "In progress", "orange"),
    Status.ESCALATED: ("Needs a human", "In progress", "red"),
    Status.CLOSED: ("Closed", "Complete", "green"),
}
DEFAULT_AREAS = ["Frontend", "Backend", "Other"]


def status_map() -> dict[str, str]:
    return {s.value: label for s, (label, _, _) in STATUS_LABELS.items()}


YOU, BOT = "✏️ You: ", "🤖 autodev: "
AREA_COLORS = ["blue", "green", "purple", "orange", "pink", "brown", "yellow"]


def _select(*options: tuple[str, str]) -> dict:
    return {"select": {"options": [{"name": n, "color": c} for n, c in options]}}


def _describe(config: dict, text: str) -> dict:
    return {**config, "description": text}


# The columns autodev fills in carry its name, so that nobody has to guess whose they are: Notion has no read-only
# columns, and the name is the one thing shown everywhere (table, page, filters).
BOT_KEYS = ("attempts", "cost", "risk", "branch", "pr", "agent_note", "verification")
BOT_PREFIX = "autodev · "


def bot_properties() -> dict[str, str]:
    """Key -> column name for the columns autodev owns (what the project file's `tracker.properties` must say)."""
    return {k: BOT_PREFIX + DEFAULT_PROPERTIES[k] for k in BOT_KEYS}


def column_names() -> dict[str, str]:
    return {**DEFAULT_PROPERTIES, **bot_properties()}


def schema(areas: list[str] | None = None, models: list[str] | None = None) -> dict[str, dict]:
    """Column name -> Notion property config, with the names the code looks for (`DEFAULT_PROPERTIES`).

    You fill the first columns in (✏️); autodev fills the rest (🤖) and says so in the column description.
    """
    p = column_names()
    area_options = [(a, AREA_COLORS[i % len(AREA_COLORS)]) for i, a in enumerate(areas or DEFAULT_AREAS)]
    model_options = [("Auto", "gray"), *((m, "default") for m in (models or []))]
    return {
        p["title"]: _describe({"title": {}}, YOU + "a short description of the problem. Put the details in the page body (at least 40 characters)."),
        p["status"]: _describe(
            {"status": {"options": [{"name": n, "group": g, "color": c} for n, g, c in STATUS_LABELS.values()]}},
            "Leave it on New. autodev moves it along; you only change it to approve a fix (In progress) or to close the ticket (Closed).",
        ),
        p["authorized"]: _describe({"checkbox": {}}, YOU + "tick it to let autodev work on this ticket. Unticked tickets are ignored."),
        p["kind"]: _describe(_select(("Bug", "red"), ("Change", "blue"), ("Feature", "green"), ("Question", "purple")), YOU + "what kind of ticket this is."),
        p["area"]: _describe(_select(*area_options), YOU + "the part of the project it concerns. It helps triage find the right files."),
        p["priority"]: _describe(_select(("Low", "gray"), ("Medium", "yellow"), ("High", "orange"), ("Blocking", "red")), YOU + "(optional) how urgent it is."),
        p["environment"]: _describe(_select(("Production", "red"), ("Staging", "orange"), ("Local", "gray")), YOU + "(optional) where the problem happens."),
        p["page_url"]: _describe({"url": {}}, YOU + "(optional) the page of the app where it happens."),
        p["reported_by"]: _describe({"rich_text": {}}, YOU + "(optional) who reported it."),
        p["attachments"]: _describe({"files": {}}, YOU + "(optional) screenshots or example files. The agents can open images, PDFs and text files."),
        p["model"]: _describe(_select(*model_options), YOU + "(optional) the model for the fix. Auto lets autodev choose and retry with a stronger one."),
        p["risk"]: _describe(_select(("Low", "green"), ("Medium", "yellow"), ("High", "red")), BOT + "how risky the change is, set by triage. Do not edit."),
        p["attempts"]: _describe({"number": {}}, BOT + "how many times it tried to fix this ticket. Do not edit."),
        p["cost"]: _describe({"number": {"format": "dollar"}}, BOT + "what the agents have spent on this ticket, in dollars. Do not edit."),
        p["branch"]: _describe({"rich_text": {}}, BOT + "the git branch with the fix. Do not edit."),
        p["pr"]: _describe({"url": {}}, BOT + "the pull request with the fix. Do not edit."),
        p["agent_note"]: _describe({"rich_text": {}}, BOT + "why it stopped or what it did, in plain words. Do not edit."),
        p["verification"]: _describe(_select(("Not run", "gray"), ("Passed", "green"), ("Failed", "red")), BOT + "whether the project's checks passed on the fix. Do not edit."),
    }


LEGEND = (
    "How to use this board: add a ticket, fill in the columns you see here, and tick Authorized when autodev may work on it. "
    "The columns named 'autodev · …' are filled in by autodev, not by you: they are hidden here, and you can read them by opening a ticket."
)
TICKETS_VIEW = "Tickets"
LEGACY_VIEW = "autodev (all columns)"  # an earlier version also made this one; it is removed when found


def user_columns() -> list[str]:
    """The columns a person fills in or acts on, in the order they are shown."""
    p = DEFAULT_PROPERTIES
    return [p[k] for k in ("title", "authorized", "status", "kind", "area", "priority", "environment", "page_url", "reported_by", "attachments", "model")]


def _client(token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=API, timeout=30,
        headers={"Authorization": f"Bearer {token}", "Notion-Version": VERSION, "Content-Type": "application/json"},
    )


async def create_database(token: str, parent_page_id: str, title: str, areas: list[str] | None = None, models: list[str] | None = None) -> dict:
    """Creates the ticket database under a page shared with the integration; returns its two ids."""
    async with _client(token) as c:
        r = await c.post("/databases", json={
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"text": {"content": title}}],
            "description": [{"text": {"content": LEGEND}}],
            "initial_data_source": {"properties": schema(areas, models)},
        })
        r.raise_for_status()
        body = r.json()
    raw_id = body["data_sources"][0]["id"]
    await arrange_views(token, raw_id)
    return {"database_id": body["id"].replace("-", ""), "data_source_id": raw_id.replace("-", ""), "url": body.get("url")}


async def missing_properties(token: str, data_source_id: str) -> dict[str, dict]:
    """The columns of `schema()` that an existing data source does not have (by name)."""
    async with _client(token) as c:
        r = await c.get(f"/data_sources/{data_source_id}")
        r.raise_for_status()
        have = set(r.json()["properties"])
    return {name: cfg for name, cfg in schema().items() if name not in have}


async def add_properties(token: str, data_source_id: str, props: dict[str, dict]) -> None:
    async with _client(token) as c:
        r = await c.patch(f"/data_sources/{data_source_id}", json={"properties": props})
        r.raise_for_status()


async def shared_pages(token: str) -> list[dict]:
    """Pages the integration can see that can hold a new database (not rows of another database)."""
    async with _client(token) as c:
        r = await c.post("/search", json={"filter": {"property": "object", "value": "page"}, "page_size": 100})
        r.raise_for_status()
    pages = []
    for p in r.json()["results"]:
        if p["parent"].get("type") in ("data_source_id", "database_id"):
            continue
        title = "".join(x["plain_text"] for v in p["properties"].values() if v.get("type") == "title" for x in v["title"])
        pages.append({"id": p["id"], "title": title or "Untitled", "url": p.get("url")})
    return pages


async def data_source_of(token: str, database_id: str) -> str:
    async with _client(token) as c:
        r = await c.get(f"/databases/{database_id}")
        r.raise_for_status()
        return r.json()["data_sources"][0]["id"].replace("-", "")


FIXED_SELECTS = {column_names()[k] for k in ("kind", "priority", "environment", "risk", "verification")}


async def refresh_properties(token: str, data_source_id: str) -> list[str]:
    """Gives an existing database the descriptions (and colors of the fixed select lists) of `schema()`.

    Values already in tickets are kept: Status, Area and Model keep the user's own options, and only get a description.
    """
    async with _client(token) as c:
        r = await c.get(f"/data_sources/{data_source_id}")
        r.raise_for_status()
        have = set(r.json()["properties"])
        props = {}
        for name, cfg in schema().items():
            if name in have:
                kind = next(iter(cfg))
                # Notion wants the type in every update; an empty config for it leaves the column as it is
                props[name] = cfg if name in FIXED_SELECTS else {kind: {}, "description": cfg["description"]}
        if props:
            patch = await c.patch(f"/data_sources/{data_source_id}", json={"properties": props})
            patch.raise_for_status()
    return sorted(props)


async def arrange_views(token: str, data_source_id: str) -> None:
    """One view, "Tickets", showing only the columns a person fills in or acts on.

    Idempotent: the view is found by name (or is the database's first view, renamed), and a leftover
    "autodev (all columns)" view from an earlier version is deleted.
    """
    async with _client(token) as c:
        ds = await c.get(f"/data_sources/{data_source_id}")
        ds.raise_for_status()
        info = ds.json()
        ids = {name: p["id"] for name, p in info["properties"].items()}
        database_id = info["parent"]["database_id"] if info.get("parent", {}).get("type") == "database_id" else info["database_parent"]["database_id"]
        shown = [n for n in user_columns() if n in ids]
        order = shown + [n for n in ids if n not in shown]
        config = {"type": "table", "properties": [{"property_id": ids[n], "visible": n in shown} for n in order]}
        listing = await c.get("/views", params={"data_source_id": data_source_id})
        listing.raise_for_status()
        existing: dict[str, str] = {}
        for v in listing.json()["results"]:
            detail = await c.get(f"/views/{v['id']}")
            detail.raise_for_status()
            existing[detail.json()["name"]] = v["id"]
        if LEGACY_VIEW in existing:
            (await c.delete(f"/views/{existing.pop(LEGACY_VIEW)}")).raise_for_status()
        target = existing.get(TICKETS_VIEW) or next(iter(existing.values()), None)
        if target:
            r = await c.patch(f"/views/{target}", json={"name": TICKETS_VIEW, "configuration": config})
        else:
            r = await c.post("/views", json={"database_id": database_id, "data_source_id": data_source_id, "name": TICKETS_VIEW, "type": "table", "configuration": config})
        r.raise_for_status()


async def rename_legacy(token: str, data_source_id: str) -> list[str]:
    """Gives the columns autodev owns their prefixed names in a database created before there was one."""
    async with _client(token) as c:
        r = await c.get(f"/data_sources/{data_source_id}")
        r.raise_for_status()
        have = set(r.json()["properties"])
        renames = {DEFAULT_PROPERTIES[k]: new for k, new in bot_properties().items() if DEFAULT_PROPERTIES[k] in have and new not in have}
        if renames:
            patch = await c.patch(f"/data_sources/{data_source_id}", json={"properties": {old: {"name": new} for old, new in renames.items()}})
            patch.raise_for_status()
    return sorted(renames.values())
