"""Anchor data model + helpers for Implementation A.

PLAN §6.A: every styled paragraph is identified by an `Anchor` — a
fingerprint composed of (quote.exact, optional prefix/suffix, heading,
ordinal, hash). The fingerprint survives small edits because the LLM
reconciler rewrites it on every sync; the fuzzy matcher here is only the
cheap pre-pass that surfaces candidates.

Everything mechanisable (hashing, parsing, fuzzy probing) is plain code
so the LLM call's only job is the genuinely-fuzzy "is this the same
paragraph after a rewrite?" decision.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

import diff_match_patch as dmp_module
import yaml


# ---------------------------------------------------------------------------
# Schema


@dataclass
class Quote:
    exact: str
    prefix: str = ""
    suffix: str = ""

    def to_dict(self) -> dict:
        d: dict = {"exact": self.exact}
        if self.prefix:
            d["prefix"] = self.prefix
        if self.suffix:
            d["suffix"] = self.suffix
        return d


@dataclass
class Anchor:
    cls: str  # rendered as `class` in YAML; reserved word in Python.
    quote: Quote
    heading: str
    ordinal: int
    hash: str
    confidence: str = "high"  # "high" | "low" — populated by review pass

    def to_dict(self) -> dict:
        out: dict = {
            "class": self.cls,
            "anchor": {
                "quote": self.quote.to_dict(),
                "heading": self.heading,
                "ordinal": int(self.ordinal),
                "hash": self.hash,
            },
        }
        if self.confidence != "high":
            out["confidence"] = self.confidence
        return out

    @classmethod
    def from_dict(cls, raw: dict) -> "Anchor":
        anc = raw.get("anchor") or {}
        q = anc.get("quote") or {}
        if isinstance(q, str):
            q = {"exact": q}
        return cls(
            cls=str(raw["class"]),
            quote=Quote(
                exact=str(q.get("exact", "")),
                prefix=str(q.get("prefix", "")),
                suffix=str(q.get("suffix", "")),
            ),
            heading=str(anc.get("heading", "")),
            ordinal=int(anc.get("ordinal", 1)),
            hash=str(anc.get("hash", "")),
            confidence=str(raw.get("confidence", "high")),
        )


# ---------------------------------------------------------------------------
# Hashing


def compute_paragraph_hash(text: str) -> str:
    """sha256[:8] of normalised paragraph text. Whitespace runs collapsed,
    leading/trailing stripped — so trivial reflows don't change the hash."""
    norm = re.sub(r"\s+", " ", text).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Markdown paragraph extraction


