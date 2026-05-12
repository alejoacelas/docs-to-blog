"""Unit tests for the anchors module: hash, paragraph parser, fuzzy matcher,
and load/save round-trip."""

from __future__ import annotations

from pathlib import Path

import pytest

from sync.anchors import (
    Anchor,
    Quote,
    compute_paragraph_hash,
    dumps_anchors,
    extract_paragraphs_with_headings,
    find_paragraph,
    fuzzy_match_candidates,
    load_anchors,
    save_anchors,
)


# ---------------------------------------------------------------------------
# compute_paragraph_hash


def test_hash_is_8_hex_chars():
    h = compute_paragraph_hash("hello world")
    assert len(h) == 8
    assert all(c in "0123456789abcdef" for c in h)


def test_hash_stable_across_whitespace_runs():
    a = compute_paragraph_hash("hello  world")
    b = compute_paragraph_hash("hello world")
    c = compute_paragraph_hash("  hello\tworld\n")
    assert a == b == c


def test_hash_changes_on_content_change():
    a = compute_paragraph_hash("hello world")
    b = compute_paragraph_hash("hello worlds")
    assert a != b


# ---------------------------------------------------------------------------
# extract_paragraphs_with_headings


def test_extract_simple():
    md = """\
# Title

First paragraph here.

Second paragraph here.

## Why

Under Why, one.

Under Why, two.
"""
    paras = extract_paragraphs_with_headings(md)
    assert [(p.heading, p.ordinal, p.text) for p in paras] == [
        ("Title", 1, "First paragraph here."),
        ("Title", 2, "Second paragraph here."),
        ("Why", 1, "Under Why, one."),
        ("Why", 2, "Under Why, two."),
    ]


def test_extract_skips_code_fences():
    md = """\
# T

Para A.

```python
x = 1
```

Para B.
"""
    paras = extract_paragraphs_with_headings(md)
    texts = [p.text for p in paras]
    assert texts == ["Para A.", "Para B."]


def test_extract_handles_no_heading():
    md = "Just one paragraph here.\n"
    paras = extract_paragraphs_with_headings(md)
    assert len(paras) == 1
    assert paras[0].heading == ""
    assert paras[0].ordinal == 1


def test_extract_handles_frontmatter():
    md = """\
---
title: x
date: 2026-05-12
---

# T

Para one.
"""
    paras = extract_paragraphs_with_headings(md)
    assert [p.text for p in paras] == ["Para one."]


def test_extract_multi_line_paragraph():
    md = "First line\nstill first paragraph.\n\nSecond paragraph here.\n"
    paras = extract_paragraphs_with_headings(md)
    assert paras[0].text == "First line\nstill first paragraph."
    assert paras[1].text == "Second paragraph here."


def test_find_paragraph_returns_match():
    md = "# A\n\nP1.\n\nP2.\n\n# B\n\nP3.\n"
    paras = extract_paragraphs_with_headings(md)
    found = find_paragraph(paras, "A", 2)
    assert found is not None
    assert found.text == "P2."


def test_find_paragraph_returns_none_on_miss():
    md = "# A\n\nP1.\n"
    paras = extract_paragraphs_with_headings(md)
    assert find_paragraph(paras, "A", 5) is None
    assert find_paragraph(paras, "Nonexistent", 1) is None


# ---------------------------------------------------------------------------
# fuzzy_match_candidates


def _para_for(heading: str, ordinal: int, text: str):
    """Build a minimal Paragraph-like value for tests."""
    from sync.anchors import Paragraph

    return Paragraph(
        text=text, heading=heading, ordinal=ordinal, hash=compute_paragraph_hash(text)
    )


def test_fuzzy_exact_substring_is_high_confidence():
    prior = [
        Anchor(
            cls="aside",
            quote=Quote(exact="When we first sketched the system"),
            heading="What this proves",
            ordinal=2,
            hash=compute_paragraph_hash(
                "When we first sketched the system on a napkin, the anchors were an afterthought."
            ),
        )
    ]
    new_paras = [
        _para_for("What this proves", 1, "Some lead-in paragraph."),
        _para_for(
            "What this proves",
            2,
            "When we first sketched the system on a napkin, the anchors were an afterthought.",
        ),
    ]
    cands = fuzzy_match_candidates(prior, new_paras, threshold=0.8)
    assert len(cands) == 1
    assert cands[0].candidate_ordinal == 2
    assert cands[0].confidence == 1.0


