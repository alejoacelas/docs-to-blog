"""Shared Anthropic SDK wrapper.

Every LLM call in the daily sync goes through `call_claude`. No retries
inside this wrapper — retries live in callers' bounded loops, per PLAN §1
("The orchestrator runs deterministic validators + optional review-pass
calls in a bounded retry loop in our code, not inside an agent.").
"""

from __future__ import annotations

import os
import sys
from typing import Any

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()


def _require_api_key() -> str:
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        print(
            "ANTHROPIC_API_KEY not set. Add it to .env or the environment "
            "before running sync.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return key


# Production default per repo conventions: sonnet-4.6, the alias-form
# model ID exposed by the API.
DEFAULT_MODEL = "claude-sonnet-4-6"

_client: Anthropic | None = None


def _client_singleton() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=_require_api_key())
    return _client


def call_claude(
    system: str,
    user: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 8000,
) -> tuple[str, dict[str, Any]]:
    """Single-shot Claude call. No tools, no retries, no streaming.

    Returns (assistant_text, usage_dict) where usage_dict has at least
    `input_tokens` and `output_tokens`.
    """
    client = _client_singleton()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    # Concatenate text blocks (we don't use tool blocks here).
    chunks: list[str] = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            chunks.append(block.text)
    text = "".join(chunks)

    usage = {
        "input_tokens": int(getattr(response.usage, "input_tokens", 0)),
        "output_tokens": int(getattr(response.usage, "output_tokens", 0)),
    }
    # Some SDK versions also surface cache hits; include if present.
    for cache_field in ("cache_read_input_tokens", "cache_creation_input_tokens"):
        if hasattr(response.usage, cache_field):
            value = getattr(response.usage, cache_field)
            if value:
                usage[cache_field] = int(value)

    return text, usage


# Pricing for claude-sonnet-4-5 (sonnet-4-6): $3/MTok input, $15/MTok output.
INPUT_USD_PER_MTOK = 3.0
OUTPUT_USD_PER_MTOK = 15.0


def estimate_cost_usd(usage: dict[str, Any]) -> float:
    """Estimate $ cost from a usage dict. Cache-read tokens are billed at
    10% of normal input rate; cache-write at 1.25x; v1 reporter treats
    both as plain input for simplicity (we don't enable caching yet)."""
    inp = float(usage.get("input_tokens", 0)) + float(
        usage.get("cache_creation_input_tokens", 0)
    ) + float(usage.get("cache_read_input_tokens", 0))
    out = float(usage.get("output_tokens", 0))
    return (inp * INPUT_USD_PER_MTOK + out * OUTPUT_USD_PER_MTOK) / 1_000_000
