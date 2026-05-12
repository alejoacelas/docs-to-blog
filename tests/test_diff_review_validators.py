"""Unit tests for the Call 4 (diff_review) validators.

Exercise the deterministic schema check and the tolerant JSON extractor
only — no live Anthropic calls. The full bounded-retry loop is exercised
by the integration smoke run.
"""

from __future__ import annotations

import json
from pathlib import Path

from sync.diff_review import (
    DiffReviewResult,
    _parse_verdict,
    _validate_schema,
    compute_doc_diff,
    write_verdict_file,
)


# ---------------------------------------------------------------------------
# _validate_schema


def test_validate_accepts_canonical():
    ok, concerns, err = _validate_schema({"auto_merge_ok": True, "concerns": []})
    assert err is None
    assert ok is True
    assert concerns == []


def test_validate_accepts_false_with_concerns():
    ok, concerns, err = _validate_schema(
        {"auto_merge_ok": False, "concerns": ["aside lost class"]}
    )
    assert err is None
    assert ok is False
    assert concerns == ["aside lost class"]


def test_validate_rejects_missing_auto_merge_ok():
    ok, _concerns, err = _validate_schema({"concerns": []})
    assert err is not None
    assert "auto_merge_ok" in err
    assert ok is False


def test_validate_rejects_missing_concerns():
    ok, _concerns, err = _validate_schema({"auto_merge_ok": True})
    assert err is not None
    assert "concerns" in err
    assert ok is False


def test_validate_rejects_non_bool_auto_merge_ok():
    _ok, _c, err = _validate_schema({"auto_merge_ok": "yes", "concerns": []})
    assert err is not None
    assert "bool" in err


def test_validate_rejects_non_string_concern():
    _ok, _c, err = _validate_schema(
        {"auto_merge_ok": False, "concerns": [{"x": 1}]}
    )
    assert err is not None
    assert "concerns" in err


def test_validate_rejects_non_dict():
    _ok, _c, err = _validate_schema(["auto_merge_ok"])  # type: ignore[arg-type]
    assert err is not None


# ---------------------------------------------------------------------------
# _parse_verdict — tolerant JSON extraction


def test_parse_bare_json():
    payload = _parse_verdict('{"auto_merge_ok": true, "concerns": []}')
    assert payload == {"auto_merge_ok": True, "concerns": []}


def test_parse_fenced_json():
    text = '```json\n{"auto_merge_ok": false, "concerns": ["x"]}\n```'
    payload = _parse_verdict(text)
    assert payload == {"auto_merge_ok": False, "concerns": ["x"]}


def test_parse_extracts_first_object_from_prose():
    text = 'Here is my verdict: {"auto_merge_ok": true, "concerns": []}. Done.'
    payload = _parse_verdict(text)
    assert payload == {"auto_merge_ok": True, "concerns": []}


def test_parse_returns_none_on_garbage():
    assert _parse_verdict("not json at all") is None


def test_parse_returns_none_on_no_object():
    assert _parse_verdict("[just a list]") is None


# ---------------------------------------------------------------------------
# compute_doc_diff


def test_diff_empty_when_unchanged():
    assert compute_doc_diff("same\n", "same\n") == ""


def test_diff_contains_added_line():
    diff = compute_doc_diff("a\n", "a\nb\n")
    assert "+b" in diff
    assert "prev/body.md" in diff
    assert "new/body.md" in diff


# ---------------------------------------------------------------------------
# write_verdict_file


def test_write_verdict_safe(tmp_path: Path):
    result = DiffReviewResult(
        auto_merge_ok=True,
        concerns=[],
        attempts=1,
        cost_usd=0.0,
    )
    path = tmp_path / "verdict.json"
    write_verdict_file(result, upstream_retry_exhausted=False, path=path)
    payload = json.loads(path.read_text())
    assert payload["safe_to_auto_merge"] is True
    assert payload["auto_merge_ok"] is True
    assert payload["upstream_retry_exhausted"] is False


def test_write_verdict_blocked_by_upstream_retry_exhausted(tmp_path: Path):
    """CI-06: upstream retry-exhaustion overrides a positive Call 4 verdict."""
    result = DiffReviewResult(
        auto_merge_ok=True,
        concerns=[],
        attempts=1,
        cost_usd=0.0,
    )
    path = tmp_path / "verdict.json"
    write_verdict_file(result, upstream_retry_exhausted=True, path=path)
    payload = json.loads(path.read_text())
    assert payload["auto_merge_ok"] is True
    assert payload["upstream_retry_exhausted"] is True
    assert payload["safe_to_auto_merge"] is False


def test_write_verdict_blocked_by_call4(tmp_path: Path):
    result = DiffReviewResult(
        auto_merge_ok=False,
        concerns=["aside silently lost"],
        attempts=1,
        cost_usd=0.0,
    )
    path = tmp_path / "verdict.json"
    write_verdict_file(result, upstream_retry_exhausted=False, path=path)
    payload = json.loads(path.read_text())
    assert payload["safe_to_auto_merge"] is False
    assert "aside silently lost" in payload["concerns"]
