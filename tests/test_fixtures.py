"""Fixture-driven snapshot tests for Implementation A (PLAN §9.1).

Each `dayN/` fixture supplies:
  - doc.md            : source markdown body (as `gdoc cat` would produce
                        after the unescape step in sync/fetch.py)
  - styling.md        : project styling tab text (plain-text export)
  - library.md        : library doc body
  - library_styling.md: library doc styling tab text
  - expected/anchors.yaml   : hand-authored "correct" anchors for this doc
  - expected/generated.css  : hand-authored "correct" CSS for this styling
  - expected/hello.html     : representative post-plugin HTML substrings

The harness is a STRUCTURAL snapshot test: it runs Implementation A's
deterministic validators (sync.css_gen.validate_css and
sync.para_style_a.validate_anchors) against the goldens and asserts
they pass. It does NOT call Claude — goldens are hand-authored so the
test is hermetic and cheap.

For the day1 → day2 transition we additionally run the fuzzy matcher
(sync.anchors.fuzzy_match_candidates) with day1's anchors against
day2's doc, and assert at least one candidate is found — proving the
matcher's typo-fix tolerance still works.

What this test is for: regression-detection. If a future code change
breaks `validate_css` or `validate_anchors` against a known-correct
golden, this test fires immediately. It does NOT verify that Claude
would reproduce the goldens (which would be flaky and expensive).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from sync.anchors import (
    extract_paragraphs_with_headings,
    fuzzy_match_candidates,
    load_anchors,
)
from sync.css_gen import extract_tag_names, validate_css
from sync.para_style_a import validate_anchors

FIXTURES_DIR = Path(__file__).parent / "fixtures"
DAYS = ["day1", "day2"]


# ---------------------------------------------------------------------------
# Helpers


def _load_fixture(day: str) -> dict:
    """Load all five input/golden files for a day."""
    base = FIXTURES_DIR / day
    return {
        "day": day,
        "base": base,
        "doc": (base / "doc.md").read_text(),
        "styling": (base / "styling.md").read_text(),
        "library": (base / "library.md").read_text(),
        "library_styling": (base / "library_styling.md").read_text(),
        "expected_anchors_path": base / "expected" / "anchors.yaml",
        "expected_css": (base / "expected" / "generated.css").read_text(),
        "expected_html": (base / "expected" / "hello.html").read_text(),
    }


def _expected_html_snippets(html_text: str) -> list[str]:
    """Strip HTML comments + blank lines, return non-empty lines as the
    substrings the built HTML must contain.

    The expected/hello.html files are hand-authored: their non-comment
    lines are the substrings we assert. We tolerate whitespace and HTML
    attribute order by matching exact substrings.
    """
    # Drop block comments
    no_comments = re.sub(r"<!--.*?-->", "", html_text, flags=re.DOTALL)
    snippets = [line.strip() for line in no_comments.splitlines() if line.strip()]
    return snippets


# ---------------------------------------------------------------------------
# Per-day validator snapshot tests


@pytest.mark.parametrize("day", DAYS)
def test_fixture_directory_layout(day: str):
    """The fixture has the exact files PLAN §9.1 calls for."""
    base = FIXTURES_DIR / day
    assert (base / "doc.md").is_file(), f"{day} missing doc.md"
    assert (base / "styling.md").is_file(), f"{day} missing styling.md"
    assert (base / "library.md").is_file(), f"{day} missing library.md"
    assert (base / "library_styling.md").is_file(), f"{day} missing library_styling.md"
    expected = base / "expected"
    assert expected.is_dir(), f"{day} missing expected/"
    assert (expected / "anchors.yaml").is_file(), f"{day} missing expected/anchors.yaml"
    assert (expected / "generated.css").is_file(), f"{day} missing expected/generated.css"
    assert (expected / "hello.html").is_file(), f"{day} missing expected/hello.html"


@pytest.mark.parametrize("day", DAYS)
def test_expected_anchors_pass_validators(day: str):
    """The hand-authored anchors.yaml golden parses and passes every
    deterministic validator from sync.para_style_a.validate_anchors.
    """
    f = _load_fixture(day)
    anchors = load_anchors(f["expected_anchors_path"])
    assert anchors, f"{day} expected anchors.yaml is empty"

    known_classes = (
        set(extract_tag_names(f["styling"]))
        | set(extract_tag_names(f["library_styling"]))
    )
    # Raises ValidationError on any failure; the test fails on that.
    validate_anchors(anchors, new_doc=f["doc"], known_classes=known_classes)


@pytest.mark.parametrize("day", DAYS)
def test_expected_css_passes_validators(day: str):
    """The hand-authored generated.css golden parses and passes every
    deterministic validator from sync.css_gen.validate_css.
    """
    f = _load_fixture(day)
    project_tags = extract_tag_names(f["styling"])
    library_tags = extract_tag_names(f["library_styling"])
    known_tags = set(project_tags) | set(library_tags)
    # Raises ValidationError on any failure.
    validate_css(
        f["expected_css"], expected_tags=project_tags, known_tags=known_tags
    )


@pytest.mark.parametrize("day", DAYS)
def test_expected_html_snippets_present_in_doc_source(day: str):
    """Every span-class substring in expected/hello.html corresponds to
    something that's actually achievable from the source.

    For inline spans, the substring must come from a source `<tag>x</tag>`
    in doc.md (proves remark-spans has something to transform).
    For paragraph wrappers (`<p class="X">`), the class must be in the
    expected anchors (proves remark-anchors will inject it).
    """
    f = _load_fixture(day)
    doc = f["doc"]
    anchors = load_anchors(f["expected_anchors_path"])
    anchor_classes = {a.cls for a in anchors}

    for snippet in _expected_html_snippets(f["expected_html"]):
        if snippet.startswith("<span"):
            # Pull `class="…"` and assert a matching `<tag>` exists in source
            m = re.search(r'class="([a-z][a-z0-9-]*)"', snippet)
            assert m, f"{day}: malformed span snippet {snippet!r}"
            tag = m.group(1)
            assert f"<{tag}" in doc, (
                f"{day}: expected <span class={tag!r}> implies a <{tag}> "
                f"in doc.md, but the source has none"
            )
        elif snippet.startswith("<p"):
            m = re.search(r'class="([a-z][a-z0-9-]*)"', snippet)
            assert m, f"{day}: malformed paragraph snippet {snippet!r}"
            cls = m.group(1)
            assert cls in anchor_classes, (
                f"{day}: expected <p class={cls!r}> but no anchor in "
                f"expected/anchors.yaml carries that class "
                f"(have: {sorted(anchor_classes)})"
            )
        # Other lines are tolerated (e.g. raw text inside span tags).


# ---------------------------------------------------------------------------
# Day 1 → Day 2 transition: fuzzy matcher coverage


def test_fuzzy_matcher_finds_typo_fix_candidate():
    """The day-1 anchor on `What I keep getting wrong` ord=2 has a
    quote.exact ("...taped to the monitor") that is NOT a verbatim
    substring of day-2's doc (the day-2 text reads "taped to my monitor").
    The fuzzy matcher should still surface day-2 ord=2 as the candidate,
    proving Call 2 has a useful pre-pass hint for the typo-fix case.
    """
    day1 = _load_fixture("day1")
    day2 = _load_fixture("day2")
    prior_anchors = load_anchors(day1["expected_anchors_path"])
    new_paragraphs = extract_paragraphs_with_headings(day2["doc"])

    candidates = fuzzy_match_candidates(prior_anchors, new_paragraphs, threshold=0.7)

    # At least one candidate found. The exact set is implementation-tunable;
    # what's load-bearing is that the matcher doesn't return [].
    assert candidates, (
        "fuzzy matcher returned no candidates across the day-1 → day-2 "
        "transition; the typo-fix case is supposed to be in scope"
    )

    # The aside anchor's old hash is d935704c (day 1). Confirm we got a
    # hit pointing at day 2's `What I keep getting wrong` ord=2.
    aside_anchor = next(
        (a for a in prior_anchors if a.cls == "aside"), None
    )
    assert aside_anchor is not None, "day-1 fixture missing the aside anchor"
    matched = [
        c
        for c in candidates
        if c.prior_anchor_hash == aside_anchor.hash
        and c.candidate_heading == "What I keep getting wrong"
        and c.candidate_ordinal == 2
    ]
    assert matched, (
        f"fuzzy matcher did not relocate the typo-fixed aside anchor; "
        f"candidates were: {candidates!r}"
    )


def test_day2_ordinals_shift_as_designed():
    """Sanity check that day-2's edits produce the ordinal shape
    described in tests/fixtures/day2/notes.md: Background gets a new
    paragraph 2 (the inserted one) and the former ord=2/3 slide down.
    """
    day2 = _load_fixture("day2")
    paras = extract_paragraphs_with_headings(day2["doc"])
    by_pos = {(p.heading, p.ordinal): p for p in paras}

    bg2 = by_pos.get(("Background", 2))
    assert bg2 is not None and bg2.text.startswith(
        "Code review is not the only example"
    ), f"day-2 Background ord=2 should be the inserted paragraph, got: {bg2!r}"

    bg3 = by_pos.get(("Background", 3))
    assert bg3 is not None and "<aside>" in bg3.text, (
        "day-2 Background ord=3 should be the rewritten paragraph "
        "carrying the inline <aside> span; got: " + repr(bg3)
    )

    bg4 = by_pos.get(("Background", 4))
    assert bg4 is not None and bg4.text.startswith(
        "It turns out the slowness was load-bearing"
    ), f"day-2 Background ord=4 should be the rewritten callout, got: {bg4!r}"


def test_day1_anchors_quote_exact_holds_verbatim_in_day1_doc():
    """Belt-and-braces: every quote.exact in day-1's expected anchors is
    a verbatim substring of day-1's doc. This is enforced by
    validate_anchors but we assert it standalone so a future loosening
    of the validator doesn't quietly let the fixture rot.
    """
    f = _load_fixture("day1")
    anchors = load_anchors(f["expected_anchors_path"])
    for a in anchors:
        assert a.quote.exact in f["doc"], (
            f"day1 anchor for class {a.cls!r} has quote.exact "
            f"{a.quote.exact!r} which is NOT a verbatim substring of day1/doc.md"
        )


def test_day2_anchors_quote_exact_holds_verbatim_in_day2_doc():
    f = _load_fixture("day2")
    anchors = load_anchors(f["expected_anchors_path"])
    for a in anchors:
        assert a.quote.exact in f["doc"], (
            f"day2 anchor for class {a.cls!r} has quote.exact "
            f"{a.quote.exact!r} which is NOT a verbatim substring of day2/doc.md"
        )
