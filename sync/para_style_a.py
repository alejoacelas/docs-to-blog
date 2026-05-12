"""Call 2 — Paragraph-styling reconciler, Implementation A.

PLAN §7.2:
  - inputs: prev doc body, new doc body, current anchors.yaml, styling
    tab, library styling tab, fuzzy candidate matches (hint, not
    directive);
  - output: new anchors.yaml;
  - deterministic validators: parses as YAML; every class referenced is
    defined in the styling tab or library; every quote.exact is a
    verbatim substring of the new doc; every ordinal is reachable;
    every hash matches the matched paragraph;
  - review pass: a second Claude call flags silent class loss and class
    mismatches against the styling tab's prose;
  - bounded retry: 3 main attempts; review pass adds 1 more call per
    accepted attempt;
  - first sync (no prev doc, no prev anchors) is the same call path —
    Claude proposes from scratch.

The fuzzy matcher in sync/anchors.py runs as a pre-pass and goes into
the prompt as a hint — Claude is the decider.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from sync.anchors import (
    Anchor,
    FuzzyCandidate,
    Quote,
    compute_paragraph_hash,
    dumps_anchors,
    extract_paragraphs_with_headings,
    find_paragraph,
    fuzzy_match_candidates,
    load_anchors,
    save_anchors,
)
from sync.css_gen import extract_tag_names
from sync.llm import call_claude, estimate_cost_usd

REPO_ROOT = Path(__file__).resolve().parent.parent
STYLES_DIR = REPO_ROOT / "styles"
ANCHORS_PATH = STYLES_DIR / "anchors.yaml"
ANCHORS_REVIEW_PATH = STYLES_DIR / "anchors_review.yaml"
CONTENT_DIR = REPO_ROOT / "src" / "content" / "posts"

MAX_ATTEMPTS = 3


@dataclass
class ReconcileResult:
    anchors: list[Anchor]
    attempts: int
    usage_totals: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    review_ran: bool = False
    review_passed: bool | None = None
    review_concerns: list[str] = field(default_factory=list)
    needs_attention: bool = False
    needs_attention_reason: list[str] = field(default_factory=list)


def _log(event: str, **fields) -> None:
    payload = {"stage": "para_style_a", "event": event, **fields}
    print(json.dumps(payload), flush=True)


# ---------------------------------------------------------------------------
# Validators


class ValidationError(Exception):
    pass


def _parse_yaml(text: str) -> dict:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValidationError(f"YAML parse error: {e}") from e
    if data is None:
        return {"paragraphs": []}
    if not isinstance(data, dict):
        raise ValidationError(f"top-level must be a mapping, got {type(data).__name__}")
    if "paragraphs" not in data:
        raise ValidationError("missing top-level `paragraphs` key")
    if not isinstance(data["paragraphs"], list):
        raise ValidationError("`paragraphs` must be a list")
    return data


def _coerce_anchors(data: dict) -> list[Anchor]:
    out: list[Anchor] = []
    for i, raw in enumerate(data["paragraphs"]):
        if not isinstance(raw, dict):
            raise ValidationError(f"paragraphs[{i}] must be a mapping")
        if "class" not in raw:
            raise ValidationError(f"paragraphs[{i}] missing `class`")
        anc = raw.get("anchor")
        if not isinstance(anc, dict):
            raise ValidationError(f"paragraphs[{i}] missing `anchor` mapping")
        for key in ("quote", "heading", "ordinal", "hash"):
            if key not in anc:
                raise ValidationError(f"paragraphs[{i}].anchor missing `{key}`")
        try:
            out.append(Anchor.from_dict(raw))
        except (KeyError, TypeError, ValueError) as e:
            raise ValidationError(f"paragraphs[{i}]: {e}") from e
    return out


def validate_anchors(
    anchors: list[Anchor],
    new_doc: str,
    known_classes: set[str],
) -> None:
    """Run every deterministic validator. Raises ValidationError on the
    first failure (with a message that identifies the offending anchor).
    """
    new_paragraphs = extract_paragraphs_with_headings(new_doc)

    # Build a fast lookup: (heading, ordinal) → Paragraph
    by_position: dict[tuple[str, int], object] = {
        (p.heading, p.ordinal): p for p in new_paragraphs
    }

    errors: list[str] = []
    seen_positions: set[tuple[str, int]] = set()

    for idx, a in enumerate(anchors):
        label = f"paragraphs[{idx}] (class={a.cls!r}, heading={a.heading!r}, ord={a.ordinal})"

        if a.cls not in known_classes:
            errors.append(
                f"{label}: class {a.cls!r} not in styling tab or library "
                f"(known: {sorted(known_classes)})"
            )
            continue

        if not a.quote.exact.strip():
            errors.append(f"{label}: quote.exact is empty")
            continue

        if a.quote.exact not in new_doc:
            errors.append(
                f"{label}: quote.exact is not a verbatim substring of the new doc"
            )
            continue

        para = by_position.get((a.heading, a.ordinal))
        if para is None:
            errors.append(
                f"{label}: ordinal {a.ordinal} unreachable under heading {a.heading!r} "
                f"(no Nth paragraph there)"
            )
            continue

        expected_hash = compute_paragraph_hash(para.text)
        if a.hash != expected_hash:
            errors.append(
                f"{label}: hash mismatch — got {a.hash!r}, "
                f"paragraph at ({a.heading!r}, {a.ordinal}) hashes to {expected_hash!r}"
            )
            continue

        # quote.exact must actually appear in the matched paragraph.
        if a.quote.exact not in para.text and a.quote.exact not in para.normalised:
            errors.append(
                f"{label}: quote.exact appears in the doc but not in the matched paragraph"
            )
            continue

        if (a.heading, a.ordinal) in seen_positions:
            errors.append(
                f"{label}: duplicate anchor on the same (heading, ordinal) — only one class per paragraph"
            )
            continue
        seen_positions.add((a.heading, a.ordinal))

    if errors:
        raise ValidationError("; ".join(errors))


# ---------------------------------------------------------------------------
# Prompt assembly


SYSTEM_PROMPT = """\
You are the paragraph-styling reconciler for a static blog generated
from a Google Doc. Your job: given the previous doc body, the new doc
body, the previous anchors.yaml, the styling tab, and a fuzzy
matcher's candidate matches, produce a fresh anchors.yaml that names
which paragraphs should receive which CSS class in the new doc.

