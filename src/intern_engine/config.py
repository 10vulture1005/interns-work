"""Tunable settings, loaded from data/config.json (with safe defaults).

Configured for India-based internship tracking.
"""

from __future__ import annotations

import json
import os
import re

from . import paths

DEFAULTS = {
    "cycles": ["Summer 2027", "Fall 2026"],
    "default_cycle": "Summer 2027",
    "regions": ["India", "Remote"],
    "role_scope": "tech",
}

_FALLBACK_REPO = "your-username/intern-engine-india"

_INDIA_TOKENS = {"india", "in", "bharat"}
_REMOTE_TOKENS = {"remote", "wfh", "work from home", "anywhere"}


def repo_slug() -> str:
    """'owner/name' for this repo: from Actions env, else the git remote."""
    env = os.environ.get("GITHUB_REPOSITORY")
    if env and "/" in env:
        return env
    try:
        with open(os.path.join(paths.ROOT, ".git", "config"), encoding="utf-8") as f:
            m = re.search(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?\s", f.read())
            if m:
                return m.group(1)
    except OSError:
        pass
    return _FALLBACK_REPO


def pages_base() -> str:
    owner, _, name = repo_slug().partition("/")
    return f"https://{owner.lower()}.github.io/{name}"


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(paths.CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, json.JSONDecodeError):
        pass
    return cfg


def cycles(cfg: dict) -> list[str]:
    return list(cfg.get("cycles") or DEFAULTS["cycles"])


def want_india(cfg: dict) -> bool:
    return any(str(r).lower() in _INDIA_TOKENS for r in (cfg.get("regions") or []))


def want_remote(cfg: dict) -> bool:
    return any(str(r).lower() in _REMOTE_TOKENS for r in (cfg.get("regions") or []))


def restrict_region(cfg: dict) -> bool:
    regions = cfg.get("regions") or []
    if not regions:
        return False
    return not any(str(r).lower() in {"global", "worldwide", "any"} for r in regions)


def max_age_days(cfg: dict):
    return cfg.get("max_age_days", 365)


def max_per_company(cfg: dict):
    return cfg.get("max_per_company", 0)


def infer_undated(cfg: dict) -> bool:
    return bool(cfg.get("infer_undated", True))


def infer_max_age_days(cfg: dict) -> int:
    return int(cfg.get("infer_max_age_days", 45))


def section_limit(cfg: dict, label: str):
    return (cfg.get("section_limits") or {}).get(label)