def test_fuzzy_tolerates_typo_fix():
    prior = [
        Anchor(
            cls="aside",
            quote=Quote(exact="quick brown fox jumps over the lazy dog"),
            heading="X",
            ordinal=1,
            hash="00000000",
        )
    ]
    new_paras = [
        # Typo fix: "quik" -> "quick" already correct, now "lazy" -> "sleeping"
        _para_for("X", 1, "quick brown fox jumps over the sleeping dog"),
    ]
    cands = fuzzy_match_candidates(prior, new_paras, threshold=0.7)
    assert len(cands) == 1
    assert cands[0].candidate_ordinal == 1


def test_fuzzy_no_match_returns_empty():
    prior = [
        Anchor(
            cls="aside",
            quote=Quote(exact="completely unrelated needle text"),
            heading="X",
            ordinal=1,
            hash="00000000",
        )
    ]
    new_paras = [_para_for("X", 1, "nothing remotely similar here")]
    # High threshold = stricter match required, so this should miss.
    cands = fuzzy_match_candidates(prior, new_paras, threshold=0.99)
    assert cands == []


def test_fuzzy_empty_inputs():
    assert fuzzy_match_candidates([], [_para_for("X", 1, "x")]) == []
    assert fuzzy_match_candidates(
        [Anchor("aside", Quote("x"), "X", 1, "00000000")], []
    ) == []


# ---------------------------------------------------------------------------
# load / save


def test_save_then_load_roundtrip(tmp_path: Path):
    anchors = [
        Anchor(
            cls="aside",
            quote=Quote(exact="The exact text", prefix="before", suffix="after"),
            heading="Why",
            ordinal=2,
            hash="abcd1234",
        ),
        Anchor(
            cls="feature-quote",
            quote=Quote(exact="Another exact text"),
            heading="Why",
            ordinal=1,
            hash="11112222",
        ),
    ]
    path = tmp_path / "anchors.yaml"
    save_anchors(anchors, path)

    text = path.read_text()
    # Deterministic order: ordinal 1 should appear before ordinal 2 under Why.
    assert text.index("11112222") < text.index("abcd1234")
    assert text.endswith("\n")

    loaded = load_anchors(path)
    assert {a.hash for a in loaded} == {"abcd1234", "11112222"}
    quotes = {a.hash: a.quote.exact for a in loaded}
    assert quotes["abcd1234"] == "The exact text"


def test_load_missing_returns_empty(tmp_path: Path):
    assert load_anchors(tmp_path / "nonexistent.yaml") == []


def test_dumps_omits_empty_prefix_suffix():
    anchors = [
        Anchor(
            cls="aside",
            quote=Quote(exact="just exact"),
            heading="H",
            ordinal=1,
            hash="00000000",
        )
    ]
    out = dumps_anchors(anchors)
    assert "prefix" not in out
    assert "suffix" not in out
    assert "just exact" in out


def test_dumps_includes_confidence_when_low():
    anchors = [
        Anchor(
            cls="aside",
            quote=Quote(exact="x"),
            heading="H",
            ordinal=1,
            hash="00000000",
            confidence="low",
        )
    ]
    out = dumps_anchors(anchors)
    assert "confidence" in out and "low" in out


# ---------------------------------------------------------------------------
# Anchor.from_dict tolerance


def test_anchor_from_dict_tolerates_string_quote():
    raw = {
        "class": "aside",
        "anchor": {
            "quote": "shorthand string form",
            "heading": "H",
            "ordinal": 1,
            "hash": "00000000",
        },
    }
    a = Anchor.from_dict(raw)
    assert a.quote.exact == "shorthand string form"


def test_anchor_from_dict_missing_optional_fields():
    raw = {
        "class": "aside",
        "anchor": {
            "quote": {"exact": "x"},
            "heading": "H",
            "ordinal": 1,
            "hash": "00000000",
        },
    }
    a = Anchor.from_dict(raw)
    assert a.quote.prefix == ""
    assert a.quote.suffix == ""
    assert a.confidence == "high"