YOU MUST OUTPUT ONE YAML DOCUMENT inside a fenced code block, like:

```yaml
paragraphs:
  - class: <class-name>
    anchor:
      quote:
        exact: "<a verbatim substring of the matched paragraph>"
        prefix: "<optional, omit if not needed>"
        suffix: "<optional, omit if not needed>"
      heading: "<the nearest heading above the paragraph>"
      ordinal: <1-indexed Nth paragraph under that heading>
      hash: "<8-char sha256 prefix of the paragraph's normalised text>"
```

Hard rules:
- `quote.exact` MUST be a verbatim substring of the NEW doc, taken from
  the paragraph being anchored. Pick a span long enough to be unique
  (around 30-80 characters is usually right).
- `heading` is the nearest `#`/`##`/`###` heading above the paragraph in
  the markdown. Use the heading text verbatim (no leading `#`). For
  paragraphs that sit before any heading, use an empty string.
- `ordinal` counts only paragraphs (not headings, not code fences) under
  that heading, starting at 1.
- `hash` is the 8-char sha256 prefix of the paragraph's text with
  whitespace runs collapsed and ends stripped — i.e. of the same
  canonical form the validator computes. If you can't compute the hash
  exactly, leave it as the hash of the original paragraph text you can
  see; the validator will reject if you're wrong and we'll retry.
- Only use class names that appear in the styling tab or the library
  styling tab.
