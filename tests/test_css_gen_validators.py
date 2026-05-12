"""Unit tests for CSS validators in sync.css_gen.

These tests exercise the validator and normaliser logic only — no live
Anthropic calls. The integration smoke for the full Call 1 path is the
manual end-to-end run on the real Google Doc.
"""

from __future__ import annotations

import pytest

from sync.css_gen import (
    ValidationError,
    extract_tag_names,
    normalize_css,
    validate_css,
)


# ---------------------------------------------------------------------------
# extract_tag_names


def test_extract_tag_names_markdown_form():
    text = """\
## Tags

**aside** — a reflective tangent.

**feature-quote** — a single line pulled out.
"""
    assert extract_tag_names(text) == ["aside", "feature-quote"]


def test_extract_tag_names_plain_form():
    text = """\
Tags

aside — a reflective tangent.

feature-quote — a single line pulled out.

spaghetti-italics — for inline conversational asides.
"""
    assert extract_tag_names(text) == ["aside", "feature-quote", "spaghetti-italics"]


def test_extract_tag_names_dedupes():
    text = "**aside** — one\n\naside — two"
    assert extract_tag_names(text) == ["aside"]


# ---------------------------------------------------------------------------
# validate_css — parse


def test_validate_rejects_unparseable_css():
    css = ".aside { color: red"  # missing closing brace
    with pytest.raises(ValidationError):
        validate_css(css, expected_tags=["aside"], known_tags={"aside"})


# ---------------------------------------------------------------------------
# validate_css — coverage


def test_validate_rejects_missing_tag():
    css = ".aside { color: red; }"
    with pytest.raises(ValidationError, match="missing rules"):
        validate_css(
            css,
            expected_tags=["aside", "feature-quote"],
            known_tags={"aside", "feature-quote"},
        )


def test_validate_rejects_unknown_class():
    css = ".aside { color: red; } .made-up { color: pink; }"
    with pytest.raises(ValidationError, match="not in styling tab"):
        validate_css(
            css,
            expected_tags=["aside"],
            known_tags={"aside"},
        )


def test_validate_allows_no_class_global_rules():
    css = """
:root { --accent: gold; }
body { font-family: serif; }
.aside { color: red; }
"""
    # Should not raise — :root and body have no class selectors.
    validate_css(css, expected_tags=["aside"], known_tags={"aside"})


def test_validate_allows_library_class_unused_in_project():
    css = ".aside { color: red; }"
    validate_css(
        css,
        expected_tags=["aside"],  # only project required
        known_tags={"aside", "spaghetti-italics"},  # library has spaghetti
    )


# ---------------------------------------------------------------------------
# validate_css — class name shape


def test_validate_rejects_bad_class_name():
    css = ".Aside { color: red; }"
    with pytest.raises(ValidationError, match="violate"):
        validate_css(css, expected_tags=[], known_tags={"Aside"})


# ---------------------------------------------------------------------------
# validate_css — @import


def test_validate_rejects_external_import():
    css = '@import url("https://fonts.googleapis.com/css?family=Inter"); .aside { color: red; }'
    with pytest.raises(ValidationError, match="@import of external URL"):
        validate_css(css, expected_tags=["aside"], known_tags={"aside"})


# ---------------------------------------------------------------------------
# normalize_css — byte-stability


def test_normalize_sorts_properties_alphabetically():
    css = ".aside { z-index: 1; color: red; background: white; }"
    out = normalize_css(css)
    # background, color, z-index alphabetical
    decl_block = out.split("{", 1)[1].split("}", 1)[0]
    decls = [d.strip() for d in decl_block.strip().split(";") if d.strip()]
    assert [d.split(":")[0].strip() for d in decls] == ["background", "color", "z-index"]


def test_normalize_strips_comments():
    css = "/* hi */ .aside { /* nope */ color: red; }"
    out = normalize_css(css)
    assert "/* hi */" not in out
    assert "/* nope */" not in out


def test_normalize_is_idempotent():
    css = ".aside { z-index: 1; color: red; } .feature-quote { font-size: 1.4rem; }"
    once = normalize_css(css)
    twice = normalize_css(once)
    assert once == twice


def test_normalize_emits_trailing_newline():
    css = ".aside { color: red; }"
    out = normalize_css(css)
    assert out.endswith("\n")
