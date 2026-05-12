"""Unit tests for the Call 2 validators in sync.para_style_a.

These exercise the deterministic validators only — no live Anthropic
calls. The integration smoke for the full reconciler is the manual
end-to-end run against the real Google Doc.
"""

from __future__ import annotations

import pytest

from sync.anchors import compute_paragraph_hash
from sync.para_style_a import (
    ValidationError,
    _coerce_anchors,
    _extract_yaml_block,
    _parse_yaml,
    validate_anchors,
)


DOC = """\
# Title

A lead-in paragraph here.

The aside-worthy paragraph: When we first sketched the system on a napkin, the anchors were an afterthought.

## Why

A normal paragraph under Why.

The featured quote paragraph: If anchors are a fingerprint, decisions are a confession.
"""

ASIDE_TEXT = (
    "The aside-worthy paragraph: When we first sketched the system on a napkin, "
    "the anchors were an afterthought."
)
FEATURE_TEXT = (
    "The featured quote paragraph: If anchors are a fingerprint, decisions are a confession."
)


def _yaml_for(class_name: str, quote: str, heading: str, ordinal: int, h: str) -> str:
    return f"""\
paragraphs:
  - class: {class_name}
    anchor:
      quote:
        exact: "{quote}"
      heading: "{heading}"
      ordinal: {ordinal}
      hash: "{h}"
"""


# ---------------------------------------------------------------------------
# YAML parse


def test_parse_rejects_unparseable_yaml():
    with pytest.raises(ValidationError, match="YAML parse"):
        _parse_yaml("paragraphs: [unclosed")


def test_parse_rejects_non_mapping_top_level():
    with pytest.raises(ValidationError, match="must be a mapping"):
        _parse_yaml("- just a list")


def test_parse_rejects_missing_paragraphs_key():
    with pytest.raises(ValidationError, match="paragraphs"):
        _parse_yaml("something_else: []")


def test_parse_empty_yaml_treated_as_empty_paragraphs():
    data = _parse_yaml("")
    assert data == {"paragraphs": []}


# ---------------------------------------------------------------------------
# Coerce


def test_coerce_rejects_missing_class():
    data = {"paragraphs": [{"anchor": {"quote": {"exact": "x"}, "heading": "H", "ordinal": 1, "hash": "00000000"}}]}
    with pytest.raises(ValidationError, match="missing `class`"):
        _coerce_anchors(data)


def test_coerce_rejects_missing_anchor():
    with pytest.raises(ValidationError, match="missing `anchor`"):
        _coerce_anchors({"paragraphs": [{"class": "aside"}]})


def test_coerce_rejects_missing_anchor_field():
    with pytest.raises(ValidationError, match="missing `hash`"):
        _coerce_anchors(
            {
                "paragraphs": [
                    {
                        "class": "aside",
                        "anchor": {
                            "quote": {"exact": "x"},
                            "heading": "H",
                            "ordinal": 1,
                        },
                    }
                ]
            }
        )


# ---------------------------------------------------------------------------
# validate_anchors


def _aside_hash() -> str:
    return compute_paragraph_hash(ASIDE_TEXT)


def _feature_hash() -> str:
    return compute_paragraph_hash(FEATURE_TEXT)


def test_validate_accepts_valid_anchor():
    text = _yaml_for("aside", "When we first sketched", "Title", 2, _aside_hash())
    anchors = _coerce_anchors(_parse_yaml(text))
    validate_anchors(anchors, new_doc=DOC, known_classes={"aside"})


def test_validate_rejects_unknown_class():
    text = _yaml_for("mystery", "When we first sketched", "Title", 2, _aside_hash())
    anchors = _coerce_anchors(_parse_yaml(text))
    with pytest.raises(ValidationError, match="not in styling tab"):
        validate_anchors(anchors, new_doc=DOC, known_classes={"aside"})


def test_validate_rejects_quote_not_in_doc():
    text = _yaml_for("aside", "this text does not appear anywhere", "Title", 2, _aside_hash())
    anchors = _coerce_anchors(_parse_yaml(text))
    with pytest.raises(ValidationError, match="verbatim substring"):
        validate_anchors(anchors, new_doc=DOC, known_classes={"aside"})


def test_validate_rejects_unreachable_ordinal():
    text = _yaml_for("aside", "When we first sketched", "Title", 99, _aside_hash())
    anchors = _coerce_anchors(_parse_yaml(text))
    with pytest.raises(ValidationError, match="unreachable"):
        validate_anchors(anchors, new_doc=DOC, known_classes={"aside"})


def test_validate_rejects_hash_mismatch():
    text = _yaml_for("aside", "When we first sketched", "Title", 2, "deadbeef")
    anchors = _coerce_anchors(_parse_yaml(text))
    with pytest.raises(ValidationError, match="hash mismatch"):
        validate_anchors(anchors, new_doc=DOC, known_classes={"aside"})


def test_validate_rejects_quote_in_doc_but_wrong_paragraph():
    # Quote points at the feature paragraph but heading/ordinal point at the aside.
    text = _yaml_for("aside", "If anchors are a fingerprint", "Title", 2, _aside_hash())
    anchors = _coerce_anchors(_parse_yaml(text))
    with pytest.raises(ValidationError, match="not in the matched paragraph"):
        validate_anchors(anchors, new_doc=DOC, known_classes={"aside"})


def test_validate_rejects_duplicate_position():
    text = (
        _yaml_for("aside", "When we first sketched", "Title", 2, _aside_hash())
        + _yaml_for("feature-quote", "When we first sketched", "Title", 2, _aside_hash())
        .replace("paragraphs:\n", "")
    )
    anchors = _coerce_anchors(_parse_yaml(text))
    with pytest.raises(ValidationError, match="duplicate anchor"):
        validate_anchors(
            anchors, new_doc=DOC, known_classes={"aside", "feature-quote"}
        )


def test_validate_accepts_two_classes_on_different_paragraphs():
    text1 = _yaml_for("aside", "When we first sketched", "Title", 2, _aside_hash())
    text2 = _yaml_for(
        "feature-quote", "If anchors are a fingerprint", "Why", 2, _feature_hash()
    )
    combined = text1 + text2.replace("paragraphs:\n", "")
    anchors = _coerce_anchors(_parse_yaml(combined))
    validate_anchors(
        anchors, new_doc=DOC, known_classes={"aside", "feature-quote"}
    )


# ---------------------------------------------------------------------------
# YAML extraction from LLM output


def test_extract_yaml_block_with_fence():
    text = "Some preamble\n```yaml\nparagraphs: []\n```\nTrailing"
    assert _extract_yaml_block(text) == "paragraphs: []"


def test_extract_yaml_block_without_fence_falls_back():
    text = "paragraphs: []"
    assert _extract_yaml_block(text) == "paragraphs: []"


def test_extract_yaml_block_bare_fence():
    text = "```\nparagraphs: []\n```"
    assert _extract_yaml_block(text) == "paragraphs: []"
