"""Fetch stage of the daily sync.

Pulls the body markdown, styling tab, and library doc (body + styling) from
Google Docs via the `gdoc` CLI, and probes Drive's `files.get(version)` to
detect no-op runs.

Design notes:
- `gdoc cat <url>` returns the full doc as rich markdown, but concatenates
  every tab. To isolate the body, we slice everything before the first
  occurrence of `# {styling_tab_title}` (case-insensitive). The styling tab
  is fetched separately via `gdoc cat --tab <title> --plain` (plain text,
  per PLAN.md §1 — tab-scoped export is plain only). This is the v1
  simplification mentioned in the Phase 2 handoff: `gdoc cat --tab styling
  --plain` satisfies SYNC-02 ("returns its plain-text content") without
  needing direct Docs API access.
- The library doc is read the same way: full body via `gdoc cat`, styling
  tab via `--tab <title> --plain`.
- Drive version probe uses the gdoc OAuth token directly with google-api-
  python-client; no separate auth flow needed.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = REPO_ROOT / "src" / "content" / "posts"
STATE_PATH = REPO_ROOT / ".sync-state.json"

GDOC_TOKEN_PATH = Path(
    os.getenv("GDOC_TOKEN_PATH", "~/.config/gdoc/token.json")
).expanduser()
GDOC_CREDENTIALS_PATH = Path(
    os.getenv("GDOC_CREDENTIALS_PATH", "~/.config/gdoc/credentials.json")
).expanduser()

DOC_ID_RE = re.compile(r"/document/d/([a-zA-Z0-9_-]+)")


@dataclass(frozen=True)
class SyncState:
    doc_version: int
    library_version: int

    def to_dict(self) -> dict:
        return {"doc_version": self.doc_version, "library_version": self.library_version}


def state_file_path() -> Path:
    return STATE_PATH


def load_state() -> SyncState | None:
    if not STATE_PATH.exists():
        return None
    try:
        raw = json.loads(STATE_PATH.read_text())
        return SyncState(
            doc_version=int(raw.get("doc_version", 0)),
            library_version=int(raw.get("library_version", 0)),
        )
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def save_state(state: SyncState) -> None:
    STATE_PATH.write_text(json.dumps(state.to_dict(), indent=2) + "\n")


def _log(event: str, **fields) -> None:
    payload = {"stage": "fetch", "event": event, **fields}
    print(json.dumps(payload), flush=True)


def _run_gdoc(args: list[str]) -> str:
    """Run gdoc with stdout captured; stderr discarded (banner noise).

    Caller is responsible for `--plain`/`--quiet` flags as appropriate.
    """
    try:
        result = subprocess.run(
            ["gdoc", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
    except FileNotFoundError as e:
        raise SystemExit(
            "gdoc CLI not found on PATH. Install it or fix PATH before running sync."
        ) from e
    except subprocess.CalledProcessError as e:
        raise SystemExit(
            f"gdoc command failed (args={args!r}, exit={e.returncode}):\n{e.stderr}"
        ) from e
    return result.stdout


def _extract_doc_id(url: str) -> str:
    m = DOC_ID_RE.search(url)
    if not m:
        raise SystemExit(f"Could not extract Google Doc ID from URL: {url!r}")
    return m.group(1)


def pull_doc_body(url: str, styling_tab_title: str = "styling") -> str:
    """Return the doc body as markdown, with the styling tab sliced off.

    `gdoc cat <url>` (default, no --tab) returns rich markdown but
    concatenates all tabs. Tab-scoped export drops markdown formatting
    (headings become plain lines), so we can't ask for the body tab
    directly. Instead we cut everything from the first `# {styling_tab_title}`
    heading onward.
    """
    raw = _run_gdoc(["cat", "--quiet", url])
    body = _slice_before_styling_heading(raw, styling_tab_title)
    return body


def _slice_before_styling_heading(markdown: str, styling_tab_title: str) -> str:
    """Drop everything from the first `# {styling_tab_title}` heading onward.

    Also strips a leading `# Tab 1` (or similar single-line H1 that equals
    the body tab title) since it's a gdoc artefact, not author content.
    """
    pattern = re.compile(
        rf"^#\s+{re.escape(styling_tab_title)}\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    m = pattern.search(markdown)
    body = markdown[: m.start()] if m else markdown

    # Strip a leading "# <something>" line if it looks like a tab-title artefact
    # (no useful author content before the first H2). The body tab is usually
    # auto-named "Tab 1" and emitted as a top-level H1 by gdoc.
    lines = body.splitlines()
    if lines and lines[0].startswith("# "):
        # Check the next non-empty line — if it's an H1 too, the first is the
        # tab title artefact; keep the second.
        first_h1 = lines[0]
        for line in lines[1:]:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("# ") and not stripped.startswith("## "):
                lines = lines[1:]
            break
        # Re-strip leading blanks
        while lines and not lines[0].strip():
            lines.pop(0)
        _ = first_h1  # silence linter; we may want to log this later

    return "\n".join(lines).rstrip() + "\n"


def pull_styling_tab(url: str, tab: str) -> str:
    """Return the styling tab as plain text.

    If the tab doesn't exist, log a warning and return empty string.
    """
    try:
        text = _run_gdoc(["cat", "--quiet", "--tab", tab, "--plain", url])
    except SystemExit as e:
        _log("styling_tab_missing", url=url, tab=tab, error=str(e))
        return ""
    return text.strip() + "\n" if text.strip() else ""


def pull_library(url: str, styling_tab_title: str = "styling") -> tuple[str, str]:
    """Pull the library doc's body and styling tab.

    Returns (body_markdown, styling_text).
    """
    body = pull_doc_body(url, styling_tab_title=styling_tab_title)
    styling = pull_styling_tab(url, styling_tab_title)
    return body, styling


def _load_credentials() -> Credentials:
    if not GDOC_TOKEN_PATH.exists():
        raise SystemExit(
            f"gdoc token not found at {GDOC_TOKEN_PATH}. "
            "Set GDOC_TOKEN_PATH or run `gdoc auth`."
        )
    token_data = json.loads(GDOC_TOKEN_PATH.read_text())
    return Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri"),
        client_id=token_data.get("client_id"),
        client_secret=token_data.get("client_secret"),
        scopes=token_data.get("scopes"),
    )


def drive_version(doc_url: str) -> int:
    """Probe the Drive version of a Google Doc.

    Returns the monotonic integer version. Caller compares against the
    saved state to decide whether to short-circuit.
    """
    doc_id = _extract_doc_id(doc_url)
    creds = _load_credentials()
    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    metadata = (
        service.files()
        .get(fileId=doc_id, fields="version,modifiedTime")
        .execute()
    )
    return int(metadata["version"])


def write_body_markdown(body: str, slug: str = "hello", title: str | None = None) -> Path:
    """Write the doc body into src/content/posts/<slug>.md with frontmatter.

    For v1 we have one source doc and use a fixed slug. Title is extracted
    from the first H1 if not provided.
    """
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)

    if title is None:
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                title = stripped[2:].strip()
                break
        if title is None:
            title = "Untitled"

    # Strip the first H1 from the body (it's the title, now in frontmatter).
    body_lines = body.splitlines()
    new_lines: list[str] = []
    h1_dropped = False
    for line in body_lines:
        if not h1_dropped and line.strip().startswith("# ") and not line.strip().startswith("## "):
            h1_dropped = True
            continue
        new_lines.append(line)
    body_no_title = "\n".join(new_lines).lstrip("\n").rstrip() + "\n"

    # Always use today's date in the local TZ; the date is metadata for ordering.
    from datetime import date as _date
    today = _date.today().isoformat()

    frontmatter = f"---\ntitle: {json.dumps(title)}\ndate: {today}\n---\n\n"
    path = CONTENT_DIR / f"{slug}.md"
    path.write_text(frontmatter + body_no_title)
    return path


if __name__ == "__main__":
    # Smoke probe — print the version of the doc passed as arg
    if len(sys.argv) < 2:
        print("usage: python -m sync.fetch <doc_url>", file=sys.stderr)
        sys.exit(2)
    print(drive_version(sys.argv[1]))