- At most one anchor per paragraph (one (heading, ordinal) pair).
- If a previously-styled paragraph still exists (possibly edited), keep
  its class unless the styling reason no longer applies. If it was
  deleted, drop its anchor. If a new paragraph deserves a class (per
  the styling tab's prose), add an anchor.
- The fuzzy candidates are HINTS — they tell you which previous anchors
  the matcher thinks correspond to which new paragraphs. You may
  override them.

No prose, no commentary outside the fenced YAML block.
"""


def build_user_prompt(
    *,
    prev_doc: str,
    new_doc: str,
    prev_anchors: list[Anchor],
    fuzzy_candidates: list[FuzzyCandidate],
    project_styling: str,
    library_styling: str,
    prior_attempt: str | None = None,
    prior_issues: list[str] | None = None,
) -> str:
    fuzzy_table = _format_fuzzy_table(fuzzy_candidates)
    new_paragraphs = extract_paragraphs_with_headings(new_doc)
    para_index = _format_paragraph_index(new_paragraphs)

    sections = [
        "PROJECT STYLING TAB (defines which classes mean what):",
        "```",
        project_styling.strip() or "(empty)",
        "```",
        "",
        "LIBRARY STYLING TAB (shared definitions):",
        "```",
        library_styling.strip() or "(empty)",
        "```",
        "",
        "PREVIOUS DOC BODY (markdown, may be empty on first sync):",
        "```markdown",
        prev_doc.strip() or "(empty — first sync)",
        "```",
        "",
        "NEW DOC BODY (markdown — the document you are anchoring):",
        "```markdown",
        new_doc.strip(),
        "```",
        "",
        "NEW DOC PARAGRAPH INDEX (heading, ordinal → first 80 chars):",
        "```",
        para_index,
        "```",
        "",
        "PREVIOUS ANCHORS YAML (may be empty on first sync):",
        "```yaml",
        dumps_anchors(prev_anchors).strip() or "paragraphs: []",
        "```",
        "",
        "FUZZY MATCHER HINTS (which prior anchor each prior paragraph likely is now):",
        "```",
        fuzzy_table or "(no prior anchors or no matches)",
        "```",
        "",
    ]
    if prior_attempt is not None:
        sections.extend(
            [
                "YOUR PREVIOUS ATTEMPT FAILED. Issues to fix:",
                *(f"- {i}" for i in (prior_issues or [])),
                "",
                "Previous attempt (for reference; produce a corrected version):",
                "```yaml",
                prior_attempt,
                "```",
                "",
            ]
        )
    sections.append(
        "Produce the corrected, complete anchors.yaml now. "
        "Output exactly one ```yaml ... ``` fenced block — nothing else."
    )
    return "\n".join(sections)


def _format_fuzzy_table(candidates: list[FuzzyCandidate]) -> str:
    if not candidates:
        return ""
    rows = ["prior_hash  new_heading -> new_ordinal  confidence  new_hash"]
    for c in candidates:
        rows.append(
            f"{c.prior_anchor_hash}    {c.candidate_heading!r} -> {c.candidate_ordinal}    "
            f"{c.confidence:.2f}    {c.candidate_hash}"
        )
    return "\n".join(rows)


def _format_paragraph_index(paragraphs) -> str:
    if not paragraphs:
        return "(no paragraphs)"
    rows: list[str] = []
    for p in paragraphs:
        snippet = re.sub(r"\s+", " ", p.text)[:80]
        rows.append(f"({p.heading!r:>30}, {p.ordinal:>2})  {p.hash}  {snippet}")
    return "\n".join(rows)


def _extract_yaml_block(text: str) -> str:
    """Pull the first ```yaml ... ``` block out of `text`. If the LLM
    forgets the fence, fall back to the whole text."""
    m = re.search(r"```(?:yaml|yml)?\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text.strip()


# ---------------------------------------------------------------------------
# Review pass


REVIEW_SYSTEM = """\
You review a freshly-generated anchors.yaml against the previous and new
doc bodies and the styling tab.

Output ONE JSON object on a single line:
  {"ok": true,  "concerns": []}
or
  {"ok": false, "concerns": ["<short concern 1>", ...]}

Flag ONLY:
(a) A previously-styled paragraph that still exists in some form in the
    new doc (you can identify it by its substring or nearby context)
    and has SILENTLY lost its class — no anchor in the new yaml points
    to it. Skip when the paragraph genuinely disappeared.
(b) A class applied to a paragraph that clearly does not match the
    style's prose description in the styling tab. (e.g. styling tab
    says `aside` = reflective tangent, but the anchor is on the main
    thesis statement.)

