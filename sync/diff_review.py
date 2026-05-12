"""Call 4 — Diff reviewer (final gate, both implementations).

PLAN §7.2:
  - inputs: yesterday's full output (markdown + artifact); today's full
    output; styling tab text; the source doc diff;
  - output: structured `{ auto_merge_ok: bool, concerns: [string] }`;
  - deterministic validators: output parses as the expected schema;
  - no nested review pass — this *is* the review pass for the pipeline
    as a whole;
  - 1 retry only. On failure: default `auto_merge_ok = false`, let the
    human decide.

This is the *only* call without a bounded-retry budget of 3 — it's the
gate, not a transform. If the gate misfires twice in a row we trust the
human, not the model.
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from sync.llm import call_claude, estimate_cost_usd

MAX_ATTEMPTS = 2  # initial attempt + 1 retry, per spec


@dataclass
class DiffReviewResult:
    auto_merge_ok: bool
    concerns: list[str]
    attempts: int
    usage_totals: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    parsed_cleanly: bool = True


def _log(event: str, **fields) -> None:
    payload = {"stage": "diff_review", "event": event, **fields}
    print(json.dumps(payload), flush=True)


SYSTEM_PROMPT = """\
You are the final reviewer of a daily blog-sync pipeline. The pipeline
turned a Google Doc into static-site artifacts: markdown, an anchors or
decisions file, and a generated CSS file. Your only job is to decide
whether the whole run is safe to auto-merge without a human glancing at
the diff.

Output ONE JSON object on a single line, with no prose, no markdown, no
code fences:
  {"auto_merge_ok": true,  "concerns": []}
or
  {"auto_merge_ok": false, "concerns": ["<short concern 1>", ...]}

Return auto_merge_ok=false (with concerns) only when the diff looks
risky. Examples of risky:
- A paragraph that was clearly styled (e.g. "aside") in yesterday's
  output has silently lost its class while still existing in the new doc.
- The new CSS file removes rules for tags that still appear in the
  source doc.
- A class is applied to a paragraph whose content obviously does not
  match the prose definition in the styling tab.
- The doc diff is suspiciously large (entire sections rewritten) and the
  artifacts changed in ways that don't track that rewrite.

When the diff is small, well-tracked by the artifacts, and consistent
with the styling-tab prose, return auto_merge_ok=true with an empty
concerns list.

