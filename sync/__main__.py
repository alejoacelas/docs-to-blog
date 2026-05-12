"""Top-level entry point for the daily sync.

Order (per PLAN.md §7.4):

  1. Load config + creds. Hard-fail on missing before any API call.
  2. Probe Drive version. Exit 0 if both source and library are unchanged.
  3. Pull doc body + styling tab + library doc.
  4. Regenerate styles/generated.css via Call 1 (sync.css_gen).
  4b. (Implementation A only) Reconcile anchors via Call 2.
  4c. Run Call 4 (diff_review) final gate; persist verdict to
      .sync-verdict.json for the workflow's auto-merge step.
  5. Save the new Drive versions to .sync-state.json.

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
from sync.diff_review import review_diff, write_verdict_file  # noqa: E402
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
from sync.para_style_a import (  # noqa: E402
    ANCHORS_PATH,
    REPO_ROOT,
    read_prev_body_from_git,
    reconcile_from_disk,
    write_anchors_artifacts,
)

VERDICT_PATH = REPO_ROOT / ".sync-verdict.json"


def _git_show_head(path: Path) -> str:
    """Return the HEAD-version contents of `path`, or "" on miss.

    Used to assemble the prev-vs-new comparison for Call 4.
    """
    import subprocess

    try:
        rel = path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        rel = path
    try:
        result = subprocess.run(
            ["git", "show", f"HEAD:{rel}"],
            capture_output=True,
            text=True,
            check=False,
            cwd=REPO_ROOT,
        )
    except FileNotFoundError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout


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

    # 4b. Call 2 — Paragraph-styling reconciler (Implementation A only).
    # Per PLAN §7.4, the reconciler runs after fetch; the order vs. CSS
    # generation doesn't matter for correctness — both consume disk
    # outputs from fetch and produce committable artefacts.
    total_cost = result.cost_usd
    para_needs_attention = False
    para_needs_attention_reason: list[str] = []
    if cfg.doc.implementation == "a":
        para_result = reconcile_from_disk(
            new_doc=post_path.read_text(),
            project_styling=project_styling,
            library_styling=library_styling,
            post_path=post_path,
            fuzzy_threshold=cfg.anchoring.fuzzy_threshold,
            anchors_path=ANCHORS_PATH,
        )
        total_cost += para_result.cost_usd

        # Cost-cap check after the reconciler too.
        cost_cap = cfg.anchoring.max_cost_usd
        if total_cost >= cost_cap * 0.5:
            _log(
                "cost_warning",
                spent_usd=round(total_cost, 6),
                cap_usd=cost_cap,
            )
        if total_cost > cost_cap:
            print(
                f"cost cap exceeded after reconciler: spent ${total_cost:.4f}, cap ${cost_cap:.2f}",
                file=sys.stderr,
            )
            raise SystemExit(1)

        anchors_path, review_path = write_anchors_artifacts(para_result)
        _log(
            "wrote_anchors",
            path=str(anchors_path.relative_to(Path.cwd())),
            review_path=(
                str(review_path.relative_to(Path.cwd())) if review_path else None
            ),
            anchor_count=len(para_result.anchors),
            attempts=para_result.attempts,
            cost_usd=round(para_result.cost_usd, 6),
            needs_attention=para_result.needs_attention,
            review_concerns=para_result.review_concerns,
        )
        para_needs_attention = para_result.needs_attention
        para_needs_attention_reason = para_result.needs_attention_reason

        # Astro 5's content layer caches rendered HTML in
        # node_modules/.astro/data-store.json. Its cache key doesn't include
        # the remark plugins' source paths, so an updated anchors.yaml on
        # its own doesn't invalidate the cache — the next `astro build`
        # would serve stale HTML. Invalidate the store eagerly when we
        # rewrite anchors so the next build re-runs the remark pipeline.
        astro_cache = REPO_ROOT / "node_modules" / ".astro" / "data-store.json"
        if astro_cache.exists():
            astro_cache.unlink()
            _log("invalidated_astro_cache", path=str(astro_cache.relative_to(Path.cwd())))

    # 4c. Call 4 — diff reviewer (final gate). Always runs after the
    # upstream calls, regardless of whether they hit a needs-attention
    # state. Per CI-06 the workflow's auto-merge gate combines this
    # verdict with whether any upstream call exhausted retries.
    upstream_exhausted = (
        bool(result.needs_attention) or bool(para_needs_attention)
    )
    prev_body = read_prev_body_from_git(post_path)
    if cfg.doc.implementation == "a":
        artifact_label = "anchors.yaml"
        new_artifact = ANCHORS_PATH.read_text() if ANCHORS_PATH.exists() else ""
        prev_artifact = _git_show_head(ANCHORS_PATH)
    else:
        # B-side artifacts don't exist on this branch yet; this branch
        # ships A only. Phase 6 picks the winner; until then the
        # workflow on this branch always runs Implementation A.
        artifact_label = "decisions.md"
        new_artifact = ""
        prev_artifact = ""

    review_result = review_diff(
        prev_markdown=prev_body,
        new_markdown=post_path.read_text(),
        prev_artifact=prev_artifact,
        new_artifact=new_artifact,
        styling_text=project_styling,
        artifact_label=artifact_label,
    )
    total_cost += review_result.cost_usd
    if total_cost > cfg.anchoring.max_cost_usd:
        # Cost cap is advisory at this point — the gate already ran. Log
        # but do not abort: the artefacts are valid and committable.
        _log(
            "cost_warning",
            spent_usd=round(total_cost, 6),
            cap_usd=cfg.anchoring.max_cost_usd,
            note="cost cap exceeded after diff_review; not aborting (gate already ran)",
        )
    write_verdict_file(
        review_result,
        upstream_retry_exhausted=upstream_exhausted,
        path=VERDICT_PATH,
    )
    _log(
        "wrote_verdict",
        path=str(VERDICT_PATH.relative_to(Path.cwd())),
        auto_merge_ok=review_result.auto_merge_ok,
        concerns=review_result.concerns,
        upstream_retry_exhausted=upstream_exhausted,
        safe_to_auto_merge=review_result.auto_merge_ok and not upstream_exhausted,
        cost_usd=round(review_result.cost_usd, 6),
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
    verdict_summary = {
        "auto_merge_ok": review_result.auto_merge_ok,
        "concerns": review_result.concerns,
        "upstream_retry_exhausted": upstream_exhausted,
        "safe_to_auto_merge": review_result.auto_merge_ok and not upstream_exhausted,
    }
    _log(
        "done",
        elapsed_sec=elapsed,
        total_cost_usd=round(total_cost, 6),
        needs_attention=result.needs_attention or para_needs_attention,
        needs_attention_reason=[
            *result.needs_attention_reason,
            *para_needs_attention_reason,
        ],
        verdict=verdict_summary,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
