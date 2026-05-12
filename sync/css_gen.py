"""Call 1 — CSS generator.

Bounded transform per PLAN §7.1/§7.2:
- assemble inputs (project styling tab + library styling tab + manual.css
  + prior generated.css);
- single Claude call → plain CSS text;
- deterministic validators (parse, tag coverage, class-name shape,
  no external @import);
- optional review pass;
- bounded retry (max 3 attempts) with the prior failure folded back.

No tool use, no agent loop inside the call — only the orchestrator loop.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import tinycss2

from sync.llm import call_claude, estimate_cost_usd

REPO_ROOT = Path(__file__).resolve().parent.parent
STYLES_DIR = REPO_ROOT / "styles"
MANUAL_CSS_PATH = STYLES_DIR / "manual.css"
GENERATED_CSS_PATH = STYLES_DIR / "generated.css"

MAX_ATTEMPTS = 3
CLASS_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
# Tag-definition line in the styling tab: `**name**` at the start of a
# definition. Tolerate optional leading whitespace and require it be on
# its own line (the styling tab body lines start at column 0 in plain
# export).
TAG_DEF_RE = re.compile(r"^\s*\*\*([a-z][a-z0-9-]*)\*\*", re.MULTILINE)
# Plain-text styling tab uses `name — definition` instead of `**name**`.
PLAIN_TAG_DEF_RE = re.compile(
    r"^([a-z][a-z0-9-]*)\s+[—-]\s+",
    re.MULTILINE,
)


@dataclass
class GenResult:
    css: str
    attempts: int
    usage_totals: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    review_ran: bool = False
    review_passed: bool | None = None
    review_issues: list[str] = field(default_factory=list)


def _log(event: str, **fields) -> None:
    payload = {"stage": "css_gen", "event": event, **fields}
    print(json.dumps(payload), flush=True)


# ---------------------------------------------------------------------------
# Extractors


def extract_tag_names(styling_text: str) -> list[str]:
    """Find every named tag declared in a styling-tab text.

    The styling tab schema (PLAN §4) defines a tag as either:
      `**name** — definition`  (markdown bold prefix), or
      `name — definition`      (plain-text export).
    """
    seen: list[str] = []
    seen_set: set[str] = set()
    for pattern in (TAG_DEF_RE, PLAIN_TAG_DEF_RE):
        for m in pattern.finditer(styling_text):
            name = m.group(1)
            if name not in seen_set:
                seen_set.add(name)
                seen.append(name)
    return seen


# ---------------------------------------------------------------------------
# Validators


class ValidationError(Exception):
    pass


def _parse_css(css: str) -> list:
    """Parse CSS into tinycss2 rules. Raises ValidationError on parse
    failure or any error token at the top level.

    tinycss2 is intentionally permissive (CSS spec: unknown things are
    discarded, not errored). We add a brace-balance check on top of it
    so that obviously malformed input — unclosed rules, mismatched
    braces, stray syntax — is rejected.
    """
    if css.count("{") != css.count("}"):
        raise ValidationError(
            f"unbalanced braces: {css.count('{')} '{{' vs {css.count('}')} '}}'"
        )
    if css.count("(") != css.count(")"):
        raise ValidationError(
            f"unbalanced parens: {css.count('(')} '(' vs {css.count(')')} ')'"
        )
    rules = tinycss2.parse_stylesheet(css, skip_comments=False, skip_whitespace=True)
    errors = [r for r in rules if r.type == "error"]
    if errors:
        msgs = "; ".join(f"{e.kind}: {getattr(e, 'message', '')}" for e in errors)
        raise ValidationError(f"CSS parse errors: {msgs}")
    return rules


def _qualified_selectors(rules: Iterable) -> list[str]:
    """Return the prelude (selector list) of every qualified rule."""
    out: list[str] = []
    for r in rules:
        if r.type == "qualified-rule":
            out.append(tinycss2.serialize(r.prelude).strip())
    return out


def _classes_in_selectors(selectors: Iterable[str]) -> set[str]:
    classes: set[str] = set()
    for sel in selectors:
        # Find every `.name` token; tolerate combinators and descendant
        # selectors. We do not parse the full selector grammar.
        for m in re.finditer(r"\.([A-Za-z_][A-Za-z0-9_-]*)", sel):
            classes.add(m.group(1))
    return classes


def _check_no_external_imports(css: str) -> None:
    # tinycss2's at-rule detection: scan top-level for `@import`.
    rules = tinycss2.parse_stylesheet(css, skip_comments=True, skip_whitespace=True)
    for r in rules:
        if r.type == "at-rule" and r.lower_at_keyword == "import":
            prelude = tinycss2.serialize(r.prelude)
            if re.search(r"https?://", prelude):
                raise ValidationError(
                    f"@import of external URL not allowed: {prelude.strip()}"
                )


def validate_css(css: str, expected_tags: list[str], known_tags: set[str]) -> None:
    """Run every deterministic validator. Raises ValidationError on failure.

    expected_tags = tags declared in the *project* styling tab (must each
                    have a rule).
    known_tags    = union of project + library tags (no rule outside this
                    set is allowed).
    """
    rules = _parse_css(css)
    _check_no_external_imports(css)

    selectors = _qualified_selectors(rules)
    classes_in_css = _classes_in_selectors(selectors)

    # Class names must match shape.
    bad_shape = [c for c in classes_in_css if not CLASS_NAME_RE.match(c)]
    if bad_shape:
        raise ValidationError(
            f"class names violate [a-z][a-z0-9-]*: {sorted(bad_shape)}"
        )

    # Coverage: every expected tag has at least one rule whose selector
    # references its class.
    missing = [t for t in expected_tags if t not in classes_in_css]
    if missing:
        raise ValidationError(
            f"missing rules for tags declared in project styling tab: {missing}"
        )

    # No stray classes (must be in known_tags). Allow utility/global rules
    # that don't reference any class (e.g. `body { ... }`).
    extras = sorted(classes_in_css - known_tags)
    if extras:
        raise ValidationError(
            f"rules reference classes not in styling tab or library: {extras}"
        )


# ---------------------------------------------------------------------------
# Normalisation


def normalize_css(css: str) -> str:
    """Return a byte-stable form: alphabetised properties per rule, strip
    comments, single blank line between rules, trailing newline."""
    rules = tinycss2.parse_stylesheet(css, skip_comments=True, skip_whitespace=True)
    out_blocks: list[str] = []
    for r in rules:
        if r.type == "qualified-rule":
            selector = tinycss2.serialize(r.prelude).strip()
            selector = re.sub(r"\s+", " ", selector)
            decls = _normalise_declaration_block(r.content)
            if not decls:
                continue
            body_lines = "\n".join(f"  {d};" for d in decls)
            out_blocks.append(f"{selector} {{\n{body_lines}\n}}")
        elif r.type == "at-rule":
            keyword = r.lower_at_keyword
            prelude = tinycss2.serialize(r.prelude).strip()
            if r.content is None:
                # e.g. @import url("..."); — keep on one line, sorted by source order
                out_blocks.append(f"@{keyword} {prelude};")
                continue
            inner = _normalise_at_rule_body(keyword, prelude, r.content)
            out_blocks.append(inner)
        # Ignore comments and whitespace tokens at the top level.

    header = (
        "/* Auto-generated by sync/css_gen.py. Do not edit by hand. */\n\n"
    )
    return header + "\n\n".join(out_blocks) + "\n"


def _normalise_declaration_block(content_tokens) -> list[str]:
    """Parse a `{ ... }` block into sorted `prop: value` declarations."""
    decls = tinycss2.parse_declaration_list(
        content_tokens, skip_comments=True, skip_whitespace=True
    )
    rendered: list[str] = []
    for d in decls:
        if d.type != "declaration":
            continue
        value = tinycss2.serialize(d.value).strip()
        value = re.sub(r"\s+", " ", value)
        importance = " !important" if d.important else ""
        rendered.append(f"{d.lower_name}: {value}{importance}")
    rendered.sort()
    return rendered


def _normalise_at_rule_body(keyword: str, prelude: str, content_tokens) -> str:
    """Normalise the body of an at-rule like @media or @supports.

    Inside the body we expect qualified rules. We recurse via a single
    parser call, then re-emit each nested rule with sorted properties.
    """
    inner_rules = tinycss2.parse_stylesheet(
        tinycss2.serialize(content_tokens), skip_comments=True, skip_whitespace=True
    )
    nested_blocks: list[str] = []
    for r in inner_rules:
        if r.type != "qualified-rule":
            continue
        selector = re.sub(r"\s+", " ", tinycss2.serialize(r.prelude).strip())
        decls = _normalise_declaration_block(r.content)
        if not decls:
            continue
        body_lines = "\n".join(f"    {d};" for d in decls)
        nested_blocks.append(f"  {selector} {{\n{body_lines}\n  }}")
    nested = "\n".join(nested_blocks)
    return f"@{keyword} {prelude} {{\n{nested}\n}}"


# ---------------------------------------------------------------------------
# Prompt assembly + Claude calls


SYSTEM_PROMPT = """\
You generate a CSS file for a static blog. The blog author writes prose
definitions of "tags" (named styles) in a Google Doc, and you translate
those definitions into clean, deterministic CSS.