If genuinely uncertain, return auto_merge_ok=false — humans pay the cost
of a false negative, models pay nothing for a false positive.
"""


def compute_doc_diff(prev_doc: str, new_doc: str, *, context_lines: int = 3) -> str:
    """Plain unified diff of yesterday's body markdown vs today's.

    Sets fromfile/tofile to fixed labels so the prompt is byte-stable for
    identical inputs (helps any future prompt caching).
    """
    prev_lines = prev_doc.splitlines(keepends=True)
    new_lines = new_doc.splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            prev_lines,
            new_lines,
            fromfile="prev/body.md",
            tofile="new/body.md",
            n=context_lines,
        )
    )


def build_user_prompt(
    *,
    doc_diff: str,
    prev_markdown: str,
    new_markdown: str,
    prev_artifact: str,
    new_artifact: str,
    styling_text: str,
    artifact_label: str,
    prior_attempt: str | None = None,
    prior_issue: str | None = None,
) -> str:
    diff_block = doc_diff.strip() or "(no diff — first sync or unchanged body)"
    sections = [
        "STYLING TAB (prose definitions of every class):",
        "```",
        styling_text.strip() or "(empty)",
        "```",
        "",
        "SOURCE DOC DIFF (unified, prev → new):",
        "```diff",
        diff_block,
        "```",
        "",
        f"PREVIOUS {artifact_label}:",
        "```",
        prev_artifact.strip() or "(empty — first sync)",
        "```",
        "",
        f"NEW {artifact_label} (under review):",
        "```",
        new_artifact.strip() or "(empty)",
        "```",
        "",
        "PREVIOUS BODY MARKDOWN (committed at HEAD):",
        "```markdown",
        prev_markdown.strip() or "(empty — first sync)",
        "```",
        "",
        "NEW BODY MARKDOWN (just produced this run):",
        "```markdown",
        new_markdown.strip() or "(empty)",
        "```",
        "",
    ]
    if prior_attempt is not None:
        sections.extend(
            [
                "YOUR PREVIOUS ATTEMPT FAILED TO PARSE AS THE EXPECTED SCHEMA.",
                f"Issue: {prior_issue or 'output did not match {auto_merge_ok, concerns}'}",
                "Previous attempt (for reference):",
                "```",
                prior_attempt,
                "```",
                "",
            ]
        )
    sections.append(
        'Reply with exactly one JSON object: '
        '{"auto_merge_ok": <bool>, "concerns": [<str>, ...]}.'
    )
    return "\n".join(sections)


def _parse_verdict(text: str) -> dict | None:
    """Tolerant JSON extractor — accepts fenced or bare JSON, takes the
    first `{...}` block. Returns None if no parseable object is found.
    """
    t = text.strip()
    if t.startswith("```"):
        first_nl = t.find("\n")
        if first_nl >= 0:
            t = t[first_nl + 1 :]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3].rstrip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", t, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _validate_schema(payload: dict) -> tuple[bool, list[str], str | None]:
    """Return (auto_merge_ok, concerns, error_or_None).

    Schema: {"auto_merge_ok": bool, "concerns": [str, ...]}. Anything
    else is a schema error.
    """
    if not isinstance(payload, dict):
        return False, [], f"top-level must be an object, got {type(payload).__name__}"
    if "auto_merge_ok" not in payload:
        return False, [], "missing key `auto_merge_ok`"
    if "concerns" not in payload:
        return False, [], "missing key `concerns`"
    ok = payload["auto_merge_ok"]
    if not isinstance(ok, bool):
        return False, [], f"`auto_merge_ok` must be bool, got {type(ok).__name__}"
    concerns = payload["concerns"]
    if not isinstance(concerns, list) or not all(isinstance(c, str) for c in concerns):
        return False, [], "`concerns` must be a list of strings"
    return bool(ok), [str(c) for c in concerns], None


def review_diff(
    *,
    prev_markdown: str,
    new_markdown: str,
    prev_artifact: str,
    new_artifact: str,
    styling_text: str,
    artifact_label: str = "anchors.yaml",
) -> DiffReviewResult:
    """Run the Call 4 bounded transform with 1 retry.

    On any failure (parse, schema, API exception): default to
    `auto_merge_ok = false` with a concern explaining why.
    """
    doc_diff = compute_doc_diff(prev_markdown, new_markdown)

    usage_totals = {"input_tokens": 0, "output_tokens": 0}
    cost_total = 0.0
    last_text: str | None = None
    last_issue: str | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        prompt = build_user_prompt(
            doc_diff=doc_diff,
            prev_markdown=prev_markdown,
            new_markdown=new_markdown,
            prev_artifact=prev_artifact,
            new_artifact=new_artifact,
            styling_text=styling_text,
            artifact_label=artifact_label,
            prior_attempt=last_text,
            prior_issue=last_issue,
        )
        try:
            text, usage = call_claude(
                system=SYSTEM_PROMPT, user=prompt, max_tokens=600
            )
        except Exception as e:
            _log("api_error", attempt=attempt, error=str(e))
            last_issue = f"API error: {e!r}"
            last_text = ""
            continue

        usage_totals["input_tokens"] += usage["input_tokens"]
        usage_totals["output_tokens"] += usage["output_tokens"]
        cost = estimate_cost_usd(usage)
        cost_total += cost
        _log(
            "claude_call",
            call="diff_review",
            attempt=attempt,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            attempt_cost_usd=round(cost, 6),
        )

        payload = _parse_verdict(text)
        if payload is None:
            last_text = text
            last_issue = "response did not contain parseable JSON"
            _log("parse_failed", attempt=attempt, snippet=text[:160])
            continue

        ok, concerns, err = _validate_schema(payload)
        if err is not None:
            last_text = text
            last_issue = err
            _log("schema_failed", attempt=attempt, error=err)
            continue

        _log(
            "success",
            attempts=attempt,
            auto_merge_ok=ok,
            concerns=concerns,
            total_cost_usd=round(cost_total, 6),
        )
        return DiffReviewResult(
            auto_merge_ok=ok,
            concerns=concerns,
            attempts=attempt,
            usage_totals=usage_totals,
            cost_usd=cost_total,
            parsed_cleanly=True,
        )

    # Both attempts failed. Per spec: default to false, let human decide.
    _log(
        "exhausted",
        attempts=MAX_ATTEMPTS,
        last_issue=last_issue,
        total_cost_usd=round(cost_total, 6),
    )
    return DiffReviewResult(
        auto_merge_ok=False,
        concerns=[
            f"diff-review gate did not produce a parseable verdict after {MAX_ATTEMPTS} attempts: {last_issue}",
        ],
        attempts=MAX_ATTEMPTS,
        usage_totals=usage_totals,
        cost_usd=cost_total,
        parsed_cleanly=False,
    )


def write_verdict_file(
    result: DiffReviewResult,
    *,
    upstream_retry_exhausted: bool,
    path: Path,
) -> None:
    """Persist the verdict to disk for the workflow's auto-merge gate.

    Mirrors the merge gate's full logic so the workflow only has to read
    one bool (`safe_to_auto_merge`).
    """
    safe = result.auto_merge_ok and not upstream_retry_exhausted
    payload = {
        "auto_merge_ok": result.auto_merge_ok,
        "concerns": result.concerns,
        "upstream_retry_exhausted": upstream_retry_exhausted,
        "safe_to_auto_merge": safe,
        "attempts": result.attempts,
        "cost_usd": round(result.cost_usd, 6),
        "parsed_cleanly": result.parsed_cleanly,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