Do NOT flag taste, alternative class choices, or anchors that are
defensible. When in doubt, return ok: true with no concerns.
"""


def _review_pass(
    prev_doc: str,
    new_doc: str,
    prev_anchors: list[Anchor],
    new_anchors: list[Anchor],
    project_styling: str,
    library_styling: str,
) -> tuple[bool, list[str], dict]:
    user = "\n".join(
        [
            "PROJECT STYLING TAB:",
            "```",
            project_styling.strip() or "(empty)",
            "```",
            "",
            "LIBRARY STYLING TAB:",
            "```",
            library_styling.strip() or "(empty)",
            "```",
            "",
            "PREVIOUS DOC BODY:",
            "```markdown",
            prev_doc.strip() or "(empty)",
            "```",
            "",
            "NEW DOC BODY:",
            "```markdown",
            new_doc.strip(),
            "```",
            "",
            "PREVIOUS ANCHORS:",
            "```yaml",
            dumps_anchors(prev_anchors).strip() or "paragraphs: []",
            "```",
            "",
            "NEW ANCHORS (under review):",
            "```yaml",
            dumps_anchors(new_anchors).strip() or "paragraphs: []",
            "```",
            "",
            'Reply with exactly one line of JSON, e.g. {"ok": true, "concerns": []}',
        ]
    )
    text, usage = call_claude(system=REVIEW_SYSTEM, user=user, max_tokens=800)
    payload = _coerce_review_json(text)
    if payload is None:
        # Same posture as css_gen: a malformed review reply degrades to a
        # soft pass with a concern logged.
        return True, [f"review-pass response not JSON; skipping (got: {text[:120]!r})"], usage
    ok = bool(payload.get("ok"))
    concerns = list(payload.get("concerns") or [])
    return ok, concerns, usage


def _coerce_review_json(text: str) -> dict | None:
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


# ---------------------------------------------------------------------------
# Orchestration


def reconcile(
    *,
    prev_doc: str,
    new_doc: str,
    prev_anchors: list[Anchor],
    project_styling: str,
    library_styling: str,
    fuzzy_threshold: float = 0.8,
    run_review: bool = True,
    max_attempts: int = MAX_ATTEMPTS,
) -> ReconcileResult:
    """Bounded-transform loop. Returns a validated set of anchors. On
    retry exhaustion, raises SystemExit(1) per IMPL-A-04 — no silent
    fallback to prev anchors."""

    project_tags = extract_tag_names(project_styling)
    library_tags = extract_tag_names(library_styling)
    known_classes = set(project_tags) | set(library_tags)

    new_paragraphs = extract_paragraphs_with_headings(new_doc)
    fuzzy = fuzzy_match_candidates(
        prev_anchors, new_paragraphs, threshold=fuzzy_threshold
    )
    _log(
        "fuzzy_prepass",
        prior_anchor_count=len(prev_anchors),
        new_paragraph_count=len(new_paragraphs),
        candidate_count=len(fuzzy),
    )

    usage_totals: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
    cost_total = 0.0

    last_attempt: str | None = None
    last_issues: list[str] = []
    last_validated_anchors: list[Anchor] | None = None
    last_validated_text: str | None = None
    last_validated_concerns: list[str] = []
    review_ran = False
    review_passed: bool | None = None
    review_concerns: list[str] = []

    for attempt in range(1, max_attempts + 1):
        prompt = build_user_prompt(
            prev_doc=prev_doc,
            new_doc=new_doc,
            prev_anchors=prev_anchors,
            fuzzy_candidates=fuzzy,
            project_styling=project_styling,
            library_styling=library_styling,
            prior_attempt=last_attempt,
            prior_issues=last_issues or None,
        )
        text, usage = call_claude(system=SYSTEM_PROMPT, user=prompt, max_tokens=8000)
        usage_totals["input_tokens"] += usage["input_tokens"]
        usage_totals["output_tokens"] += usage["output_tokens"]
        cost = estimate_cost_usd(usage)
        cost_total += cost
        _log(
            "claude_call",
            call="para_style_a",
            attempt=attempt,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            attempt_cost_usd=round(cost, 6),
        )

        yaml_text = _extract_yaml_block(text)

        try:
            data = _parse_yaml(yaml_text)
            anchors = _coerce_anchors(data)
            validate_anchors(anchors, new_doc=new_doc, known_classes=known_classes)
        except ValidationError as e:
            _log("validator_failed", attempt=attempt, error=str(e))
            last_attempt = yaml_text
            last_issues = [str(e)]
            continue

        if run_review:
            review_ran = True
            ok, concerns, review_usage = _review_pass(
                prev_doc=prev_doc,
                new_doc=new_doc,
                prev_anchors=prev_anchors,
                new_anchors=anchors,
                project_styling=project_styling,
                library_styling=library_styling,
            )
            usage_totals["input_tokens"] += review_usage["input_tokens"]
            usage_totals["output_tokens"] += review_usage["output_tokens"]
            review_cost = estimate_cost_usd(review_usage)
            cost_total += review_cost
            _log(
                "claude_call",
                call="para_style_a_review",
                attempt=attempt,
                input_tokens=review_usage["input_tokens"],
                output_tokens=review_usage["output_tokens"],
                attempt_cost_usd=round(review_cost, 6),
                ok=ok,
                concerns=concerns,
            )
            review_passed = ok
            review_concerns = concerns
            if not ok:
                last_attempt = yaml_text
                last_issues = concerns
                last_validated_anchors = anchors
                last_validated_text = yaml_text
                last_validated_concerns = concerns
                continue

        _log(
            "success",
            attempts=attempt,
            total_input_tokens=usage_totals["input_tokens"],
            total_output_tokens=usage_totals["output_tokens"],
            total_cost_usd=round(cost_total, 6),
            anchor_count=len(anchors),
        )
        return ReconcileResult(
            anchors=anchors,
            attempts=attempt,
            usage_totals=usage_totals,
            cost_usd=cost_total,
            review_ran=review_ran,
            review_passed=review_passed,
            review_concerns=review_concerns,
        )

    # Exhausted. Two paths per PLAN §7.1 step 6.
    if last_validated_anchors is not None:
        _log(
            "exhausted_review_only",
            attempts=max_attempts,
            concerns=last_validated_concerns,
            total_cost_usd=round(cost_total, 6),
        )
        # Mark every anchor low-confidence so the review file flags them.
        flagged = [
            Anchor(
                cls=a.cls,
                quote=a.quote,
                heading=a.heading,
                ordinal=a.ordinal,
                hash=a.hash,
                confidence="low",
            )
            for a in last_validated_anchors
        ]
        return ReconcileResult(
            anchors=flagged,
            attempts=max_attempts,
            usage_totals=usage_totals,
            cost_usd=cost_total,
            review_ran=True,
            review_passed=False,
            review_concerns=last_validated_concerns,
            needs_attention=True,
            needs_attention_reason=[
                "review pass never approved across retries; deterministic validators ok",
                *last_validated_concerns,
            ],
        )

    _log(
        "exhausted_validators",
        attempts=max_attempts,
        last_issues=last_issues,
        total_cost_usd=round(cost_total, 6),
    )
    print(
        "para_style_a exhausted retries — deterministic validators never passed: "
        + "; ".join(last_issues),
        file=sys.stderr,
    )
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# Pipeline glue


def read_prev_body_from_git(post_path: Path) -> str:
    """Return the previous version of the post markdown from git HEAD.

    Used as `prev_doc` for the reconciler. If HEAD doesn't have the file
    yet (first sync), returns "" — the reconciler treats that as the
    first-sync path.
    """
    try:
        rel = post_path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        rel = post_path
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


def write_anchors_artifacts(
    result: ReconcileResult,
    anchors_path: Path = ANCHORS_PATH,
    review_path: Path = ANCHORS_REVIEW_PATH,
) -> tuple[Path, Path | None]:
    """Write the main anchors.yaml deterministically. If the run produced
    review concerns (or any low-confidence anchors), also write
    anchors_review.yaml. Returns (anchors_path, review_path_or_None)."""
    save_anchors(result.anchors, anchors_path)

    low_conf = [a for a in result.anchors if a.confidence == "low"]
    has_concerns = bool(result.review_concerns)
    if not low_conf and not has_concerns:
        # Clean run — clear any stale review file.
        if review_path.exists():
            review_path.unlink()
        return anchors_path, None

    payload = {
        "concerns": result.review_concerns,
        "low_confidence_anchors": [a.to_dict() for a in low_conf],
        "needs_attention": result.needs_attention,
    }
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(
        yaml.safe_dump(
            payload,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
            width=1000,
        )
    )
    return anchors_path, review_path


def reconcile_from_disk(
    *,
    new_doc: str,
    project_styling: str,
    library_styling: str,
    post_path: Path,
    fuzzy_threshold: float = 0.8,
    anchors_path: Path = ANCHORS_PATH,
) -> ReconcileResult:
    """Convenience wrapper for sync/__main__.py: read prev body from git,
    read prev anchors from disk, run the reconciler."""
    prev_doc = read_prev_body_from_git(post_path)
    prev_anchors = load_anchors(anchors_path)
    return reconcile(
        prev_doc=prev_doc,
        new_doc=new_doc,
        prev_anchors=prev_anchors,
        project_styling=project_styling,
        library_styling=library_styling,
        fuzzy_threshold=fuzzy_threshold,
    )


if __name__ == "__main__":
    # Trivial smoke: read inputs from stdin as JSON.
    payload = json.loads(sys.stdin.read())
    result = reconcile(
        prev_doc=payload.get("prev_doc", ""),
        new_doc=payload["new_doc"],
        prev_anchors=[Anchor.from_dict(r) for r in payload.get("prev_anchors", [])],
        project_styling=payload.get("project_styling", ""),
        library_styling=payload.get("library_styling", ""),
    )
    write_anchors_artifacts(result)
    print(dumps_anchors(result.anchors))