# A paragraph (per PLAN §6.A's "ordinal under heading" model) is any
# top-level block that carries prose. We treat the following as "not a
# paragraph": headings themselves, fenced code blocks, blockquotes,
# list-item bullets, and blank lines. List items DO count: an aside in a
# bulleted list still needs an ordinal slot.
#
# This is a deliberately lo-fi parser: we walk lines, group consecutive
# non-blank lines into "paragraphs", and re-emit each line's heading
# context. A real markdown-it parser would be more correct on edge cases
# (setext headings, tables), but those don't appear in the source doc;
# we can swap parsers in later without changing the call signature.

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*```")


@dataclass(frozen=True)
class Paragraph:
    text: str
    heading: str  # nearest heading text above this paragraph; "" if none
    ordinal: int  # 1-indexed position under that heading
    hash: str

    @property
    def normalised(self) -> str:
        return re.sub(r"\s+", " ", self.text).strip()


def extract_paragraphs_with_headings(markdown: str) -> list[Paragraph]:
    """Walk markdown and return every prose paragraph with its heading +
    ordinal + hash. Skips frontmatter, fenced code, and headings themselves.

    Multiple non-blank lines separated by blank lines = one paragraph.
    """
    body = _strip_frontmatter(markdown)
    lines = body.split("\n")

    paragraphs: list[Paragraph] = []
    current_heading: str = ""
    ordinal_by_heading: dict[str, int] = {"": 0}
    in_fence = False
    buf: list[str] = []

    def flush_buf() -> None:
        nonlocal buf
        if not buf:
            return
        text = "\n".join(buf).strip()
        if not text:
            buf = []
            return
        ordinal_by_heading[current_heading] = (
            ordinal_by_heading.get(current_heading, 0) + 1
        )
        ordinal = ordinal_by_heading[current_heading]
        paragraphs.append(
            Paragraph(
                text=text,
                heading=current_heading,
                ordinal=ordinal,
                hash=compute_paragraph_hash(text),
            )
        )
        buf = []

    for line in lines:
        if _FENCE_RE.match(line):
            flush_buf()
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        m = _HEADING_RE.match(line)
        if m:
            flush_buf()
            current_heading = m.group(2).strip()
            ordinal_by_heading.setdefault(current_heading, 0)
            continue

        if not line.strip():
            flush_buf()
            continue

        buf.append(line)

    flush_buf()
    return paragraphs


def _strip_frontmatter(markdown: str) -> str:
    """Drop a leading `---\\n...\\n---\\n` block if present."""
    if not markdown.startswith("---\n"):
        return markdown
    end = markdown.find("\n---", 4)
    if end == -1:
        return markdown
    rest_start = markdown.find("\n", end + 1)
    if rest_start == -1:
        return ""
    return markdown[rest_start + 1 :]


def find_paragraph(
    paragraphs: list[Paragraph], heading: str, ordinal: int
) -> Paragraph | None:
    for p in paragraphs:
        if p.heading == heading and p.ordinal == ordinal:
            return p
    return None


# ---------------------------------------------------------------------------
# Fuzzy matching (diff-match-patch pre-pass)


@dataclass(frozen=True)
class FuzzyCandidate:
    """A fuzzy-matcher hint for one prior anchor: which new paragraph (by
    heading + ordinal) likely corresponds to it, and how confident we are
    (0.0-1.0). 1.0 means an exact substring hit; lower means dmp found a
    near-miss."""

    prior_anchor_hash: str
    candidate_heading: str
    candidate_ordinal: int
    candidate_hash: str
    confidence: float


def fuzzy_match_candidates(
    prior_anchors: list[Anchor],
    new_paragraphs: list[Paragraph],
    threshold: float = 0.8,
) -> list[FuzzyCandidate]:
    """For each prior anchor, find the best-matching paragraph in the new
    doc. Uses diff-match-patch's character-level fuzzy match against the
    concatenation of new paragraphs; converts the char position back into
    a paragraph index.

    This is a HINT for the LLM call, not a directive. Claude may override.
    """
    if not prior_anchors or not new_paragraphs:
        return []

    dmp = dmp_module.diff_match_patch()
    # dmp.Match_Threshold: 0 = exact, 1 = match anything. Our `threshold`
    # convention (PLAN/project.toml) is "closer to 1.0 = stricter", so
    # invert: dmp_threshold = 1 - our_threshold.
    dmp.Match_Threshold = max(0.0, min(1.0, 1.0 - threshold))
    dmp.Match_Distance = 10000  # allow matches anywhere in the doc

    # Build a positional map: byte offset → paragraph index.
    haystack_parts: list[str] = []
    para_offsets: list[int] = []
    cursor = 0
    SEP = "\n\n"
    for p in new_paragraphs:
        para_offsets.append(cursor)
        haystack_parts.append(p.normalised)
        cursor += len(p.normalised) + len(SEP)
    haystack = SEP.join(haystack_parts)

    def offset_to_paragraph(offset: int) -> Paragraph | None:
        for i in range(len(para_offsets) - 1, -1, -1):
            if para_offsets[i] <= offset:
                return new_paragraphs[i]
        return None

    candidates: list[FuzzyCandidate] = []
    for anchor in prior_anchors:
        needle = re.sub(r"\s+", " ", anchor.quote.exact).strip()
        if not needle:
            continue
        # Use the prior anchor's heading+ordinal as a hint for `loc`.
        hint_para = find_paragraph(new_paragraphs, anchor.heading, anchor.ordinal)
        loc = para_offsets[new_paragraphs.index(hint_para)] if hint_para else 0
        # dmp's match_main has a hard 32-char limit on the pattern; we
        # shrink long quotes to their first 28 chars + suffix marker.
        probe = needle if len(needle) <= 32 else needle[:32]
        try:
            pos = dmp.match_main(haystack, probe, loc)
        except Exception:
            pos = -1

        if pos < 0:
            # Fallback: try a plain substring on the full needle (cheap).
            sub = haystack.find(needle)
            if sub >= 0:
                candidate = offset_to_paragraph(sub)
                if candidate is not None:
                    candidates.append(
                        FuzzyCandidate(
                            prior_anchor_hash=anchor.hash,
                            candidate_heading=candidate.heading,
                            candidate_ordinal=candidate.ordinal,
                            candidate_hash=candidate.hash,
                            confidence=1.0,
                        )
                    )
            continue

        candidate = offset_to_paragraph(pos)
        if candidate is None:
            continue
        # Confidence: 1.0 if the needle is verbatim in the candidate;
        # otherwise an approximation from the dmp threshold.
        if needle in candidate.normalised or candidate.normalised in needle:
            confidence = 1.0
        else:
            confidence = max(0.0, 1.0 - dmp.Match_Threshold)
        candidates.append(
            FuzzyCandidate(
                prior_anchor_hash=anchor.hash,
                candidate_heading=candidate.heading,
                candidate_ordinal=candidate.ordinal,
                candidate_hash=candidate.hash,
                confidence=round(confidence, 3),
            )
        )

    return candidates


# ---------------------------------------------------------------------------
# Load / save


def load_anchors(path: Path) -> list[Anchor]:
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text()) or {}
    return [Anchor.from_dict(r) for r in (raw.get("paragraphs") or [])]


def save_anchors(anchors: Iterable[Anchor], path: Path) -> None:
    """Write anchors as a sorted, deterministic YAML file with trailing
    newline. Order: heading (alphabetical), then ordinal (numeric)."""
    sorted_anchors = sorted(
        anchors, key=lambda a: (a.heading.lower(), a.ordinal, a.cls)
    )
    payload = {"paragraphs": [a.to_dict() for a in sorted_anchors]}
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(
        payload,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=1000,
    )
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text)


def dumps_anchors(anchors: Iterable[Anchor]) -> str:
    """In-memory equivalent of save_anchors. Used by the prompt builder."""
    sorted_anchors = sorted(
        anchors, key=lambda a: (a.heading.lower(), a.ordinal, a.cls)
    )
    payload = {"paragraphs": [a.to_dict() for a in sorted_anchors]}
    return yaml.safe_dump(
        payload,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=1000,
    )