Hard rules:
- Output PLAIN CSS only. No fences, no commentary, no markdown.
- One rule per declared tag, using the class selector `.tagname`.
- Class names match `[a-z][a-z0-9-]*` — never invent new ones.
- Never `@import` an external URL.
- Do not duplicate or override declarations from the supplied manual.css.
- Use only widely-supported CSS properties.
- Prefer reuse: if both project and library declare the same tag, the
  project styling tab is the override layer on top of the library.
- Page-level styling from the project styling tab's "Global" section
  should land as either `:root` custom properties or `body` declarations.
"""


def build_user_prompt(
    project_styling: str,
    library_styling: str,
    manual_css: str,
    prior_generated_css: str,
    expected_tags: list[str],
    prior_attempt: str | None = None,
    prior_issues: list[str] | None = None,
) -> str:
    sections = [
        "PROJECT STYLING TAB (overrides library on name collision):",
        "```",
        project_styling.strip() or "(empty)",
        "```",
        "",
        "LIBRARY STYLING TAB (shared definitions):",
        "```",
        library_styling.strip() or "(empty)",
        "```",
        "",
        "MANUAL CSS (already in styles/manual.css — do not duplicate):",
        "```css",
        manual_css.strip() or "(empty)",
        "```",
        "",
        "PRIOR GENERATED CSS (last successful run — keep unchanged rules byte-stable):",
        "```css",
        prior_generated_css.strip() or "(empty — first run)",
        "```",
        "",
        f"REQUIRED TAGS (must each have a `.tagname` rule): {expected_tags}",
        "",
    ]
    if prior_attempt is not None:
        sections.extend(
            [
                "YOUR PREVIOUS ATTEMPT FAILED. Issues to fix:",
                *(f"- {i}" for i in (prior_issues or [])),
                "",
                "Previous attempt (for reference; produce a corrected version):",
                "```css",
                prior_attempt,
                "```",
                "",
            ]
        )
    sections.append(
        "Produce the corrected, complete styles/generated.css now. "
        "Output the file contents only — no markdown fences, no prose."
    )
    return "\n".join(sections)


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    # Drop opening fence (```css or just ```)
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        # Drop closing fence
        if text.rstrip().endswith("```"):
            text = text.rstrip()[: -3].rstrip()
    return text


REVIEW_SYSTEM = """\
You are reviewing a generated CSS file against the prose definitions
that produced it. Reply with JSON only:
  {"ok": true,  "issues": []}
