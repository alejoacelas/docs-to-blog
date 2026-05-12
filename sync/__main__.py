"""Top-level entry point for the daily sync.

Order (per PLAN.md §7.4 + Phase 2 success criteria):

  1. Load config + creds. Hard-fail on missing before any API call.
  2. Probe Drive version. Exit 0 if both source and library are unchanged.
  3. Pull doc body + styling tab + library doc.
  4. Regenerate styles/generated.css via Call 1 (sync.css_gen).
  5. Save the new Drive versions to .sync-state.json.

Phase 2 stops at the CSS step. Phases 3+ extend this entry point with
the span plugin and the paragraph-styling reconcilers.

Each step emits a structured JSON log line to stdout. Errors print a
descriptive message to stderr before exiting non-zero.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from sync.config import load_config  # noqa: E402
from sync.css_gen import generate_css, write_generated_css  # noqa: E402
from sync.fetch import (  # noqa: E402
    SyncState,
    drive_version,
    load_state,
    pull_doc_body,
    pull_library,
    pull_styling_tab,
    save_state,
    write_body_markdown,
)
from sync.llm import estimate_cost_usd  # noqa: E402


def _log(event: str, **fields) -> None:
    payload = {"stage": "main", "event": event, **fields}
    print(json.dumps(payload), flush=True)


def _ensure_creds() -> None:
    """Verify creds + state files exist before any API call."""
    missing: list[str] = []
    if not os.getenv("ANTHROPIC_API_KEY", "").strip():
        missing.append("ANTHROPIC_API_KEY (env)")
    gdoc_token = Path(
        os.getenv("GDOC_TOKEN_PATH", "~/.config/gdoc/token.json")
    ).expanduser()
    if not gdoc_token.exists():
        missing.append(f"gdoc token at {gdoc_token}")
    if missing:
        msg = "missing prerequisites:\n  - " + "\n  - ".join(missing)
        print(msg, file=sys.stderr)
        raise SystemExit(1)


def main() -> int:
    started = time.time()
    _log("start")

    _ensure_creds()

    cfg = load_config()
    _log(
        "config_loaded",
        implementation=cfg.doc.implementation,
        deploy_target=cfg.deploy.target,
    )

    # 2. Drive version probe
    new_doc_version = drive_version(cfg.doc.url)
    new_lib_version = drive_version(cfg.doc.library_url)
    state = load_state()
    _log(
        "drive_probe",
        doc_version=new_doc_version,
        library_version=new_lib_version,
        prior_doc_version=state.doc_version if state else None,
        prior_library_version=state.library_version if state else None,
    )

    if (
        state is not None
        and state.doc_version == new_doc_version
        and state.library_version == new_lib_version
    ):
        _log("no_op_exit", elapsed_sec=round(time.time() - started, 3))
        return 0

    # 3. Pull content
    body_md = pull_doc_body(cfg.doc.url, styling_tab_title=cfg.doc.styling_tab_title)
    project_styling = pull_styling_tab(cfg.doc.url, cfg.doc.styling_tab_title)
    library_body, library_styling = pull_library(
        cfg.doc.library_url, styling_tab_title=cfg.doc.styling_tab_title
    )
    _ = library_body  # library body is used by phase 3+ (span gallery)
    _log(
        "pulled",
        body_chars=len(body_md),
        project_styling_chars=len(project_styling),
        library_styling_chars=len(library_styling),
    )

    # Persist the body markdown. v1 has one source doc → fixed slug.
    post_path = write_body_markdown(body_md, slug="hello")
    _log("wrote_post", path=str(post_path.relative_to(Path.cwd())))

    # 4. Call 1 — CSS generator
    result = generate_css(
        project_styling=project_styling,
        library_styling=library_styling,
    )

    # Cost-cap warning
    cost_cap = cfg.anchoring.max_cost_usd
    if result.cost_usd >= cost_cap * 0.5:
        _log("cost_warning", spent_usd=round(result.cost_usd, 6), cap_usd=cost_cap)
    if result.cost_usd > cost_cap:
        print(
            f"cost cap exceeded: spent ${result.cost_usd:.4f}, cap ${cost_cap:.2f}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    css_path = write_generated_css(result.css)
    _log(
        "wrote_css",
        path=str(css_path.relative_to(Path.cwd())),
        attempts=result.attempts,
        bytes=len(result.css),
        cost_usd=round(result.cost_usd, 6),
        needs_attention=result.needs_attention,
        needs_attention_reason=result.needs_attention_reason,
    )

    # 5. Save state
    new_state = SyncState(
        doc_version=new_doc_version,
        library_version=new_lib_version,
    )
    save_state(new_state)
    _log(
        "saved_state",
        doc_version=new_state.doc_version,
        library_version=new_state.library_version,
    )

    elapsed = round(time.time() - started, 3)
    _log("done", elapsed_sec=elapsed, total_cost_usd=round(result.cost_usd, 6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
