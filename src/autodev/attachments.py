"""Ticket files for the agents: save what the tracker hosts on disk and tell the agent where it is.

The agents open them with Read (images, PDFs, text). To use one in the project, the fix agent copies it
(`cp`, which asks for permission unless the project allows it).
"""
import mimetypes
import re
import shutil
from pathlib import Path

import httpx

from autodev.db import DEFAULT_PATH
from autodev.models import Ticket

ROOT = DEFAULT_PATH.parent / "attachments"
MAX_FILES = 10
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 50 * 1024 * 1024


# shown in the browser as they are; anything else (HTML, SVG, ...) is only ever offered as a download
INLINE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"}


def folder(project: str, ticket_id: str) -> Path:
    return ROOT / re.sub(r"[^A-Za-z0-9_-]", "_", project) / re.sub(r"[^A-Za-z0-9_-]", "_", ticket_id)


def plan(refs: list[dict]) -> list[dict]:
    """The tracker's references with the name each one is saved under (`saved`, None for links), in a stable order."""
    taken: set[str] = set()
    return [{**ref, "saved": None if ref.get("external") else safe_name(ref["name"], taken)} for ref in refs]


async def ensure(item: dict, where: Path, client: httpx.AsyncClient) -> Path:
    """The saved file of a planned item, downloaded now if it is not on disk yet."""
    target = where / item["saved"]
    if not target.is_file():
        where.mkdir(parents=True, exist_ok=True)
        try:
            await _download(client, item["url"], target, MAX_FILE_BYTES)
        except Exception:
            target.unlink(missing_ok=True)
            raise
    return target


def safe_name(name: str, taken: set[str]) -> str:
    """A plain file name: no folders, no odd characters, never the same twice."""
    stem = re.sub(r"[^\w. -]", "_", Path(name).name).strip(" .") or "file"
    candidate, n = stem, 1
    while candidate in taken:
        n += 1
        candidate = f"{Path(stem).stem}-{n}{Path(stem).suffix}"
    taken.add(candidate)
    return candidate


def size_label(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB" if n >= 1024 * 1024 else f"{max(1, n // 1024)} KB"


async def _download(client: httpx.AsyncClient, url: str, target: Path, room: int) -> int:
    limit = min(MAX_FILE_BYTES, room)
    size = 0
    async with client.stream("GET", url, follow_redirects=True) as r:
        r.raise_for_status()
        if int(r.headers.get("content-length") or 0) > limit:
            raise ValueError(f"larger than {size_label(limit)}")
        with target.open("wb") as out:
            async for chunk in r.aiter_bytes():
                size += len(chunk)
                if size > limit:
                    raise ValueError(f"larger than {size_label(limit)}")
                out.write(chunk)
    return size


async def attach(tracker, ticket: Ticket, project: str, client: httpx.AsyncClient | None = None) -> None:
    """Saves the ticket's files and fills `ticket.files` / `ticket.file_notes`. Never raises: a missing file must not stop a run."""
    ticket.files, ticket.file_notes = [], []
    if not hasattr(tracker, "attachments"):
        return
    try:
        refs = await tracker.attachments(ticket.id)
    except Exception as e:
        ticket.file_notes.append(f"The attachments could not be read from the tracker ({e}).")
        return
    if not refs:
        return
    where = folder(project, ticket.id)
    shutil.rmtree(where, ignore_errors=True)
    where.mkdir(parents=True)
    # the signed URLs carry their own access: no tracker credentials may go with them
    own = client or httpx.AsyncClient(timeout=60)
    total = 0
    try:
        for ref in plan(refs):
            if ref.get("external"):
                ticket.file_notes.append(f"{ref['name']}: a link, not downloaded ({ref['url']})")
            elif len(ticket.files) >= MAX_FILES:
                ticket.file_notes.append(f"{ref['name']}: skipped, more than {MAX_FILES} files")
            else:
                target = where / ref["saved"]
                try:
                    size = await _download(own, ref["url"], target, MAX_TOTAL_BYTES - total)
                except Exception as e:
                    target.unlink(missing_ok=True)
                    ticket.file_notes.append(f"{ref['name']}: not downloaded ({e})")
                    continue
                total += size
                ticket.files.append({"name": ref["name"], "path": str(target), "size": size, "type": mimetypes.guess_type(target.name)[0] or "unknown"})
    finally:
        if client is None:
            await own.aclose()


def folders(ticket: Ticket) -> list[str]:
    """Where the agent may read the files from (`add_dirs`)."""
    return sorted({str(Path(f["path"]).parent) for f in ticket.files})


def prompt_section(ticket: Ticket) -> str:
    if not ticket.files and not ticket.file_notes:
        return f"Attachments: {', '.join(ticket.attachments) or 'none'}"
    lines = ["Attachments:"]
    for f in ticket.files:
        lines.append(f"- {f['name']} ({f['type']}, {size_label(f['size'])}): {f['path']}")
    lines += [f"- {n}" for n in ticket.file_notes]
    if ticket.files:
        lines.append(
            "Open them with Read (it shows images and PDFs and reads text files). To use one in the project, "
            "for example as a test fixture, copy it into the repository with `cp <path> <destination>`."
        )
    return "\n".join(lines)
