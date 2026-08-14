"""Persistent job state, stored as a single human-diffable JSON file.

Lifecycle:
  - first-seen tracking: the moment WE first saw a job (powers "🆕" + sorting)
  - open/closed tracking: mark closed when job disappears from successful fetch
  - retention: long-closed records are purged so the file never grows unbounded
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta

from . import filters


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)


_REFRESH_FIELDS = (
    "title",
    "location",
    "region",
    "url",
    "season",
    "season_inferred",
    "category",
    "salary",
    "company",
    "source",
    "company_slug",
)


def _normalize_region(location: str) -> str:
    """Classify a raw location string into India / Remote / Other."""
    if not location:
        return "Other"
    if filters.is_india(location):
        return "India"
    if filters.is_remote_or_hybrid(location):
        return "Remote"
    return "Other"


def upsert(
    existing: dict,
    jobs: list[dict],
    succeeded_keys: set[str],
    enriched_ids: set[str] | None = None,
) -> list[str]:
    """Merge freshly-fetched jobs into the existing store.
    Returns the list of NEWLY-seen job ids.
    """
    ts = now_iso()
    enriched_ids = enriched_ids or set()
    seen_ids: set[str] = set()
    new_ids: list[str] = []

    for job in jobs:
        jid = job["id"]
        seen_ids.add(jid)
        # Always compute the normalized region from raw location
        job["region"] = _normalize_region(job.get("location", ""))
        if jid in existing:
            record = existing[jid]
            for key in _REFRESH_FIELDS:
                if key in job:
                    record[key] = job[key]
            if not record.get("posted_at") and job.get("posted_at"):
                record["posted_at"] = job["posted_at"]
            if job.get("skills") is not None:
                record["skills"] = job["skills"]
            if record.get("closed_at"):
                del record["closed_at"]
            record["last_seen_at"] = ts
            record["is_open"] = True
        else:
            record = dict(job)
            record["first_seen_at"] = ts
            record["last_seen_at"] = ts
            record["is_open"] = True
            existing[jid] = record
            new_ids.append(jid)
        if jid in enriched_ids:
            existing[jid]["enriched_at"] = ts

    # Close jobs that belong to a successfully-fetched company but didn't appear.
    for jid, record in existing.items():
        company_key = f"{record.get('source')}:{record.get('company_slug')}"
        if (
            company_key in succeeded_keys
            and jid not in seen_ids
            and record.get("is_open")
        ):
            record["is_open"] = False
            record["closed_at"] = ts

    return new_ids


def purge(existing: dict, keep_closed_days: int = 60) -> int:
    cutoff = (datetime.now(UTC) - timedelta(days=keep_closed_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    stale = [
        jid
        for jid, record in existing.items()
        if not record.get("is_open")
        and (record.get("closed_at") or record.get("last_seen_at") or "") < cutoff
    ]
    for jid in stale:
        del existing[jid]
    return len(stale)
