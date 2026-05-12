"""Unit tests for sync.fetch.unescape_span_tags.

The empirical observation behind this function (and why the regex is
narrow rather than a blanket `\\<` → `<` swap) is recorded in
notes/2026-05-12-gdoc-span-escaping.md.
"""

from __future__ import annotations

from sync.fetch import unescape_span_tags


def test_simple_span_pair():
    raw = r"the \<aside\>quiet bit\</aside\> ends here"
    assert unescape_span_tags(raw) == "the <aside>quiet bit</aside> ends here"


def test_nested_spans():
    raw = r"\<aside\>see \<em\>here\</em\>\</aside\>"
    # Both outer and inner pairs are unescaped independently.
    assert unescape_span_tags(raw) == "<aside>see <em>here</em></aside>"


def test_hyphen_and_digit_tagnames():
    raw = r"\<feature-quote\>x\</feature-quote\> and \<h1-style\>y\</h1-style\>"
    assert (
        unescape_span_tags(raw)
        == "<feature-quote>x</feature-quote> and <h1-style>y</h1-style>"
    )


def test_uppercase_tagnames_left_alone():
    # CSS-class-shaped means lowercase-led; uppercase shouldn't unescape.
    raw = r"\<Aside\>x\</Aside\>"
    assert unescape_span_tags(raw) == raw


def test_stray_lt_gt_not_unescaped():
    # A backslash-escaped inequality stays escaped; only tag-shaped tokens
    # are unescaped. Markdown renderers will then handle the `\<` literally.
    raw = r"if 5 \< 6 then \> 4"
    assert unescape_span_tags(raw) == raw


def test_unmatched_opener_passes_through():
    # `\<aside\>` alone (no closer) still unescapes since the regex matches
    # one pair at a time. The remark plugin handles unbalanced tags by
    # leaving them in place — no error.
    raw = r"open \<aside\>but no closer"
    assert unescape_span_tags(raw) == "open <aside>but no closer"


def test_no_escapes_returns_unchanged():
    raw = "plain text with <em>real html-ish</em> markup already canonical"
    assert unescape_span_tags(raw) == raw


def test_empty_string():
    assert unescape_span_tags("") == ""


def test_multiline_preserves_other_content():
    raw = (
        "para one — nothing special\n"
        "\n"
        r"para two has a \<aside\>side note\</aside\> in the middle"
        "\n"
        "\n"
        "para three — also nothing\n"
    )
    expected = (
        "para one — nothing special\n"
        "\n"
        "para two has a <aside>side note</aside> in the middle"
        "\n"
        "\n"
        "para three — also nothing\n"
    )
    assert unescape_span_tags(raw) == expected
