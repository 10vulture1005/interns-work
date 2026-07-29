"""Generate slug candidates for ATS brute-force probing.

Given a canonical company name (e.g. ``"zepto"`` or ``"national-payments-coorperation-india"``),
produce 10-15 URL slug guesses in priority order so the discovery probe can
short-circuit on the first hit.

This module is **pure** — no I/O, no network calls — so it's trivial to unit test.
"""

from __future__ import annotations

import re

# Suffixes that are likely disambiguation artifacts, not part of the real ATS slug.
_STRIP_SUFFIXES = re.compile(
    r"[-_](?:"
    r"\d+|suite|india|global|hq|inc|corp|llc|ltd|io|ai|tech|labs|group"
    r")$",
    re.I,
)

# Multi-word names where the acronym is the most common ATS slug.
_ACRONYM_OVERRIDES: dict[str, str] = {
    "national-payments-coorperation-india": "npci",
    "national-payments-corporation-india": "npci",
    "general-electric": "ge",
    "texas-instruments": "ti",
    "deutsche-bank": "db",
    "bank-of-america": "bofa",
    "american-express": "amex",
    "larsen-toubro": "lnt",
    "lg-electronics": "lge",
}


def _slugify(raw: str) -> str:
    """Normalize a string to a URL-safe, lowercase slug."""
    return re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")


def _strip_suffix(slug: str) -> str | None:
    """Remove trailing disambiguation suffixes (e.g. '-2', '-suite')."""
    stripped = _STRIP_SUFFIXES.sub("", slug)
    return stripped if stripped and stripped != slug else None


def _concat(slug: str) -> str:
    """Remove all hyphens: 'de-shaw' → 'deshaw'."""
    return slug.replace("-", "")


def _acronym(slug: str) -> str | None:
    """First letter of each word: 'bank-of-america' → 'boa'."""
    parts = slug.split("-")
    if len(parts) < 2:
        return None
    acr = "".join(p[0] for p in parts if p)
    return acr if len(acr) >= 2 else None


def generate_candidates(name: str) -> list[str]:
    """Return 10-15 slug candidates for *name*, most likely first.

    >>> "zepto" in generate_candidates("zepto")
    True
    >>> "npci" in generate_candidates("national-payments-coorperation-india")
    True
    >>> "ramp" in generate_candidates("ramp-2")
    True
    """
    base = _slugify(name)
    if not base:
        return []

    seen: set[str] = set()
    candidates: list[str] = []

    def _add(slug: str) -> None:
        if slug and slug not in seen and re.fullmatch(r"[a-z0-9][a-z0-9\-]*", slug):
            seen.add(slug)
            candidates.append(slug)

    # ── Priority 1: exact + concatenated ────────────────────────────
    _add(base)
    _add(_concat(base))

    # ── Priority 2: suffix-stripped variants ─────────────────────────
    stripped = _strip_suffix(base)
    if stripped:
        _add(stripped)
        _add(_concat(stripped))

    # ── Priority 3: known acronym overrides ──────────────────────────
    override = _ACRONYM_OVERRIDES.get(base)
    if override:
        _add(override)

    # ── Priority 4: computed acronym (multi-word names) ──────────────
    acr = _acronym(base)
    if acr:
        _add(acr)

    # ── Priority 5: common suffix patterns ───────────────────────────
    root = stripped or base
    concat_root = _concat(root)
    for suffix in ("hq", "io", "tech", "technologies", "inc", "labs", "ai"):
        _add(f"{concat_root}{suffix}")

    # ── Priority 6: common prefix patterns ───────────────────────────
    for prefix in ("get", "join", "hire"):
        _add(f"{prefix}{concat_root}")

    # ── Priority 7: career-page patterns ─────────────────────────────
    _add(f"{concat_root}-careers")
    _add(f"{concat_root}careers")

    # ── Priority 8: hyphenated suffix variants ───────────────────────
    for suffix in ("hq", "io", "tech", "inc"):
        _add(f"{root}-{suffix}")

    return candidates
