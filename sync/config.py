"""Load and validate project.toml.

Every sync script imports `load_config()` first. A missing or malformed field
exits the process before any API call so cron failures surface with a clear
field-level message instead of a downstream stack trace.
"""

from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "project.toml"

VALID_IMPLEMENTATIONS = {"a", "b"}
VALID_DEPLOY_TARGETS = {"vercel", "cloudflare-pages", "github-pages"}


@dataclass(frozen=True)
class DocConfig:
    url: str
    library_url: str
    styling_tab_title: str
    implementation: str


@dataclass(frozen=True)
class SyncConfig:
    cron: str
    auto_merge: bool


@dataclass(frozen=True)
class AnchoringConfig:
    fuzzy_threshold: float
    max_cost_usd: float


@dataclass(frozen=True)
class DeployConfig:
    target: str


@dataclass(frozen=True)
class Config:
    doc: DocConfig
    sync: SyncConfig
    anchoring: AnchoringConfig
    deploy: DeployConfig


def _type_label(expected: type | tuple[type, ...]) -> str:
    if isinstance(expected, tuple):
        return " or ".join(t.__name__ for t in expected)
    return expected.__name__


def _require(
    section: dict,
    section_name: str,
    key: str,
    expected_type: type | tuple[type, ...],
    errors: list[str],
):
    if key not in section:
        errors.append(f"[{section_name}] missing required field `{key}`")
        return None
    value = section[key]
    # bool is a subclass of int; reject silently-coerced bools where we expect numbers.
    if isinstance(expected_type, tuple) and bool not in expected_type and isinstance(value, bool):
        errors.append(
            f"[{section_name}] field `{key}` must be {_type_label(expected_type)}, got bool"
        )
        return None
    if not isinstance(value, expected_type):
        errors.append(
            f"[{section_name}] field `{key}` must be {_type_label(expected_type)}, "
            f"got {type(value).__name__}"
        )
        return None
    return value


def load_config(path: Path | None = None) -> Config:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise SystemExit(f"project.toml not found at {config_path}")

    with config_path.open("rb") as f:
        raw = tomllib.load(f)

    errors: list[str] = []

    doc_section = raw.get("doc", {})
    doc_url = _require(doc_section, "doc", "url", str, errors)
    doc_library_url = _require(doc_section, "doc", "library_url", str, errors)
    doc_styling_tab = _require(doc_section, "doc", "styling_tab_title", str, errors)
    doc_impl = _require(doc_section, "doc", "implementation", str, errors)
    if doc_impl is not None and doc_impl not in VALID_IMPLEMENTATIONS:
        errors.append(
            f"[doc] `implementation` must be one of {sorted(VALID_IMPLEMENTATIONS)}, got {doc_impl!r}"
        )

    sync_section = raw.get("sync", {})
    sync_cron = _require(sync_section, "sync", "cron", str, errors)
    sync_auto_merge = _require(sync_section, "sync", "auto_merge", bool, errors)

    anchoring_section = raw.get("anchoring", {})
    fuzzy_threshold = _require(
        anchoring_section, "anchoring", "fuzzy_threshold", (int, float), errors
    )
    max_cost_usd = _require(
        anchoring_section, "anchoring", "max_cost_usd", (int, float), errors
    )

    deploy_section = raw.get("deploy", {})
    deploy_target = _require(deploy_section, "deploy", "target", str, errors)
    if deploy_target is not None and deploy_target not in VALID_DEPLOY_TARGETS:
        errors.append(
            f"[deploy] `target` must be one of {sorted(VALID_DEPLOY_TARGETS)}, got {deploy_target!r}"
        )

    if errors:
        message = "Invalid project.toml:\n  - " + "\n  - ".join(errors)
        raise SystemExit(message)

    return Config(
        doc=DocConfig(
            url=doc_url,
            library_url=doc_library_url,
            styling_tab_title=doc_styling_tab,
            implementation=doc_impl,
        ),
        sync=SyncConfig(cron=sync_cron, auto_merge=sync_auto_merge),
        anchoring=AnchoringConfig(
            fuzzy_threshold=float(fuzzy_threshold),
            max_cost_usd=float(max_cost_usd),
        ),
        deploy=DeployConfig(target=deploy_target),
    )


if __name__ == "__main__":
    cfg = load_config()
    print("project.toml OK")
    print(cfg)
    sys.exit(0)