or
  {"ok": false, "issues": ["<short issue 1>", "<short issue 2>"]}

Flag only concrete contradictions: a property the prose explicitly named
that the CSS omits or contradicts. Do not flag stylistic taste. Do not
flag missing tags — a separate validator handles coverage.
"""


def _review_pass(prose: str, css: str) -> tuple[bool, list[str], dict]:
    user = (
        "PROSE DEFINITIONS:\n```\n" + prose.strip() + "\n```\n\n"
        "GENERATED CSS:\n```css\n" + css + "\n```\n\n"
        "Reply with JSON only."
    )
    text, usage = call_claude(system=REVIEW_SYSTEM, user=user, max_tokens=1000)
    text = text.strip()
    # Sometimes the model wraps JSON in a fence even when told not to.
    if text.startswith("```"):
        text = _strip_code_fences(text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return False, [f"review-pass response not JSON: {text[:200]!r}"], usage
    ok = bool(payload.get("ok"))
    issues = list(payload.get("issues") or [])
    return ok, issues, usage


# ---------------------------------------------------------------------------
# Orchestration


def generate_css(
    project_styling: str,
    library_styling: str,
    *,
    manual_css: str | None = None,
    prior_generated_css: str | None = None,
    run_review: bool = True,
    max_attempts: int = MAX_ATTEMPTS,
) -> GenResult:
    """Run the bounded-transform loop to produce a validated, normalised
    CSS string. Raises SystemExit(1) on exhaustion."""
    if manual_css is None:
        manual_css = MANUAL_CSS_PATH.read_text() if MANUAL_CSS_PATH.exists() else ""
    if prior_generated_css is None:
        prior_generated_css = (
            GENERATED_CSS_PATH.read_text() if GENERATED_CSS_PATH.exists() else ""
        )

    project_tags = extract_tag_names(project_styling)
    library_tags = extract_tag_names(library_styling)
    known_tags = set(project_tags) | set(library_tags)

    usage_totals: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
    cost_total = 0.0

    last_attempt: str | None = None
    last_issues: list[str] = []
    review_ran = False
    review_passed: bool | None = None
    review_issues: list[str] = []

    for attempt in range(1, max_attempts + 1):
        prompt = build_user_prompt(
            project_styling=project_styling,
            library_styling=library_styling,
            manual_css=manual_css,
            prior_generated_css=prior_generated_css,
            expected_tags=project_tags,
            prior_attempt=last_attempt,
            prior_issues=last_issues or None,
        )
        text, usage = call_claude(system=SYSTEM_PROMPT, user=prompt, max_tokens=6000)
        usage_totals["input_tokens"] += usage["input_tokens"]
        usage_totals["output_tokens"] += usage["output_tokens"]
        attempt_cost = estimate_cost_usd(usage)
        cost_total += attempt_cost
        _log(
            "claude_call",
            call="css_gen",
            attempt=attempt,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            attempt_cost_usd=round(attempt_cost, 6),
        )

        css_candidate = _strip_code_fences(text)

        # Validators
        try:
            validate_css(css_candidate, expected_tags=project_tags, known_tags=known_tags)
        except ValidationError as e:
            _log("validator_failed", attempt=attempt, error=str(e))
            last_attempt = css_candidate
            last_issues = [str(e)]
            continue

        # Optional review pass
        if run_review:
            review_ran = True
            review_prose = (
                "PROJECT STYLING TAB:\n"
                + project_styling.strip()
                + "\n\nLIBRARY STYLING TAB:\n"
                + library_styling.strip()
            )
            ok, issues, review_usage = _review_pass(review_prose, css_candidate)
            usage_totals["input_tokens"] += review_usage["input_tokens"]
            usage_totals["output_tokens"] += review_usage["output_tokens"]
            review_cost = estimate_cost_usd(review_usage)
            cost_total += review_cost
            _log(
                "claude_call",
                call="css_gen_review",
                attempt=attempt,
                input_tokens=review_usage["input_tokens"],
                output_tokens=review_usage["output_tokens"],
                attempt_cost_usd=round(review_cost, 6),
                ok=ok,
                issues=issues,
            )
            review_passed = ok
            review_issues = issues
            if not ok:
                last_attempt = css_candidate
                last_issues = issues
                continue

        # Success — normalise and return
        normalised = normalize_css(css_candidate)
        _log(
            "success",
            attempts=attempt,
            total_input_tokens=usage_totals["input_tokens"],
            total_output_tokens=usage_totals["output_tokens"],
            total_cost_usd=round(cost_total, 6),
        )
        return GenResult(
            css=normalised,
            attempts=attempt,
            usage_totals=usage_totals,
            cost_usd=cost_total,
            review_ran=review_ran,
            review_passed=review_passed,
            review_issues=review_issues,
        )

    # All attempts exhausted
    _log(
        "exhausted",
        attempts=max_attempts,
        last_issues=last_issues,
        total_cost_usd=round(cost_total, 6),
    )
    print(
        "css_gen exhausted retries — last issues: " + "; ".join(last_issues),
        file=sys.stderr,
    )
    raise SystemExit(1)


def write_generated_css(css: str) -> Path:
    STYLES_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_CSS_PATH.write_text(css)
    return GENERATED_CSS_PATH


if __name__ == "__main__":
    # Trivial smoke: read styling tab + library from stdin (JSON form).
    payload = json.loads(sys.stdin.read())
    result = generate_css(
        project_styling=payload["project_styling"],
        library_styling=payload.get("library_styling", ""),
    )
    write_generated_css(result.css)
    print(result.css)
